"""source_retrieval: source-only receipt determinism, negative fingerprints and schema."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.source_retrieval.registry import (
    STAGES, STAGE_TYPES, contracts,
)

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys

class ReplayTests(unittest.TestCase):
    def test_canonical_source_digest_ignores_mapping_insertion_order(self):
        source = successful_evidence(STAGE_TYPES)
        first = evaluate_domain("source_retrieval", source).to_record()
        reversed_source = dict(reversed(tuple(source.items())))
        self.assertEqual(first, evaluate_domain("source_retrieval", reversed_source).to_record())

    def test_single_stage_mutations_change_diagnostic_fingerprint(self):
        good = evaluate_domain("source_retrieval", successful_evidence(STAGE_TYPES))
        for label, sample in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=label):
                bad = evaluate_domain("source_retrieval", sample)
                self.assertFalse(bad.accepted)
                self.assertNotEqual(good.evidence_sha256, bad.evidence_sha256)

    def test_declared_contracts_are_exact_and_unprivileged(self):
        docs = contracts()
        self.assertEqual(len(docs), len(STAGES))
        for doc,(label,kind) in zip(docs,STAGE_TYPES):
            with self.subTest(stage=label):
                self.assertEqual(doc["domain"], "source_retrieval")
                self.assertEqual(doc["stage"], label)
                self.assertEqual(doc["predicate"], kind)
                self.assertEqual(doc["required_fields"], list(required_keys(kind,label)))
                self.assertIs(doc["device_qualified"], False)
                self.assertIs(doc["operator_proof_is_insufficient_for_activation"], True)
