"""Cross-module historical evidence, provenance and training custody regressions."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.training.temporal_signals import TemporalSignalError
from skeleton.ai.training.bitemporal_authority import BitemporalFact, bitemporal_snapshot, require_no_future_knowledge
from skeleton.ai.training.temporal_facts import TemporalFact, snapshot_facts, require_historical_snapshot
from skeleton.ai.training.temporal_freshness import FactVersion, resolve_fact_versions
from skeleton.ai.training.temporal_provenance import ProvenanceNode, IndependenceReceipt, assess_source_independence, require_independent_roots
from skeleton.ai.training.temporal_custody import TemporalCustodyEntry, append_custody, build_custody_chain
from skeleton.ai.training.temporal_revocation import TemporalRevocation, RevocationRegistry
from skeleton.ai.training.temporal_quarantine import QuarantineItem, QuarantineResolution, quarantine, resolve_quarantine, require_learning_release
from skeleton.ai.training.temporal_replay import TemporalAuthorityEntry, TemporalAuthorityLedger

A, B, C, D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)


class TestTemporalEvidenceCustody(unittest.TestCase):
    def test_bitemporal_knowledge_cutoff(self):
        fact = BitemporalFact("fact", "system", "is", A, 2020, 2030, 2025, 2050, B)
        old = bitemporal_snapshot((fact,), world_year=2024, knowledge_year=2024)
        self.assertEqual(old.excluded_unknown, 1)
        self.assertEqual(old.fact_digests, ())
        current = bitemporal_snapshot((fact,), world_year=2025, knowledge_year=2025)
        self.assertEqual(current.fact_digests, (fact.digest,))
        self.assertEqual(require_no_future_knowledge(current), current.digest)

    def test_future_known_facts_cannot_authorize_past_snapshot(self):
        fact = BitemporalFact("fact", "system", "is", A, 2020, 2030, 2025, 2050, B)
        snapshot = bitemporal_snapshot((fact,), world_year=2024, knowledge_year=2025)
        with self.assertRaisesRegex(TemporalSignalError, "knowledge snapshot"):
            require_no_future_knowledge(snapshot)
        with self.assertRaises(TemporalSignalError):
            BitemporalFact("fact", "system", "is", A, True, 2030, 2025, 2050, B)

    def test_temporal_facts_hide_future_observations(self):
        fact = TemporalFact("fact", "system", "is", A, 2020, 2030, 2025, B)
        historical = snapshot_facts((fact,), as_of_year=2024)
        self.assertEqual(historical.excluded_future_count, 1)
        self.assertEqual(historical.fact_digests, ())
        self.assertEqual(require_historical_snapshot(historical, expected_year=2024), historical.digest)

    def test_freshness_versions_do_not_leak_future_and_reject_conflict(self):
        old = FactVersion("v1", "item", A, 2020, 2020, 2099, B)
        new = FactVersion("v2", "item", B, 2021, 2020, 2099, C)
        self.assertEqual(resolve_fact_versions((old, new), policy_year=2020).selected_digest, old.digest)
        self.assertEqual(resolve_fact_versions((old, new), policy_year=2021).selected_digest, new.digest)
        competing = FactVersion("v3", "item", C, 2021, 2020, 2099, D)
        with self.assertRaisesRegex(TemporalSignalError, "conflict"):
            resolve_fact_versions((old, new, competing), policy_year=2021)

    def test_malformed_fact_digest_and_year_rejected(self):
        with self.assertRaisesRegex(TemporalSignalError, "digest"):
            FactVersion("v", "item", "g" * 64, 2020, 2020, 2030, A)
        with self.assertRaisesRegex(TemporalSignalError, "year"):
            FactVersion("v", "item", B, True, 2020, 2030, A)

    def test_provenance_echoes_do_not_count_as_independent(self):
        receipt = assess_source_independence((
            ProvenanceNode(A), ProvenanceNode(B, (A,)), ProvenanceNode(C),
        ))
        self.assertEqual(receipt.independent_root_count, 2)
        self.assertGreater(receipt.echo_count, 0)
        self.assertEqual(require_independent_roots(receipt), receipt.digest)
        with self.assertRaisesRegex(TemporalSignalError, "count mismatch"):
            replace(receipt, independent_root_count=8)

    def test_provenance_cycles_fail_closed(self):
        with self.assertRaisesRegex(TemporalSignalError, "cycle"):
            assess_source_independence((ProvenanceNode(A, (B,)), ProvenanceNode(B, (A,))))
        with self.assertRaisesRegex(TemporalSignalError, "independent"):
            require_independent_roots(assess_source_independence((ProvenanceNode(A),)))

    def test_custody_chain_is_sequential_and_tamper_evident(self):
        first = append_custody((), artifact_digest=A, artifact_kind="fact", authority_id="reviewer")
        second = append_custody(first, artifact_digest=B, artifact_kind="certificate", authority_id="reviewer")
        receipt = build_custody_chain(second)
        self.assertEqual(receipt.length, 2)
        self.assertEqual(receipt.head_digest, second[-1].digest)
        with self.assertRaisesRegex(TemporalSignalError, "predecessor"):
            build_custody_chain((first[0], replace(second[-1], previous_digest=C)))
        with self.assertRaisesRegex(TemporalSignalError, "sequence"):
            replace(first[0], sequence=True)

    def test_revocation_is_epoch_scoped_and_monotone(self):
        item = TemporalRevocation(A, "certificate", 5, "evidence-invalidated", "auditor", B)
        registry = RevocationRegistry().revoke(item)
        self.assertTrue(registry.require_not_revoked(A, epoch=4))
        with self.assertRaisesRegex(TemporalSignalError, "revoked"):
            registry.require_not_revoked(A, epoch=5)
        with self.assertRaisesRegex(TemporalSignalError, "duplicate"):
            registry.revoke(item)
        with self.assertRaisesRegex(TemporalSignalError, "authority"):
            replace(item, epoch=True)

    def test_quarantine_requires_explicit_learning_release(self):
        item = quarantine(A, item_id="evidence-1", reason_code="future-leakage", admitted_year=2026, source_digest=B)
        held = resolve_quarantine(item, resolution="release-retrieval", evidence_digest=C, resolver_id="auditor")
        with self.assertRaisesRegex(TemporalSignalError, "learning"):
            require_learning_release(held)
        released = resolve_quarantine(item, resolution="release-learning", evidence_digest=C, resolver_id="auditor")
        self.assertEqual(require_learning_release(released), released.digest)

    def test_unverified_direct_quarantine_receipts_rejected(self):
        with self.assertRaisesRegex(TemporalSignalError, "digest"):
            QuarantineItem("e", "g" * 64, "future-leakage", 2026, B)
        with self.assertRaisesRegex(TemporalSignalError, "resolution"):
            QuarantineResolution(A, "promoted", B, "reviewer")
        with self.assertRaisesRegex(TemporalSignalError, "year"):
            quarantine(A, item_id="e", reason_code="future-leakage", admitted_year=True, source_digest=B)

    def test_ledger_roundtrip_blocks_replay_and_tampering(self):
        ledger = TemporalAuthorityLedger()
        first = ledger.append(A, "system", 2026)
        ledger.append(B, "system", 2027)
        restored = TemporalAuthorityLedger.restore(ledger.snapshot())
        self.assertEqual(restored.snapshot(), ledger.snapshot())
        self.assertEqual(first.sequence, 1)
        with self.assertRaisesRegex(TemporalSignalError, "replayed"):
            ledger.append(A, "system", 2028)
        before = ledger.snapshot()
        bad = ledger.snapshot()
        bad["entries"][0]["authority_digest"] = C
        self.assertEqual(ledger.snapshot(), before)
        with self.assertRaisesRegex(TemporalSignalError, "snapshot"):
            TemporalAuthorityLedger.restore(bad)

    def test_direct_ledger_receipts_require_digest_and_year(self):
        with self.assertRaisesRegex(TemporalSignalError, "digest"):
            TemporalAuthorityEntry(1, "bad", "system", 2026, None)
        with self.assertRaisesRegex(TemporalSignalError, "year"):
            TemporalAuthorityEntry(1, A, "system", True, None)


if __name__ == "__main__":
    unittest.main()
