import unittest
from dataclasses import replace

from skeleton.ai.evidence_memory import (
    EvidenceMemoryError,
    GenerationMemoryEvidence,
    admit_generation_memory,
)
from skeleton.ai.project_memory import ProjectMemory


D = "a" * 64


def evidence(**changes):
    values = dict(
        context_source_digest=D,
        context_text_digest="b" * 64,
        model_identity_digest="c" * 64,
        prompt_sequence_digest="d" * 64,
        runtime_request_digest="e" * 64,
        output_digest="f" * 64,
        replay_receipt_digest="1" * 64,
        generated_text="durable generated knowledge",
    )
    values.update(changes)
    return GenerationMemoryEvidence(**values)


class TestEvidenceGenerationMemory(unittest.TestCase):
    def memory(self):
        return ProjectMemory("tenant", "project", "generated-evidence")

    def test_completed_verified_generation_becomes_attributed_fact(self):
        updated, receipt = admit_generation_memory(
            self.memory(), evidence(), tenant_id="tenant", project_id="project"
        )
        self.assertEqual(len(updated.facts), 1)
        fact = updated.facts[0]
        self.assertEqual(fact.source_id, evidence().evidence_digest)
        self.assertEqual(receipt.fact_id, fact.fact_id)
        self.assertEqual(receipt.evidence_digest, evidence().evidence_digest)

    def test_failed_generation_cannot_be_constructed_as_memory_evidence(self):
        with self.assertRaises(EvidenceMemoryError):
            evidence(terminal_reason="model_error")

    def test_cross_project_and_cross_trust_writes_fail_closed(self):
        for project, trust in (("other", "generated-evidence"), ("project", "trusted-human")):
            with self.subTest(project=project, trust=trust):
                with self.assertRaises(EvidenceMemoryError):
                    admit_generation_memory(
                        self.memory(), evidence(), tenant_id="tenant",
                        project_id=project, trust_class=trust,
                    )

    def test_fact_identity_is_deterministic_and_append_only(self):
        memory = self.memory()
        first, receipt = admit_generation_memory(
            memory, evidence(), tenant_id="tenant", project_id="project"
        )
        with self.assertRaises(EvidenceMemoryError):
            admit_generation_memory(
                first, evidence(), tenant_id="tenant", project_id="project"
            )
        second, receipt2 = admit_generation_memory(
            first, evidence(generated_text="revised"),
            tenant_id="tenant", project_id="project", supersedes=receipt.fact_id,
        )
        self.assertEqual(len(second.visible("tenant", "project", "generated-evidence")), 1)
        self.assertNotEqual(receipt.fact_id, receipt2.fact_id)

    def test_unknown_supersession_target_fails_closed(self):
        with self.assertRaises(EvidenceMemoryError):
            admit_generation_memory(
                self.memory(), evidence(), tenant_id="tenant", project_id="project",
                supersedes="0" * 64,
            )

    def test_malformed_digest_and_unicode_fail_closed(self):
        with self.assertRaises(EvidenceMemoryError):
            evidence(output_digest="xyz")
        with self.assertRaises(EvidenceMemoryError):
            evidence(generated_text="bad\ud800")


if __name__ == "__main__":
    unittest.main()
