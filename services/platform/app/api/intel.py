"""Bounded read APIs, batched graph queries, evidence-aware timelines, and exports."""
import csv
import io
import json
import uuid
from datetime import datetime, timezone, date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, or_, union_all, select
from sqlalchemy.orm import Session, selectinload
from database.database import get_db, qdrant, COLLECTION_NAME
from database.models import Document, Entity, Relation, Evidence, Behavior, IntelligenceChange, TemporalEvent
from core.config import settings
from core.dates import iso_date
import httpx

router = APIRouter()


def entity_dict(e, counts=None):
    return {'id': str(e.id), 'name': e.canonical_name, 'type': e.type, 'confidence': e.confidence,
            'relations': (counts or {}).get(e.id, 0), 'first_seen_at': iso_date(e.first_seen_at)}


def relation_counts(db):
    endpoints = union_all(select(Relation.subject_id.label('entity_id')).where(Relation.status == 'ACTIVE', Relation.negated == False),
                          select(Relation.object_id.label('entity_id')).where(Relation.status == 'ACTIVE', Relation.negated == False)).subquery()
    return dict(db.query(endpoints.c.entity_id, func.count()).group_by(endpoints.c.entity_id).all())


@router.get('/dashboard/stats')
def get_dashboard_stats(db: Session = Depends(get_db)):
    statuses = dict(db.query(Document.processing_status, func.count(Document.id)).group_by(Document.processing_status).all())
    changes = dict(db.query(IntelligenceChange.change_type, func.count(IntelligenceChange.id)).group_by(IntelligenceChange.change_type).all())
    return {'metrics': {'documents': sum(statuses.values()), 'processed': statuses.get('COMPLETED', 0),
        'pending': statuses.get('PENDING', 0) + statuses.get('PROCESSING', 0), 'failed': statuses.get('FAILED', 0),
        'entities': db.query(Entity).count(), 'relations': db.query(Relation).filter(Relation.status == 'ACTIVE', Relation.negated == False).count(),
        'entity_types': dict(db.query(Entity.type, func.count(Entity.id)).group_by(Entity.type).all()),
        **{k.lower(): changes.get(k, 0) for k in ['NEW', 'KNOWN', 'UPDATED', 'CONFLICTING', 'UNCERTAIN']}}}


def load_evidence(db, relation_ids=(), behavior_ids=()):
    filters = []
    if relation_ids:
        filters.append(Evidence.relation_id.in_(relation_ids))
    if behavior_ids:
        filters.append(Evidence.behavior_id.in_(behavior_ids))
    rows = db.query(Evidence).filter(or_(*filters)).all() if filters else []
    doc_ids = {e.document_id for e in rows}
    docs = {d.id: d for d in db.query(Document).options(selectinload(Document.source)).filter(Document.id.in_(doc_ids)).all()} if doc_ids else {}
    return rows, docs


def evidence_dict(e, docs):
    doc = docs.get(e.document_id) if e else None
    return {'snippet': e.snippet, 'char_start': e.char_start, 'char_end': e.char_end, 'page_number': e.page_number,
            'document_id': str(e.document_id), 'source_name': doc.source.name if doc else 'Unknown',
            'source_url': doc.url if doc else None, 'published_at': iso_date(doc.published_at) if doc else None} if e else None


@router.get('/intelligence/feed')
def get_intelligence_feed(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    changes = db.query(IntelligenceChange).order_by(IntelligenceChange.timestamp.desc(), IntelligenceChange.id).offset(offset).limit(limit).all()
    relation_ids = [c.entity_id for c in changes if c.entity_type == 'Relation']
    relations = {r.id: r for r in db.query(Relation).filter(Relation.id.in_(relation_ids)).all()} if relation_ids else {}
    entity_ids = {c.entity_id for c in changes if c.entity_type == 'Entity'} | {r.subject_id for r in relations.values()} | {r.object_id for r in relations.values()}
    entities = {e.id: e for e in db.query(Entity).filter(Entity.id.in_(entity_ids)).all()} if entity_ids else {}
    evidence, docs = load_evidence(db, relation_ids)
    by_relation = {}
    for e in evidence:
        by_relation.setdefault(e.relation_id, []).append(e)
    result = []
    for c in changes:
        item = {'id': str(c.id), 'change_type': c.change_type, 'entity_type': c.entity_type,
                'timestamp': iso_date(c.timestamp), 'explanation': c.reason or 'Legacy classification; detailed reasoning was not retained.'}
        if c.entity_type == 'Entity' and c.entity_id in entities:
            e = entities[c.entity_id]
            item.update(description=f"{e.type.replace('_', ' ').title()} '{e.canonical_name}' identified",
                        fact={'subject': e.canonical_name, 'type': e.type}, confidence=e.confidence)
        elif c.entity_id in relations:
            r = relations[c.entity_id]
            sub, obj = entities.get(r.subject_id), entities.get(r.object_id)
            if sub and obj:
                item.update(description=f"{sub.canonical_name} → {'NOT ' if r.negated else ''}{r.relation_type} → {obj.canonical_name}",
                    fact={'subject': sub.canonical_name, 'subject_id': str(sub.id), 'relation': r.relation_type,
                          'object': obj.canonical_name, 'negated': r.negated}, confidence=r.confidence)
                choices = by_relation.get(r.id, [])
                ev = next((e for e in choices if e.document_id == c.document_id), choices[0] if choices else None)
                item['evidence'] = evidence_dict(ev, docs)
        result.append(item)
    return result


@router.get('/graph/explore')
def explore_graph(db: Session = Depends(get_db), query: str = '', entity_type: str = '',
                  since: date | None = None, until: date | None = None,
                  focus_id: uuid.UUID | None = None,
                  limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)):
    if since and until and since > until:
        raise HTTPException(422, 'Start date must not be after end date.')
    entities = db.query(Entity)
    if query.strip():
        from database.models import EntityAlias
        aliases = select(EntityAlias.entity_id).where(EntityAlias.alias.ilike(f'%{query.strip()}%'))
        entities = entities.filter(or_(Entity.canonical_name.ilike(f'%{query.strip()}%'), Entity.id.in_(aliases)))
    if entity_type and entity_type != 'ALL':
        entities = entities.filter(Entity.type == entity_type)
    if since:
        entities = entities.filter(Entity.last_seen_at >= datetime.combine(since, datetime.min.time()))
    if until:
        entities = entities.filter(Entity.last_seen_at < datetime.combine(until + timedelta(days=1), datetime.min.time()))
    center = None
    if focus_id:
        center = db.get(Entity, focus_id)
        if center is None:
            raise HTTPException(404, 'Entity not found.')
        neighbors = union_all(
            select(Relation.object_id.label('entity_id')).where(Relation.subject_id == focus_id, Relation.status == 'ACTIVE', Relation.negated == False),
            select(Relation.subject_id.label('entity_id')).where(Relation.object_id == focus_id, Relation.status == 'ACTIVE', Relation.negated == False)).subquery()
        entities = entities.filter(Entity.id.in_(select(neighbors.c.entity_id)), Entity.id != focus_id)
    total = entities.count()
    page = entities.order_by(Entity.last_seen_at.desc(), Entity.id).offset(offset).limit(limit).all()
    displayed = ([center] if center else []) + page
    ids = [e.id for e in displayed]
    links = db.query(Relation).filter(Relation.subject_id.in_(ids), Relation.object_id.in_(ids),
        Relation.status == 'ACTIVE', Relation.negated == False).order_by(Relation.last_seen_at.desc(), Relation.id).limit(2001).all() if ids else []
    return {'nodes': [{'id': str(e.id), 'name': e.canonical_name, 'group': e.type} for e in displayed],
            'links': [{'source': str(r.subject_id), 'target': str(r.object_id), 'label': r.relation_type,
                       'review_required': r.review_required} for r in links[:2000]],
            'total_entities': db.query(Entity).count(), 'total_matches': total,
            'offset': offset, 'page_count': len(page), 'has_more': offset + len(page) < total,
            'links_truncated': len(links) > 2000, 'node_limit': limit}


@router.get('/graph')
def get_knowledge_graph(db: Session = Depends(get_db), limit: int = Query(200, ge=1, le=1000)):
    # Keep both ends of recent relationships together in the bounded view.
    # Selecting only recent entity mentions can hide almost every useful edge.
    recent = db.query(Relation.subject_id, Relation.object_id).filter(
        Relation.status == 'ACTIVE', Relation.negated == False).order_by(
        Relation.last_seen_at.desc(), Relation.id).limit(1000).all()
    selected = set()
    for subject_id, object_id in recent:
        pair = {subject_id, object_id}
        if len(selected | pair) <= limit:
            selected.update(pair)
        if len(selected) == limit:
            break
    entities = db.query(Entity).filter(Entity.id.in_(selected)).order_by(Entity.last_seen_at.desc(), Entity.id).all() if selected else []
    if len(entities) < limit:
        entities += db.query(Entity).filter(~Entity.id.in_(selected)).order_by(
            Entity.last_seen_at.desc(), Entity.id).limit(limit - len(entities)).all()
    ids = [e.id for e in entities]
    relations = db.query(Relation).filter(Relation.subject_id.in_(ids), Relation.object_id.in_(ids),
        Relation.status == 'ACTIVE', Relation.negated == False).order_by(Relation.last_seen_at.desc()).limit(1000).all() if ids else []
    return {'nodes': [{'id': str(e.id), 'name': e.canonical_name, 'group': e.type} for e in entities],
            'links': [{'source': str(r.subject_id), 'target': str(r.object_id), 'label': r.relation_type,
                       'review_required': r.review_required} for r in relations],
            'total_entities': db.query(Entity).count(), 'node_limit': limit}


@router.get('/entities')
def get_all_entities(db: Session = Depends(get_db), limit: int = Query(250, ge=1, le=1000), offset: int = Query(0, ge=0), query: str | None = None):
    q = db.query(Entity)
    if query:
        q = q.filter(Entity.canonical_name.ilike(f'%{query}%'))
    entities = q.order_by(Entity.last_seen_at.desc(), Entity.id).offset(offset).limit(limit).all()
    return _entity_rows(db, entities)


def _entity_rows(db, entities):
    counts = relation_counts(db)
    return [entity_dict(e, counts) for e in entities]


def document_dict(doc, score=None):
    return {'id': str(doc.id), 'title': doc.title, 'external_id': doc.external_id,
        'status': doc.processing_status, 'date': iso_date(doc.first_seen_at), 'published_at': iso_date(doc.published_at),
        'score': score, 'embedding_status': doc.embedding_status, 'error': doc.processing_error}


@router.get('/documents')
def get_documents(query: str | None = Query(None, max_length=500), db: Session = Depends(get_db),
                  limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    if not query or not query.strip():
        docs = db.query(Document).order_by(Document.first_seen_at.desc(), Document.id).offset(offset).limit(limit).all()
        return [document_dict(d) for d in docs]
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(f'{settings.NLP_SERVICE_URL}/embed', json={'texts': [query.strip()]})
            response.raise_for_status()
            vector = response.json()['embeddings'][0]
        hits = qdrant.query_points(collection_name=COLLECTION_NAME, query=vector, limit=limit, offset=offset).points
        ids = [uuid.UUID(str(hit.id)) for hit in hits]
        docs = {d.id: d for d in db.query(Document).filter(Document.id.in_(ids)).all()} if ids else {}
        return [document_dict(docs[uuid.UUID(str(h.id))], round(h.score, 4)) for h in hits if uuid.UUID(str(h.id)) in docs]
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('Semantic search failed')
        raise HTTPException(503, 'Semantic search is unavailable. Clear the search to browse reports, or retry shortly.') from exc


@router.get('/documents/{doc_id}')
def get_document_details(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, 'Document not found.')
    return {**document_dict(doc), 'content': doc.content, 'url': doc.url, 'processing': doc.processing_metadata,
            'behaviors': [{'description': b.description, 'mitre_attack_id': b.mitre_attack_id,
                            'confidence': b.confidence, 'entity_id': str(b.entity_id) if b.entity_id else None}
                          for b in db.query(Behavior).filter_by(document_id=doc.id).all()]}


@router.get('/intelligence/entity/{entity_id}/timeline')
def get_entity_timeline(entity_id: uuid.UUID, db: Session = Depends(get_db)):
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(404, 'Entity not found.')
    relations = db.query(Relation).filter(or_(Relation.subject_id == entity_id, Relation.object_id == entity_id)).order_by(Relation.last_seen_at.desc()).limit(200).all()
    behaviors = db.query(Behavior).filter_by(entity_id=entity_id).limit(200).all()
    events = db.query(TemporalEvent).filter_by(entity_id=entity_id).limit(200).all()
    ids = {r.subject_id for r in relations} | {r.object_id for r in relations}
    entities = {e.id: e for e in db.query(Entity).filter(Entity.id.in_(ids)).all()} if ids else {}
    evidence, docs = load_evidence(db, [r.id for r in relations], [b.id for b in behaviors])
    extra_ids = {t.document_id for t in events} | {b.document_id for b in behaviors}
    if extra_ids:
        docs.update({d.id: d for d in db.query(Document).options(selectinload(Document.source)).filter(Document.id.in_(extra_ids)).all()})
    rel_evidence, beh_evidence = {}, {}
    for e in evidence:
        if e.relation_id:
            rel_evidence.setdefault(e.relation_id, e)
        if e.behavior_id:
            beh_evidence.setdefault(e.behavior_id, e)
    timeline, related, iocs = [], {}, {}
    for r in relations:
        sub, obj = entities[r.subject_id], entities[r.object_id]
        ev = rel_evidence.get(r.id)
        doc = docs.get(ev.document_id) if ev else None
        date = r.source_first_seen_at or (doc.published_at if doc else None) or r.first_seen_at
        other = obj if r.subject_id == entity_id else sub
        if r.status == 'ACTIVE' and not r.negated:
            related[other.id] = {'type': other.type, 'value': other.canonical_name, 'confidence': r.confidence, 'relation': r.relation_type}
            if other.type == 'OBSERVABLE':
                iocs[other.id] = related[other.id]
        timeline.append({'type': 'relation', 'date': iso_date(date), 'date_basis': 'source' if r.source_first_seen_at or (doc and doc.published_at) else 'ingestion',
            'status': r.status, 'review_required': r.review_required,
            'description': f"{sub.canonical_name} {'does not ' if r.negated else ''}{r.relation_type} {obj.canonical_name}",
            'confidence': r.confidence, 'evidence': ev.snippet if ev else None, 'source_name': doc.source.name if doc else 'Unknown',
            'source_url': doc.url if doc else None, 'document_id': str(doc.id) if doc else None})
    for b in behaviors:
        doc, ev = docs.get(b.document_id), beh_evidence.get(b.id)
        timeline.append({'type': 'behavior', 'date': iso_date(doc.published_at or doc.first_seen_at) if doc else None,
            'date_basis': 'source' if doc and doc.published_at else 'ingestion', 'status': 'OBSERVED',
            'description': b.description, 'mitre_attack_id': b.mitre_attack_id, 'confidence': b.confidence,
            'evidence': ev.snippet if ev else None, 'source_name': doc.source.name if doc else 'Unknown',
            'source_url': doc.url if doc else None, 'document_id': str(doc.id) if doc else None})
    for t in events:
        doc = docs.get(t.document_id)
        timeline.append({'type': 'temporal', 'date': t.time, 'date_basis': 'extracted', 'status': t.type,
            'description': t.event, 'confidence': t.confidence, 'evidence': (t.evidence or {}).get('text'),
            'source_name': doc.source.name if doc else 'Unknown', 'source_url': doc.url if doc else None,
            'document_id': str(doc.id) if doc else None})
    timeline.sort(key=lambda item: item['date'] or '', reverse=True)
    return {'entity': entity.canonical_name, 'type': entity.type, 'first_seen': iso_date(entity.first_seen_at),
            'context': next((e['evidence'] for e in timeline if e.get('evidence')), 'No supporting source sentence is available for this legacy entity.'),
            'related': list(related.values()), 'iocs': list(iocs.values()), 'timeline': timeline[:100]}


def csv_response(rows, filename):
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            # Prevent spreadsheet applications treating source text as executable formulas.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k, v in row.items()})
    return Response('\ufeff' + buffer.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@router.get('/exports/{kind}')
def export_report(kind: str, db: Session = Depends(get_db)):
    if kind == 'entities':
        return csv_response(_entity_rows(db, db.query(Entity).order_by(Entity.canonical_name).all()), 'openthreat-entities.csv')
    if kind == 'feed':
        rows = []
        for c in db.query(IntelligenceChange).order_by(IntelligenceChange.timestamp.desc()).all():
            rows.append({'id': str(c.id), 'timestamp': iso_date(c.timestamp), 'entity_type': c.entity_type,
                         'entity_id': str(c.entity_id), 'change_type': c.change_type, 'reason': c.reason or '',
                         'document_id': str(c.document_id) if c.document_id else ''})
        return csv_response(rows, 'openthreat-intelligence.csv')
    entities = db.query(Entity).all()
    relations = db.query(Relation).all()
    if kind == 'graph':
        content = {'nodes': [entity_dict(e) for e in entities], 'links': [
            {'id': str(r.id), 'source': str(r.subject_id), 'target': str(r.object_id), 'relation': r.relation_type,
             'negated': r.negated, 'status': r.status, 'confidence': r.confidence, 'review_required': r.review_required}
            for r in relations]}
    elif kind == 'stix':
        stamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        mapping = {'THREAT_ACTOR': 'threat-actor', 'MALWARE': 'malware', 'TOOL': 'tool', 'VULNERABILITY': 'vulnerability',
                   'ORGANIZATION': 'identity', 'TECHNIQUE': 'attack-pattern'}
        objects, ids = [], {}
        for e in entities:
            kind_name = mapping.get(e.type)
            if not kind_name:
                continue
            object_id = f'{kind_name}--{e.id}'
            ids[e.id] = object_id
            obj = {'type': kind_name, 'spec_version': '2.1', 'id': object_id, 'created': stamp, 'modified': stamp,
                   'name': e.canonical_name, 'confidence': round(e.confidence * 100)}
            if e.type == 'MALWARE':
                obj['is_family'] = True
            if e.type == 'ORGANIZATION':
                obj['identity_class'] = 'organization'
            if e.type == 'TECHNIQUE' and e.canonical_name.startswith('T'):
                obj['external_references'] = [{'source_name': 'mitre-attack', 'external_id': e.canonical_name}]
            objects.append(obj)
        for r in relations:
            if r.status != 'ACTIVE' or r.negated or r.review_required or r.subject_id not in ids or r.object_id not in ids:
                continue
            objects.append({'type': 'relationship', 'spec_version': '2.1', 'id': f'relationship--{r.id}',
                'created': stamp, 'modified': stamp, 'relationship_type': {'DEPLOYS': 'uses'}.get(r.relation_type, r.relation_type.lower().replace('_', '-')),
                'source_ref': ids[r.subject_id], 'target_ref': ids[r.object_id], 'confidence': round(r.confidence * 100)})
        content = {'type': 'bundle', 'id': f'bundle--{uuid.uuid4()}', 'objects': objects}
    else:
        raise HTTPException(404, 'Unknown export format.')
    return Response(json.dumps(content, indent=2), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="openthreat-{kind}.json"'})
