"""Regression coverage for provenance, transactional extraction and read performance.

Run: python -m unittest discover -s tests -v (from platform-service).
Uses a separate in-memory SQLite database; never touches the project database.
"""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from database.models import Base, Source, Document, Entity, Relation, Evidence, Behavior, TemporalEvent, IntelligenceChange
from novelty.engine import NoveltyEngine
from crud import crud
from core.dates import iso_date, parse_date
from api.intel import get_all_entities, export_report, get_entity_timeline, get_knowledge_graph
from api.upload import extract_file
from collectors.rss_collector import RSSCollector


class Reply:
    def __init__(self, decisions):
        self.decisions = decisions
    def raise_for_status(self):
        pass
    def json(self):
        return {'results': self.decisions}


class IntegrityTests(unittest.TestCase):
    def test_lifecycle_retains_clickable_report_source(self):
        self.doc.url = 'https://example.org/threat-report'
        self.process([{'status': 'NEW'}])
        actor = self.db.query(Entity).filter_by(canonical_name='APT28').one()
        timeline = get_entity_timeline(actor.id, self.db)
        self.assertEqual(timeline['timeline'][0]['source_url'], self.doc.url)
        self.assertEqual(timeline['timeline'][0]['document_id'], str(self.doc.id))

    def test_bounded_graph_keeps_both_ends_of_recent_relationships(self):
        self.process([{'status': 'NEW'}])
        self.db.add(Entity(canonical_name='Unconnected recent entity', type='TOOL', confidence=.9))
        self.db.flush()
        graph = get_knowledge_graph(self.db, limit=2)
        self.assertEqual(len(graph['nodes']), 2)
        self.assertEqual(len(graph['links']), 1)
        self.assertEqual({node['name'] for node in graph['nodes']}, {'APT28', 'Mimikatz'})

    def test_rss_article_excludes_sidebar_and_unrecognized_pages(self):
        collector = RSSCollector()
        text = collector._article_text('<p>Unrelated sidebar text about another incident.</p><article><p>APT28 used Mimikatz in this incident.</p><aside><p>Unrelated advertisement for other tools.</p></aside></article>')
        self.assertIn('APT28 used Mimikatz', text)
        self.assertNotIn('Unrelated', text)
        self.assertEqual(collector._article_text('<p>Only unrelated page navigation content.</p>'), '')

    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.source = Source(name='Test source', source_type='test')
        self.db.add(self.source)
        self.db.flush()
        self.doc = Document(source_id=self.source.id, title='Test report', content='APT28 used Mimikatz.',
                            content_hash='test', published_at=datetime(2024, 6, 20))
        self.db.add(self.doc)
        self.db.commit()
        self.db.info['defer_commit'] = True
        self.payload = {'entities': [
            {'canonical_name': 'APT28', 'mention': 'APT28', 'type': 'THREAT_ACTOR', 'confidence': .9, 'char_start': 0},
            {'canonical_name': 'Mimikatz', 'mention': 'Mimikatz', 'type': 'TOOL', 'confidence': .9, 'char_start': 11}],
            'relations': [{'subject': 'APT28', 'subject_type': 'THREAT_ACTOR', 'relation': 'USES',
                'object': 'Mimikatz', 'object_type': 'TOOL', 'negated': False, 'confidence': .8,
                'evidence': {'text': 'APT28 used Mimikatz.', 'char_start': 0, 'char_end': 19, 'page_number': 1}}]}

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def process(self, decisions, payload=None):
        with patch('novelty.engine.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value = Reply(decisions)
            NoveltyEngine(self.db).process_nlp_payload(self.doc.id, payload or self.payload, '2024-06-20T00:00:00Z')
            return client.return_value.__enter__.return_value.post.call_args.kwargs['json']

    def test_full_contract_and_known_evidence_are_preserved(self):
        request = self.process([{'status': 'NEW', 'reason': 'New fact'}])
        self.assertEqual(request['facts'][0]['evidence']['page_number'], 1)
        relation = self.db.query(Relation).one()
        self.db.commit()
        other = Document(source_id=self.source.id, title='Second source', content='Same fact', content_hash='two')
        self.db.add(other)
        self.db.commit()
        self.doc = other
        request = self.process([{'status': 'KNOWN', 'matched_fact_id': str(relation.id), 'reason': 'Repeated'}])
        self.assertEqual(request['candidates'][0]['first_seen_at'], '2024-06-20T00:00:00Z')
        self.assertFalse(request['candidates'][0]['negated'])
        self.assertEqual(self.db.query(Evidence).count(), 2)
        self.assertEqual(self.db.query(Relation).count(), 1)
        self.assertEqual(self.db.query(Evidence).first().char_start, 0)

    def test_negation_update_marks_prior_fact_historical(self):
        self.process([{'status': 'NEW'}])
        old = self.db.query(Relation).one()
        self.payload['relations'][0]['negated'] = True
        self.payload['relations'][0]['evidence']['text'] = 'APT28 no longer uses Mimikatz.'
        request = self.process([{'status': 'UPDATED', 'superseded_fact_ids': [str(old.id)]}])
        self.assertTrue(request['facts'][0]['negated'])
        self.assertEqual(old.status, 'HISTORICAL')
        self.assertTrue(self.db.query(Relation).filter_by(status='ACTIVE').one().negated)

    def test_nlp_failure_can_roll_back_all_extracted_intelligence(self):
        with patch('novelty.engine.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.side_effect = RuntimeError('Unavailable')
            with self.assertRaises(RuntimeError):
                NoveltyEngine(self.db).process_nlp_payload(self.doc.id, self.payload)
        self.db.rollback()
        self.assertEqual(self.db.query(Entity).count(), 0)
        self.assertEqual(self.db.query(Relation).count(), 0)
        self.assertEqual(self.db.query(Document).count(), 1)

    def test_ambiguous_behavior_is_not_assigned_to_first_actor(self):
        self.payload['entities'].append({'canonical_name': 'APT29', 'mention': 'APT29', 'type': 'THREAT_ACTOR',
                                         'confidence': .9, 'char_start': 5})
        self.payload['behaviors'] = [{'description': 'Several actors stole credentials.', 'mitre_attack_id': 'T1003',
            'confidence': .7, 'evidence': {'text': 'Several actors stole credentials.', 'char_start': 0, 'char_end': 40}}]
        self.process([{'status': 'NEW'}])
        self.assertIsNone(self.db.query(Behavior).one().entity_id)

    def test_temporal_events_and_uncertain_review_are_stored(self):
        self.payload['temporal_events'] = [{'entity': 'APT28', 'event': 'active since 2004', 'time': '2004',
            'type': 'ACTIVE', 'confidence': .8, 'evidence': {'text': 'APT28 active since 2004.'}}]
        self.process([{'status': 'UNCERTAIN', 'reason': 'Weak evidence'}])
        rel = self.db.query(Relation).one()
        self.assertEqual(rel.status, 'UNCERTAIN')
        self.assertTrue(rel.review_required)
        self.assertEqual(self.db.query(TemporalEvent).one().time, '2004')
        timeline = get_entity_timeline(rel.subject_id, self.db)
        self.assertTrue(any(e['date'] == '2004' for e in timeline['timeline']))

    def test_directory_query_count_does_not_grow_per_entity(self):
        for index in range(30):
            self.db.add(Entity(canonical_name=f'Actor {index}', type='THREAT_ACTOR', confidence=.8))
        self.db.commit()
        queries = []
        def capture(*args):
            queries.append(args[2])
        event.listen(self.engine, 'before_cursor_execute', capture)
        rows = get_all_entities(self.db, 100, 0, None)
        self.assertEqual(len(rows), 30)
        self.assertLessEqual(len(queries), 2)

    def test_document_version_preserves_prior_content_and_source_date(self):
        doc = crud.create_document(self.db, self.source.id, 'Original', 'Old content', 'old', external_id='versioned',
                                   published_at='Mon, 01 Jan 2024 12:00:00 GMT')
        crud.create_document(self.db, self.source.id, 'Updated', 'New content', 'new', external_id='versioned',
                             published_at='2024-06-20')
        self.assertEqual(doc.versions[0].content, 'Old content')
        self.assertEqual(doc.published_at, datetime(2024, 6, 20))

    def test_html_import_ignores_scripts_and_decodes_entities(self):
        text = extract_file('report.html', b'<p>APT28 &amp; APT29</p><script>fake report</script>')
        self.assertIn('APT28 & APT29', text)
        self.assertNotIn('fake report', text)
        with self.assertRaises(ValueError):
            extract_file('report.exe', b'binary')

    def test_stix_excludes_negation_and_uncertain_relations(self):
        self.process([{'status': 'UNCERTAIN'}])
        import json
        bundle = json.loads(export_report('stix', self.db).body)
        self.assertEqual(bundle['type'], 'bundle')
        self.assertFalse(any(o['type'] == 'relationship' for o in bundle['objects']))

    def test_rss_dates_are_normalized_and_missing_dates_stay_missing(self):
        self.assertEqual(iso_date('Mon, 01 Jan 2024 17:30:00 +0530'), '2024-01-01T12:00:00Z')
        self.assertIsNone(parse_date('not a date'))


if __name__ == '__main__':
    unittest.main()
