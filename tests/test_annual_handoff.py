"""Cross-plane provenance under half-year and yearly production restarts."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from skeleton.automation.annual_production import AnnualProductionStore,ProductionConflict
from skeleton.automation.annual_handoff import AnnualHandoffLedger

D=lambda s:sha256(s.encode()).hexdigest()
T0=1_800_000_000.0
DAY=86400.0


class AnnualHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=AnnualProductionStore(Path(self.temp.name)/"handoff.db")
        for name in ("dragon","jeeves","builder"):
            self.db.enroll(production_id=name,system=name,horizon_days=366,
                objective_digest=D("plan-"+name),
                authority_digest=D("authorized-"+name),
                authority_expires_at=T0+600*DAY,now=T0)
        self.h=AnnualHandoffLedger(self.db)

    def tearDown(self):self.temp.cleanup()

    def checkpoint(self, system, sequence=1, now=T0+2):
        self.token=self.db.claim(system,worker="worker",now=now-1,
            authority_digest=D("authorized-"+system))
        return self.db.checkpoint(self.token,sequence=sequence,now=now,
            state_digest=D(system+"-state-"+str(sequence)),
            evidence_digest=D(system+"-evidence-"+str(sequence)))

    def send(self, source="dragon", target="jeeves",receipt=None,
             seq=1,now=T0+3, verifier=None):
        return self.h.handoff(source_id=source,target_id=target,
            source_sequence=seq,
            source_receipt_digest=receipt if receipt is not None
                else self.db.read(source).last_receipt_digest,
            review_evidence_digest=D("reviewed-source"),
            now=now,verify_review=verifier or (lambda *_:True))

    def test_dragon_to_jeeves_handoff_persists_a_reviewed_source(self):
        self.checkpoint("dragon")
        result=self.send()
        self.assertEqual(result.source_system,"dragon")
        self.assertEqual(result.target_system,"jeeves")
        self.assertEqual(self.h.verify("dragon","jeeves"),1)
        self.assertEqual(AnnualHandoffLedger(AnnualProductionStore(self.db.path))
                         .list_for("jeeves")[0],result)

    def test_jeeves_to_builder_handoff_preserves_canon_digest(self):
        self.checkpoint("jeeves")
        result=self.send("jeeves","builder")
        self.assertEqual(result.target_objective_digest,D("plan-builder"))
        self.assertEqual(result.source_receipt_digest,
                         self.db.read("jeeves").last_receipt_digest)

    def test_cross_domain_handoff_cannot_replace_canonical_worker_permission(self):
        self.checkpoint("dragon")
        self.send()
        # Receiving a source digest does not create a Jeeves worker lease
        self.assertEqual(self.db.read("jeeves").sequence,0)
        self.assertEqual(self.db.read("jeeves").status,"queued")

    def test_external_review_rejection_fails_closed(self):
        self.checkpoint("dragon")
        with self.assertRaises(PermissionError):
            self.send(verifier=lambda *_:False)
        self.assertEqual(self.h.list_for("jeeves"),())

    def test_repeated_same_checkpoint_is_idempotent(self):
        self.checkpoint("dragon")
        original=self.send()
        self.assertEqual(self.send(),original)
        self.assertEqual(self.h.verify("dragon","jeeves"),1)

    def test_stale_source_checkpoint_cannot_be_handed_to_next_lane(self):
        first=self.checkpoint("dragon")
        self.db.release(self.token,now=T0+3,retry_seconds=0)
        self.checkpoint("dragon",sequence=2,now=T0+5)
        with self.assertRaises(ProductionConflict):
            self.send(receipt=first)
        result=self.send(seq=2,now=T0+6)
        self.assertEqual(result.source_sequence,2)

    def test_sequential_handoffs_form_a_verifiable_digest_chain(self):
        self.checkpoint("dragon")
        first=self.send()
        self.db.release(self.token,now=T0+4,retry_seconds=0)
        self.checkpoint("dragon",sequence=2,now=T0+6)
        second=self.send(seq=2,now=T0+7)
        self.assertEqual(second.previous_handoff_digest,first.handoff_digest)
        self.assertEqual(self.h.verify("dragon","jeeves"),2)

    def test_sqlite_receipt_corruption_is_detected(self):
        self.checkpoint("dragon")
        self.send()
        with sqlite3.connect(self.db.path) as conn:
            conn.execute("UPDATE annual_handoffs SET review_evidence_digest=?",
                         (D("forged"),))
        with self.assertRaises(ProductionConflict):
            self.h.verify("dragon","jeeves")

    def test_same_domain_handoff_is_not_permitted(self):
        self.checkpoint("dragon")
        with self.assertRaises(ValueError):
            self.send("dragon","dragon")
        # Source and target are different IDs but represent the same system
        self.db.enroll(production_id="dragon-2",system="dragon",horizon_days=183,
                       objective_digest=D("plan"),authority_digest=D("grant"),
                       authority_expires_at=T0+300*DAY,now=T0)
        with self.assertRaises(ProductionConflict):
            self.send("dragon","dragon-2")

    def test_unstarted_source_has_no_provenance_to_transfer(self):
        with self.assertRaises(ProductionConflict):
            self.send(receipt=D("forged"))

    def test_terminal_destination_cannot_accept_new_canon_handoff(self):
        self.checkpoint("dragon")
        self.checkpoint("jeeves")
        self.db.terminal(self.token,state="completed",
            verified_evidence_digest=D("complete"),now=T0+3)
        with self.assertRaises(ProductionConflict):
            self.send(now=T0+4)

    def test_paged_handoffs_have_bounded_memory_and_scope(self):
        self.checkpoint("dragon")
        self.send()
        self.assertEqual(len(self.h.list_for("jeeves",limit=1)),1)
        with self.assertRaises(ValueError):self.h.list_for("jeeves",limit=1000)
        self.assertEqual(self.h.list_for("builder"),())


if __name__=="__main__":unittest.main()
