"""Persist extracted intelligence without losing the NLP contract's provenance."""
from datetime import datetime
import uuid
import httpx
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from core.config import settings
from core.dates import parse_date, iso_date
from crud import crud
from database.models import Entity, Relation, Behavior, TemporalEvent, Evidence, Document


class NoveltyEngine:
    def __init__(self, db):
        self.db = db

    def process_nlp_payload(self, document_id, payload, published_at=None):
        db = self.db
        results = {'entities_processed': 0, 'relations': dict.fromkeys(['NEW', 'KNOWN', 'UPDATED', 'CONFLICTING', 'UNCERTAIN'], 0), 'behaviors': 0}
        entity_map = {}
        for data in payload.get('entities', []):
            name = data.get('canonical_name') or data['mention']
            key = (name, data['type'])
            if key in entity_map:
                continue
            entity = crud.get_entity_by_name(db, name, data['type'])
            if entity is None:
                entity = crud.create_entity(db, name, data['type'], data['confidence'])
                crud.log_intelligence_change(db, 'Entity', entity.id, 'NEW', document_id, 'First extracted mention in this knowledge base.')
            else:
                entity.last_seen_at = datetime.utcnow()
                entity.confidence = max(entity.confidence, data['confidence'])
            entity_map[key] = entity
            results['entities_processed'] += 1

        def lookup(name, kind=None):
            if kind:
                return entity_map.get((name, kind))
            matches = [e for (n, _), e in entity_map.items() if n == name]
            return matches[0] if len(matches) == 1 else None

        jobs = []
        for fact in payload.get('relations', []):
            sub = lookup(fact['subject'], fact.get('subject_type'))
            obj = lookup(fact['object'], fact.get('object_type'))
            if sub and obj:
                jobs.append((fact, sub, obj))
        subject_ids = {sub.id for _, sub, _ in jobs}
        siblings = db.query(Relation).filter(Relation.subject_id.in_(subject_ids), Relation.status.in_(['ACTIVE', 'HISTORICAL'])).all() if subject_ids else []
        sibling_ids = [r.id for r in siblings]
        entity_ids = {r.subject_id for r in siblings} | {r.object_id for r in siblings}
        known = {e.id: e for e in db.query(Entity).options(selectinload(Entity.aliases)).filter(Entity.id.in_(entity_ids)).all()} if entity_ids else {}
        # Use actual source publication dates, never ingestion times, to order assessments.
        evidence_dates = {}
        if sibling_ids:
            rows = db.query(Evidence.relation_id, Document.published_at).join(Document, Evidence.document_id == Document.id).filter(Evidence.relation_id.in_(sibling_ids)).all()
            for relation_id, date in rows:
                if date:
                    evidence_dates.setdefault(relation_id, []).append(date)
        candidates = []
        for rel in siblings:
            sub, obj = known[rel.subject_id], known[rel.object_id]
            dates = evidence_dates.get(rel.id, [])
            first = rel.source_first_seen_at or (min(dates) if dates else None)
            last = rel.source_last_seen_at or (max(dates) if dates else None)
            candidates.append({'fact_id': str(rel.id), 'subject': sub.canonical_name,
                'subject_aliases': [a.alias for a in sub.aliases], 'relation': rel.relation_type,
                'object': obj.canonical_name, 'object_aliases': [a.alias for a in obj.aliases],
                'status': rel.status, 'negated': rel.negated,
                'first_seen_at': iso_date(first), 'last_seen_at': iso_date(last)})
        classifications = []
        if jobs:
            # One call per document. Fail visibly and roll back if classification is unavailable.
            with httpx.Client(timeout=settings.NLP_TIMEOUT_SECONDS) as client:
                response = client.post(f'{settings.NLP_SERVICE_URL}/classify_novelty', json={
                    'document_id': str(document_id), 'published_at': iso_date(published_at),
                    'facts': [fact for fact, _, _ in jobs], 'candidates': candidates})
                response.raise_for_status()
                classifications = response.json()['results']
            if len(classifications) != len(jobs):
                raise ValueError('NLP returned an incomplete novelty classification.')
        source_date = parse_date(published_at)
        for (fact, sub, obj), decision in zip(jobs, classifications):
            status = decision['status']
            if status not in results['relations']:
                raise ValueError('NLP returned an unknown novelty label.')
            matched = decision.get('matched_fact_id')
            relation = db.get(Relation, uuid.UUID(matched)) if status == 'KNOWN' and matched else None
            if status == 'KNOWN' and relation is None:
                raise ValueError('Known fact is missing from the database.')
            if relation is None:
                # A retry must not duplicate an already committed fact with identical polarity/status.
                relation = db.query(Relation).filter_by(subject_id=sub.id, object_id=obj.id,
                    relation_type=fact['relation'], negated=fact.get('negated', False),
                    status='UNCERTAIN' if status == 'UNCERTAIN' else 'ACTIVE').first()
                if relation is None:
                    relation = Relation(subject_id=sub.id, object_id=obj.id, relation_type=fact['relation'],
                        negated=fact.get('negated', False), confidence=fact['confidence'],
                        status='UNCERTAIN' if status == 'UNCERTAIN' else 'ACTIVE')
                    db.add(relation)
                    db.flush()
            relation.last_seen_at = datetime.utcnow()
            relation.confidence = max(relation.confidence, fact['confidence'])
            if source_date:
                relation.source_first_seen_at = min(relation.source_first_seen_at or source_date, source_date)
                relation.source_last_seen_at = max(relation.source_last_seen_at or source_date, source_date)
            for old_id in decision.get('superseded_fact_ids', []):
                old = db.get(Relation, uuid.UUID(old_id))
                if old:
                    old.status = 'HISTORICAL'
            if status in ('CONFLICTING', 'UNCERTAIN'):
                relation.review_required = True
                for old_id in decision.get('conflicting_fact_ids', []):
                    old = db.get(Relation, uuid.UUID(old_id))
                    if old:
                        old.review_required = True
            evidence = fact.get('evidence') or {}
            crud.create_evidence(db, document_id, relation.id, None, evidence.get('text', ''), evidence)
            crud.log_intelligence_change(db, 'Relation', relation.id, status, document_id, decision.get('reason'))
            results['relations'][status] += 1

        for data in payload.get('behaviors', []):
            evidence = data.get('evidence') or {}
            mentions = [e for e in payload.get('entities', []) if
                e['type'] in ('THREAT_ACTOR', 'MALWARE', 'TOOL') and
                evidence.get('char_start', -1) <= e.get('char_start', -2) < evidence.get('char_end', -1)]
            actors = {lookup(e.get('canonical_name') or e['mention'], e['type']).id for e in mentions
                      if e['type'] == 'THREAT_ACTOR' and lookup(e.get('canonical_name') or e['mention'], e['type'])}
            codes = {lookup(e.get('canonical_name') or e['mention'], e['type']).id for e in mentions
                     if lookup(e.get('canonical_name') or e['mention'], e['type'])}
            owners = actors or codes
            owner = next(iter(owners)) if len(owners) == 1 else None
            # Ambiguous behaviors stay document-level, rather than being assigned to an arbitrary actor.
            behavior = db.query(Behavior).filter_by(document_id=document_id, description=data['description'],
                mitre_attack_id=data.get('mitre_attack_id'), entity_id=owner).first()
            if behavior is None:
                behavior = crud.create_behavior(db, document_id, owner, data['description'], data.get('mitre_attack_id'), data['confidence'])
            crud.create_evidence(db, document_id, None, behavior.id, evidence.get('text', ''), evidence)
            results['behaviors'] += 1
        for data in payload.get('temporal_events', []):
            entity = lookup(data['entity'])
            if entity and not db.query(TemporalEvent).filter_by(document_id=document_id, entity_id=entity.id,
                    time=data['time'], type=data['type'], event=data['event']).first():
                db.add(TemporalEvent(document_id=document_id, entity_id=entity.id, event=data['event'],
                    time=data['time'], type=data['type'], confidence=data['confidence'], evidence=data.get('evidence')))
        db.flush()
        return results
