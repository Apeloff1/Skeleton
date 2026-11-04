"""Real SQLite/FTS5 acceptance for an authenticated offline AI evidence plane.

Fixture native models prove only boundary behavior. No model quality or device
qualification is inferred from these tests.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity,SpineLimits,SpineError,Conflict)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.context.knowledge_plane import (
    KnowledgePlane,KnowledgePolicy,KnowledgeError)
from skeleton.ai.runtime.operational_ai.context.knowledge_plane import (
    chunks,decode,query,events,readiness,schema,provider)
from skeleton.ai.runtime.operational_ai.context.knowledge_plane.path_guard import read_source
from skeleton.ai.runtime.operational_ai.context.knowledge_plane.cli import main as cli
from skeleton.ai.runtime.operational_ai.deployment.boot.identity import (
    PrincipalBinding,establish_binding)

M='a'*64
T='b'*64

class Native:
    model_digest=M;tokenizer_digest=T
    def __init__(self):self.calls=0;self.messages=[]
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1;self.messages.append(messages)
        text='A deterministic native fixture output.'
        return Generated(text,55,8,hashlib.sha256(text.encode()).hexdigest(),M,T,'stop')


class KnowledgeAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ai-knowledge-',dir=Path.home())
        self.root=Path(self.tmp.name)
        self.state=self.root/'state';self.state.mkdir(mode=0o700)
        self.source=self.root/'source';self.source.mkdir(mode=0o700)
        self.identity=Identity('org','human',M,T)
        establish_binding(self.state,PrincipalBinding('org','human',M,T))
        self.db=SpineDatabase(self.state)
        self.policy=KnowledgePolicy(max_document_bytes=32768,max_total_bytes=200000,
            max_documents=16,max_chunks=128,chunk_characters=160,chunk_overlap=20,
            max_hits=4,max_query_terms=5,max_scan_rows=1000)
        self.plane=KnowledgePlane(self.db,self.identity,policy=self.policy)

    def tearDown(self):
        self.db.close();self.tmp.cleanup()

    def add(self,doc='guide',text='The lighthouse saves ships in the harbor.\nThe harbor is safe.',
            rev=0,title='Local guide'):
        return self.plane.admit_bytes_for_tests(text.encode('utf8'),doc_id=doc,
            title=title,rights='operator-authored',approved=True,
            expected_revision=rev)

    def test_empty_search_and_doctor(self):
        self.assertEqual(self.plane.search('lighthouse harbor'),())
        x=self.plane.doctor()
        self.assertEqual(x['status'],'source-custody-verified-not-answer-truth')
        self.assertEqual(x['proof']['revisions'],0)

    def test_ingest_and_retrieve_exact_bytes(self):
        record=self.add()
        self.assertEqual(record['revision'],1)
        hits=self.plane.search('lighthouse harbor',include_text=True)
        self.assertTrue(hits)
        self.assertIn('lighthouse',hits[0]['passage'])
        self.assertEqual(hits[0]['document_sha256'],record['document_sha256'])
        self.assertEqual(self.plane.doctor()['proof']['active_documents'],1)

    def test_provider_produces_native_context_evidence(self):
        self.add()
        items=self.plane.evidence_provider()(self.identity,'harbor lighthouse')
        self.assertTrue(items)
        self.assertEqual(items[0].owner_subject,'human')
        self.assertEqual(items[0].document_sha256,self.plane.list()[0]['document_sha256'])

    def test_provider_refuses_cross_model_or_tenant(self):
        self.add()
        for identity in (Identity('other','human',M,T),Identity('org','other',M,T),
                         Identity('org','human','c'*64,T)):
            with self.subTest(identity=identity),self.assertRaises(KnowledgeError):
                self.plane.evidence_provider()(identity,'lighthouse')

    def test_source_ids_are_unique_and_bounded(self):
        self.add()
        sources=self.plane.search('lighthouse harbor',include_text=True)
        self.assertEqual(len({x['source_id'] for x in sources}),len(sources))
        self.assertTrue(all(1<len(x['source_id'])<=128 for x in sources))

    def test_revisions_shadow_old_fts_hits(self):
        first=self.add(text='Tungsten is a metal.')
        second=self.add(rev=1,text='Iridium is a noble metal.')
        self.assertEqual(first['revision'],1)
        self.assertEqual(second['revision'],2)
        self.assertFalse(self.plane.search('Tungsten'))
        self.assertTrue(self.plane.search('Iridium'))
        self.assertEqual(len(self.plane.list()),1)
        self.assertEqual(self.plane.doctor()['proof']['revisions'],2)

    def test_idempotent_retry_does_not_write_event(self):
        self.add()
        first=self.plane.doctor()['proof']['mutation_events']
        duplicate=self.add(rev=0)
        self.assertTrue(duplicate['replayed'])
        self.assertEqual(self.plane.doctor()['proof']['mutation_events'],first)
        self.assertEqual(self.plane.list()[0]['revision'],1)

    def test_same_bytes_changed_rights_requires_revision(self):
        self.add()
        with self.assertRaises(KnowledgeError):
            self.plane.admit_bytes_for_tests(b'The lighthouse saves ships in the harbor.\nThe harbor is safe.',
                    doc_id='guide',title='Local guide',rights='public-domain',
                    approved=True,expected_revision=0)

    def test_reject_missing_approval_before_writes(self):
        with self.assertRaisesRegex(KnowledgeError,'approval'):
            self.plane.admit_bytes_for_tests(b'private',doc_id='guide',
                    title='Guide',approved=False)
        self.assertEqual(self.plane.list(),())

    def test_wrong_revision_does_not_replace(self):
        self.add()
        with self.assertRaisesRegex(KnowledgeError,'revision'):
            self.add(rev=0,text='The source changed')
        self.assertEqual(self.plane.list()[0]['revision'],1)

    def test_forget_is_not_premature_and_is_idempotent(self):
        self.add()
        with self.assertRaises(KnowledgeError):self.plane.forget('guide',expected_revision=1)
        with self.assertRaises(KnowledgeError):self.plane.forget('guide',expected_revision=9,approved=True)
        self.assertTrue(self.plane.forget('guide',expected_revision=1,approved=True))
        self.assertFalse(self.plane.forget('guide',expected_revision=1,approved=True))
        self.assertFalse(self.plane.search('lighthouse'))
        self.assertEqual(self.plane.list(),())
        self.assertEqual(self.plane.doctor()['proof']['mutation_events'],2)

    def test_reingest_after_forget_requires_last_revision(self):
        self.add();self.plane.forget('guide',expected_revision=1,approved=True)
        new=self.add(rev=1,text='The moon has craters')
        self.assertEqual(new['revision'],2)
        self.assertTrue(self.plane.search('craters'))

    def test_conflicting_one_active_revision_detected_by_constraint(self):
        self.add()
        with self.db.transaction() as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('UPDATE ai_kb_documents SET active=1 WHERE 0') if False else c.execute(
                    'INSERT INTO ai_kb_documents SELECT principal,doc_id,revision+1,title,rights,'
                    'content_type,raw_sha256,normalized_sha256,raw_bytes,normalized_bytes,chunks,'
                    'active,deleted,created_ns FROM ai_kb_documents WHERE principal=?',
                    (self.identity.key(),))

    def test_readonly_db_can_query_after_schema_install(self):
        self.add()
        with SpineDatabase(self.state,readonly=True) as db:
            kb=KnowledgePlane(db,self.identity,initialize=False)
            self.assertTrue(kb.search('harbor'))
            self.assertEqual(kb.doctor()['proof']['active_documents'],1)

    def test_no_silent_readonly_schema_creation(self):
        with self.db.transaction() as c:
            c.execute("DELETE FROM controls WHERE control='ai_knowledge_schema'")
        with self.assertRaises(KnowledgeError):
            KnowledgePlane(self.db,self.identity,initialize=False)

    def test_legacy_schema_version_fails_closed(self):
        with self.db.transaction() as c:
            c.execute("UPDATE controls SET value='2' WHERE control='ai_knowledge_schema'")
        with self.assertRaises(KnowledgeError):
            KnowledgePlane(self.db,self.identity,initialize=False)

    def test_normalized_line_endings_are_honest(self):
        self.plane.admit_bytes_for_tests(b'Neptune\r\nhas clouds\r',doc_id='guide',
            title='Planets',approved=True)
        x=self.plane.search('Neptune',include_text=True)[0]
        self.assertEqual(x['passage'],'Neptune\nhas clouds\n')
        self.assertEqual(x['char_end'],len(x['passage']))
        self.plane.doctor()

    def test_fts_injection_is_quoted_as_data(self):
        self.add()
        for q in ('NEAR(lighthouse,harbor)', '" OR *', 'harbor NOT lighthouse',
                  'lighthouse) ) OR (*)', '+++', 'lighthouse:*'):
            with self.subTest(q=q):
                self.plane.search(q)
        self.assertIn('"near"',query.fts_expression('NEAR(lighthouse,harbor)',self.policy))

    def test_invalid_query_budget(self):
        for invalid in ('', '\x00 test', 'x'*5000):
            with self.subTest(q=invalid[:20]), self.assertRaises(KnowledgeError):
                self.plane.search(invalid)

    def test_search_return_limit(self):
        for i in range(7):self.add(doc='d'+str(i),text='Harbor lighthouse is useful for boats')
        self.assertLessEqual(len(self.plane.search('Harbor lighthouse',limit=3)),3)
        with self.assertRaises(KnowledgeError):self.plane.search('harbor',limit=5)

    def test_mutated_passage_hash_refused(self):
        self.add()
        with self.db.transaction() as c:
            c.execute("UPDATE ai_kb_chunks SET passage='unverified replacement'")
        with self.assertRaises(KnowledgeError):self.plane.search('unverified')
        with self.assertRaises(KnowledgeError):self.plane.doctor()

    def test_deleted_chunk_refused_by_doctor(self):
        self.add()
        with self.db.transaction() as c:c.execute('DELETE FROM ai_kb_chunks')
        with self.assertRaises(KnowledgeError):self.plane.doctor()

    def test_tampered_event_refused(self):
        self.add()
        with self.db.transaction() as c:
            c.execute("UPDATE ai_kb_events SET event_json=?",(b'{}',))
        with self.assertRaises(KnowledgeError):self.plane.doctor()
        with self.assertRaises(KnowledgeError):self.add(doc='second',text='another document')

    def test_missing_audit_outbox_refused(self):
        self.add()
        with self.db.transaction() as c:
            c.execute("DELETE FROM outbox WHERE kind='ai_knowledge'")
        with self.assertRaises(KnowledgeError):self.plane.doctor()

    def test_forged_cross_subject_search_is_empty(self):
        self.add()
        other=Identity('org','stranger',M,T)
        with self.db.snapshot() as c:
            from skeleton.ai.runtime.operational_ai.context.knowledge_plane.search import search
            self.assertFalse(search(c,other,'lighthouse',limit=2,policy=self.policy))

    def test_source_file_rejects_symlink_and_hardlink(self):
        p=self.source/'notes.txt';p.write_text('lighthouse',encoding='utf8')
        (self.source/'link.txt').symlink_to(p)
        with self.assertRaises(OSError):read_source(self.source,'link.txt',policy=self.policy)
        os.link(p,self.source/'hard.txt')
        with self.assertRaises(KnowledgeError):read_source(self.source,'hard.txt',policy=self.policy)

    def test_source_file_rejects_parent_symlink(self):
        (self.source/'nested').mkdir(mode=0o700)
        (self.source/'nested'/'test.md').write_text('lighthouse')
        (self.source/'alias').symlink_to(self.source/'nested',target_is_directory=True)
        with self.assertRaises(OSError):read_source(self.source,'alias/test.md',policy=self.policy)

    def test_source_file_rejects_escape_and_hidden(self):
        for name in ('../x','/etc/passwd','a//b','a/./b','a/../b','.hidden','a\\b','-q'):
            with self.subTest(name=name),self.assertRaises(KnowledgeError):
                read_source(self.source,name,policy=self.policy)

    def test_source_file_accepts_owned_relative(self):
        (self.source/'notes.txt').write_text('lighthouse',encoding='utf8')
        x=self.plane.admit_file(root=self.source,relative_path='notes.txt',
           doc_id='notes',title='Notes',rights='operator-authored',
           content_type='text/plain',approved=True,expected_revision=0)
        self.assertEqual(x['revision'],1)

    def test_source_file_too_big_rejected(self):
        (self.source/'huge.txt').write_bytes(b'a'*(self.policy.max_document_bytes+1))
        with self.assertRaises(KnowledgeError):read_source(self.source,'huge.txt',policy=self.policy)

    def test_document_rejects_binary_invalid_json_and_html(self):
        for raw,kind in ((b'GGUFjunk','text/plain'),(b'PK\x03\x04junk','text/plain'),
                         (b'\xff','text/plain'),(b'{}{}','application/json'),
                         (b'{"a":1,"a":2}','application/json'),(b'<html>hi','text/plain'),
                         (b'abc\x00def','text/plain')):
            with self.subTest(raw=raw),self.assertRaises(KnowledgeError):
                self.plane.admit_bytes_for_tests(raw,doc_id='source',title='Raw',
                      approved=True,content_type=kind)

    def test_split_coverage_and_digests(self):
        text=('alpha\nbeta gamma delta\n'*35)
        chunks_=chunks.split(text,self.policy)
        self.assertGreater(len(chunks_),2)
        self.assertEqual(chunks_[0].start,0)
        self.assertEqual(chunks_[-1].end,len(text))
        for x in chunks_:
            self.assertEqual(text[x.start:x.end],x.passage)
            self.assertEqual(hashlib.sha256(x.passage.encode()).hexdigest(),x.digest)

    def test_policy_rejects_overlapping_nonprogress(self):
        with self.assertRaises(KnowledgeError):
            KnowledgePolicy(chunk_characters=64,chunk_overlap=32)

    def test_doc_and_total_budget(self):
        p=KnowledgePolicy(max_document_bytes=1024,max_total_bytes=1024,
                          chunk_characters=128,chunk_overlap=16)
        kb=KnowledgePlane(self.db,self.identity,policy=p)
        kb.admit_bytes_for_tests(b'a'*1000,doc_id='one',title='A',approved=True)
        with self.assertRaises(KnowledgeError):
            kb.admit_bytes_for_tests(b'b'*1000,doc_id='two',title='B',approved=True)

    def test_retrieval_as_actual_spine_model_input(self):
        self.add(text='Orion uses stars for navigation.')
        locks=self.root/'locks';locks.mkdir(mode=0o700)
        with SessionGate(locks) as gate:
            model=Native()
            spine=ExecutionSpine(db=self.db,session_gate=gate,
                backend=model,identity=self.identity,
                limits=SpineLimits(context_tokens=4096,max_output_tokens=64),
                evidence_provider=self.plane.evidence_provider())
            spine.create('testchat')
            first=spine.turn('testchat','ask1','What is Orion navigation?')
            self.assertEqual(first['revision'],1)
            self.assertEqual(model.calls,1)
            self.assertTrue(any('Orion uses stars' in x['content'] for x in model.messages[0]))
            self.assertGreater(first['evidence_sources'],0)
            again=spine.replay('testchat','ask1','What is Orion navigation?')
            self.assertEqual(again['revision'],1)
            self.assertEqual(model.calls,1)

    def test_no_document_means_no_invented_citations(self):
        with self.db.snapshot() as c:
            from skeleton.ai.runtime.operational_ai.context.knowledge_plane.search import search
            self.assertEqual(search(c,self.identity,'nonsense',limit=2,policy=self.policy),())

    def test_cli_requires_actual_bound_state_identity(self):
        args=['--state-dir',str(self.state),'--tenant','org','--subject','other',
              '--model-sha256',M,'--tokenizer-sha256',T,'list']
        self.assertEqual(cli(args),2)

    def test_cli_read_only_doctor(self):
        self.add()
        args=['--state-dir',str(self.state),'--tenant','org','--subject','human',
              '--model-sha256',M,'--tokenizer-sha256',T,'doctor']
        self.assertEqual(cli(args),0)


    def test_ingest_retry_detects_existing_tamper(self):
        self.add()
        with self.db.transaction() as c:
            c.execute("UPDATE ai_kb_chunks SET passage='corrupted text'")
        with self.assertRaises(KnowledgeError):self.add(rev=1)

    def test_revision_update_cannot_hide_corrupt_previous_document(self):
        self.add()
        with self.db.transaction() as c:
            c.execute("UPDATE ai_kb_chunks SET passage='corrupted text'")
        with self.assertRaises(KnowledgeError):self.add(rev=1,text='Entirely new material')

    def test_forget_refuses_corrupt_active_document(self):
        self.add()
        with self.db.transaction() as c:
            c.execute("UPDATE ai_kb_chunks SET passage='corrupted text'")
        with self.assertRaises(KnowledgeError):
            self.plane.forget('guide',expected_revision=1,approved=True)
        self.assertEqual(self.plane.list()[0]['revision'],1)

    def test_sources_retracted_after_retrieval_cannot_commit(self):
        self.add(text='Orion pilot consults lighthouse signals.')
        locks=self.root/'locks';locks.mkdir(mode=0o700)
        class Revoker(Native):
            def generate(inner,messages,*,max_output_tokens,seed,temperature):
                self.plane.forget('guide',expected_revision=1,approved=True)
                return super(Revoker,inner).generate(messages,max_output_tokens=max_output_tokens,
                    seed=seed,temperature=temperature)
        with SessionGate(locks) as gate:
            model=Revoker()
            spine=ExecutionSpine(db=self.db,session_gate=gate,backend=model,
                identity=self.identity,limits=SpineLimits(context_tokens=4096,max_output_tokens=64),
                evidence_provider=self.plane.evidence_provider())
            spine.create('chat1')
            with self.assertRaises(KnowledgeError):
                spine.turn('chat1','req1','Explain Orion pilot lighthouse')
            self.assertEqual(model.calls,1)
            self.assertEqual(spine.history('chat1'),())
            with self.db.snapshot() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM turns').fetchone()[0],0)

    def test_source_freshness_accepts_still_active(self):
        self.add()
        from skeleton.ai.runtime.operational_ai.context.knowledge_plane.freshness import require_current
        evidence=self.plane.evidence_provider()(self.identity,'lighthouse')
        sources=tuple({'source_id':x.source_id,'revision':x.revision,
                 'sha256':x.sha256,'document_sha256':x.document_sha256,
                 'char_start':x.start,'char_end':x.end} for x in evidence)
        with self.db.transaction() as c:
            require_current(c,self.identity,sources,policy=self.policy)

    def test_source_freshness_refuses_forgery(self):
        self.add()
        from skeleton.ai.runtime.operational_ai.context.knowledge_plane.freshness import require_current
        evidence=self.plane.evidence_provider()(self.identity,'lighthouse')
        row={'source_id':evidence[0].source_id,'revision':evidence[0].revision,
                 'sha256':evidence[0].sha256,'document_sha256':evidence[0].document_sha256,
                 'char_start':evidence[0].start,'char_end':evidence[0].end}
        row['source_id']='kb_'+'a'*48
        with self.db.transaction() as c,self.assertRaises(KnowledgeError):
            require_current(c,self.identity,(row,),policy=self.policy)

    def test_batch_all_or_nothing_with_conflicting_revision(self):
        from skeleton.ai.runtime.operational_ai.context.knowledge_plane.batch import BatchItem
        (self.source/'a.md').write_text('Orion signals navigation.')
        (self.source/'b.md').write_text('Lighthouse harbor navigation.')
        batch=(BatchItem('a.md','a','A','operator-authored','text/markdown',0),
               BatchItem('b.md','b','B','operator-authored','text/markdown',1))
        with self.assertRaises(KnowledgeError):
            self.plane.ingest_many(source_root=self.source,items=batch,approved=True)
        self.assertEqual(self.plane.list(),())
        self.assertEqual(self.plane.doctor()['proof']['mutation_events'],0)

    def test_batch_accepts_multiple_independent_sources_atomically(self):
        from skeleton.ai.runtime.operational_ai.context.knowledge_plane.batch import BatchItem
        for name in ('a','b','c'):(self.source/(name+'.md')).write_text(name+' lighthouse harbor')
        batch=tuple(BatchItem(x+'.md',x,x,'operator-authored','text/markdown',0)
                    for x in ('a','b','c'))
        results=self.plane.ingest_many(source_root=self.source,items=batch,approved=True)
        self.assertEqual(len(results),3)
        self.assertEqual(self.plane.doctor()['proof']['mutation_events'],3)
        self.assertEqual(self.plane.doctor()['proof']['active_documents'],3)

    def test_batch_requires_approval_and_rejects_duplicates(self):
        from skeleton.ai.runtime.operational_ai.context.knowledge_plane.batch import BatchItem
        (self.source/'a.md').write_text('lighthouse')
        entry=BatchItem('a.md','a','A','operator-authored','text/markdown',0)
        with self.assertRaises(KnowledgeError):
            self.plane.ingest_many(source_root=self.source,items=(entry,),approved=False)
        with self.assertRaises(KnowledgeError):
            self.plane.ingest_many(source_root=self.source,items=(entry,entry),approved=True)

    def test_fts5_external_content_proof(self):
        self.add()
        self.assertEqual(self.plane.check_index()['status'],'fts5-content-index-verified')

    def test_index_rebuild_requires_approval_and_is_witnessed(self):
        self.add()
        with self.assertRaises(KnowledgeError):self.plane.rebuild_index(approved=False)
        result=self.plane.rebuild_index(approved=True)
        self.assertEqual(result['status'],'operator-approved-index-rebuilt')
        self.assertEqual(self.plane.doctor()['proof']['mutation_events'],2)
        self.assertTrue(self.plane.search('lighthouse'))

    def test_rebuild_never_accepts_corrupt_source_rows(self):
        self.add()
        with self.db.transaction() as c:
            c.execute("UPDATE ai_kb_chunks SET passage='corrupted'")
        with self.assertRaises(KnowledgeError):self.plane.rebuild_index(approved=True)

    def test_batch_overlong_fails_before_reading_all_files(self):
        from skeleton.ai.runtime.operational_ai.context.knowledge_plane.batch import BatchItem
        items=(BatchItem(f'{i}.md',f'd{i}','D','operator-authored','text/markdown',0)
               for i in range(18))
        with self.assertRaises(KnowledgeError):
            self.plane.ingest_many(source_root=self.source,items=items,approved=True,maximum=16)

    def test_doctor_catches_fts_event_chain_status_after_rebuild(self):
        self.add()
        self.plane.rebuild_index(approved=True)
        result=self.plane.doctor()
        self.assertEqual(result['proof']['mutation_events'],2)
        with self.db.transaction() as c:
            c.execute("DELETE FROM outbox WHERE kind='ai_knowledge' AND event_key IN "
                      "(SELECT event_key FROM outbox WHERE kind='ai_knowledge' ORDER BY sequence DESC LIMIT 1)")
        with self.assertRaises(KnowledgeError):self.plane.doctor()

    def test_startup_attaches_native_model_custodied_evidence_provider(self):
        from contextlib import nullcontext
        from skeleton.ai.runtime.operational_ai.deployment.production import startup
        from skeleton.ai.runtime.operational_ai.context.knowledge_plane.provider import KnowledgeEvidenceProvider
        self.add()
        with patch.object(startup,'load_approved_manifest',return_value=object()), \
             patch.object(startup,'activate_model',return_value=nullcontext(Native())):
            stack,supervised=startup.activate(model_root=self.source,state_dir=self.state,
                tenant='org',subject='human',n_ctx=4096,max_new_tokens=64)
            with stack:
                self.assertIsInstance(supervised.spine.evidence_provider,KnowledgeEvidenceProvider)
                supervised.spine.create('teststartup')
                result=supervised.spine.turn('teststartup','ask1','lighthouse harbor')
                self.assertGreater(result['evidence_sources'],0)

    def test_knowledge_readiness_requires_approved_corpus(self):
        first=readiness.inspect_readiness(self.plane,minimum_documents=1)
        self.assertEqual(first['status'],'insufficient-approved-sources')
        self.add()
        ready=readiness.inspect_readiness(self.plane,minimum_documents=1)
        self.assertEqual(ready['status'],'ready')
        self.assertEqual(ready['model_calls'],0)

    def test_source_root_symlink_refused(self):
        alias=self.root/'alias';alias.symlink_to(self.source,target_is_directory=True)
        with self.assertRaises(OSError):read_source(alias,'hello.md',policy=self.policy)

    def test_multi_process_reopen_preserves_fts_state(self):
        self.add()
        # Independent SQLite connection and a read-only schema attestation.
        with SpineDatabase(self.state,readonly=True) as separate:
            other=KnowledgePlane(separate,self.identity,initialize=False)
            hits=other.search('lighthouse')
            self.assertTrue(hits)
            self.assertEqual(other.doctor()['proof']['revisions'],1)

    def test_query_unicode_diacritics_is_data_only(self):
        self.add(doc='unicode',text='Café à la carte, naïve façade, Übergrün. Solstice.')
        hits=self.plane.search('café façade')
        self.assertTrue(hits)
        self.assertEqual(hits[0]['document_id'],'unicode')

    def test_freshness_refuses_removed_index_after_new_revision(self):
        self.add()
        from skeleton.ai.runtime.operational_ai.context.knowledge_plane.freshness import require_current
        evidence=self.plane.evidence_provider()(self.identity,'lighthouse')
        self.add(rev=1,text='The source now discusses only comets.')
        x=evidence[0]
        row={'source_id':x.source_id,'revision':x.revision,'sha256':x.sha256,
             'document_sha256':x.document_sha256,'char_start':x.start,'char_end':x.end}
        with self.db.transaction() as c,self.assertRaises(KnowledgeError):
            require_current(c,self.identity,(row,),policy=self.policy)


if __name__=='__main__':unittest.main()
