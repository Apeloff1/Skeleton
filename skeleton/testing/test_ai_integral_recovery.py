"""Production audit/SQL recovery proof: no model reruns or silent repair."""
from __future__ import annotations
from contextlib import contextmanager
import sqlite3
from types import SimpleNamespace
import unittest
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
from skeleton.ai.runtime.operational_ai.authority.identity import Actor
from skeleton.ai.runtime.operational_ai.persistence.journal import EventJournal,JournalError
from skeleton.ai.runtime.operational_ai.orchestration.recovery import inspect,reconcile

A='a'*64
B='b'*64
C='c'*64


class FixtureAuthority:
    def __init__(self):
        self._db=sqlite3.connect(':memory:')
        self._db.execute('CREATE TABLE offline_turns (session_id TEXT, request_id TEXT, request_digest TEXT, output_digest TEXT, revision INTEGER)')
    @contextmanager
    def read_snapshot(self):
        yield
    def load(self,session,model_digest,tokenizer_digest):
        if (model_digest,tokenizer_digest)!=(A,B):
            raise ContractViolation('bad model')
        rows=self._db.execute('SELECT COUNT(*) FROM offline_turns WHERE session_id=?',(session,)).fetchone()
        return SimpleNamespace(revision=rows[0])
    def insert(self,request_id,revision,request_digest=B,output_digest=C):
        self._db.execute('INSERT INTO offline_turns VALUES (?,?,?,?,?)',
                         ('s_1',request_id,request_digest,output_digest,revision))
    def close(self):self._db.close()


class TestIntegralRecovery(unittest.TestCase):
    def setUp(self):
        self.store=FixtureAuthority()
        self.journal=EventJournal()
        self.s=SimpleNamespace(store=self.store,journal=self.journal,
                               actor=Actor('tenant','user',A,B))
        self.store.insert('r_1',1)
    def tearDown(self):
        self.store.close()
        self.journal.close()
    def audit(self,request_id='r_1',**overrides):
        payload={'request_id':request_id,'request_digest':B,'output_digest':C,
                 'revision':1,'model_digest':A}
        payload.update(overrides)
        return self.journal.append(stream='s_1',event_id='ai_turn_'+request_id,
                                   kind='ai.turn.committed',payload=payload)

    def test_missing_audit_detected_without_model_call(self):
        report=inspect(self.s,'s_1')
        self.assertEqual(report.missing_audits,1)
        self.assertEqual(report.status,'audit-incomplete')
        self.assertEqual(self.journal.head('s_1')[0],0)

    def test_operator_repair_only_missing_audit(self):
        result=reconcile(self.s,'s_1',approved=True)
        self.assertEqual(result.status,'verified')
        self.assertEqual(self.journal.head('s_1')[0],1)
        self.assertEqual(self.journal.replay('s_1')[0].payload['output_digest'],C)

    def test_repair_is_idempotent_without_duplicate_record(self):
        self.assertEqual(reconcile(self.s,'s_1',approved=True).status,'verified')
        self.assertEqual(reconcile(self.s,'s_1',approved=True).status,'verified')
        self.assertEqual(self.journal.head('s_1')[0],1)

    def test_approval_is_mandatory(self):
        with self.assertRaisesRegex(ContractViolation,'approval'):
            reconcile(self.s,'s_1')
        self.assertEqual(self.journal.head('s_1')[0],0)

    def test_conflicting_digest_refuses_repair(self):
        self.audit(output_digest='d'*64)
        with self.assertRaisesRegex(ContractViolation,'disagree'):
            reconcile(self.s,'s_1',approved=True)
        self.assertEqual(self.journal.head('s_1')[0],1)

    def test_conflicting_request_identity_refuses(self):
        self.audit(request_digest='d'*64)
        with self.assertRaisesRegex(ContractViolation,'disagree'):
            inspect(self.s,'s_1')

    def test_phantom_audit_refuses_backfill(self):
        self.audit('missing')
        with self.assertRaisesRegex(ContractViolation,'absent'):
            reconcile(self.s,'s_1',approved=True)

    def test_wrong_event_id_refuses_backfill(self):
        self.journal.append(stream='s_1',event_id='wrong',kind='ai.turn.committed',
                            payload={'request_id':'r_1'})
        with self.assertRaisesRegex(ContractViolation,'noncanonical'):
            inspect(self.s,'s_1')

    def test_missing_authoritative_turn_sequence_refused(self):
        self.store.insert('r_2',3)
        with self.assertRaisesRegex(ContractViolation,'corruption'):
            reconcile(self.s,'s_1',approved=True)

    def test_invalid_request_digest_refused(self):
        self.store._db.execute('UPDATE offline_turns SET request_digest=?',('wrong',))
        with self.assertRaisesRegex(ContractViolation,'corruption'):
            inspect(self.s,'s_1')

    def test_audit_chain_mutation_blocks_repair(self):
        self.audit()
        self.journal._db.execute('UPDATE ai_events SET payload=?', (b'{}',))
        with self.assertRaises(JournalError):
            reconcile(self.s,'s_1',approved=True)

    def test_bounded_repair_maximum(self):
        self.store.insert('r_2',2)
        with self.assertRaisesRegex(ContractViolation,'too many'):
            reconcile(self.s,'s_1',approved=True,maximum_missing=1)
        self.assertEqual(self.journal.head('s_1')[0],0)

    def test_tampered_revision_does_not_count_as_covered(self):
        self.audit(revision=2)
        with self.assertRaisesRegex(ContractViolation,'disagree'):
            inspect(self.s,'s_1')

    def test_more_than_one_turn_reconciles_in_order(self):
        self.store.insert('r_2',2)
        self.store.insert('r_3',3)
        result=reconcile(self.s,'s_1',approved=True)
        self.assertEqual(result.missing_audits,0)
        self.assertEqual(self.journal.head('s_1')[0],3)
        self.assertEqual([x.payload['revision'] for x in self.journal.replay('s_1')],[1,2,3])

if __name__=='__main__':unittest.main()
