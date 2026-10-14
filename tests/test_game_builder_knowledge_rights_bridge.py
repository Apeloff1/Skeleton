"""Integration coverage for independent rights evidence and game research handoff."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import unittest

from skeleton.ai.game_builder.contracts import EvaluatorProvenance
from skeleton.ai.game_builder.knowledge_rights_bridge import (
    ResearchHandoffError,
    clear_research_for_design,
    require_cleared_research_current,
)
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument,
    ReviewedKnowledgeStore,
    ReviewedNote,
)
from skeleton.ai.game_builder.rights import (
    RightsLedger,
    RightsState,
    SimilarityFinding,
    SimilarityRisk,
    SourceRecord,
    UseKind,
)


SOURCE = "Jump timing should remain predictable."
SOURCE_DIGEST = sha256(SOURCE.encode()).hexdigest()
LICENSE_ID = "licensed-for-reference"
ARTIFACT_DIGEST = "a" * 64


def provenance(evidence: str = "e" * 64, evaluator_id: str = "independent-rights-reviewer"):
    return EvaluatorProvenance(
        evaluator_id=evaluator_id,
        operation_id="right-review",
        execution_id="rights-review-001",
        execution_identity_digest="1" * 64,
        finalization_intent_digest="2" * 64,
        authority_kind="deterministic_control",
        authority_identity_digest="3" * 64,
        method_id="source-license-review",
        source_revision="4" * 40,
        output_evidence_refs=(evidence,),
    )


def reviewed(source_id: str = "study-a", *, owner="studio-one",
             time="2026-10-08T12:00:00Z"):
    return ReviewedDocument(
        owner=owner, source_id=source_id,
        source_url="https://example.org/authorized-study",
        title="Reviewed jump timing", text=SOURCE, observed_at=time,
        license_id=LICENSE_ID,
        allowed_scopes=("design_reference", "research"),
        reviewer_id="human-1", approved=True,
        notes=(ReviewedNote(
            note_id="jump-a", mechanic="platforming",
            statement="Jump timing is predictable",
            start=0, end=len(SOURCE), stance="supports",
            confidence_ppm=900000, dependence_group="study-publisher",
            tags=("jump", "timing"),
        ),),
    )


def record(source_id: str = "study-a", *,
           digest=SOURCE_DIGEST, license_id=LICENSE_ID,
           state=RightsState.LICENSED_REUSE,
           allowed=frozenset({UseKind.FACTS_IDEAS_REFERENCE})):
    return SourceRecord(
        source_id=source_id,
        content_digest=digest,
        rights_state=state,
        allowed_uses=allowed,
        source_class="independent-gameplay-study",
        rights_authority=provenance(),
        rights_evidence_digest="e" * 64,
        license_id=license_id,
    )


class RightsBoundKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.store = ReviewedKnowledgeStore(":memory:")
        self.receipt = self.store.import_document(
            reviewed(), expected_parent_digest=None, authorized=True,
        )
        self.brief = self.store.build_brief("studio-one", "jump", authorized=True)
        self.rights = RightsLedger()
        self.rights.register_source(record())

    def tearDown(self):
        self.store.close()

    def clear(self, *, rights=None, brief=None, human_approved=True, authorized=True):
        return clear_research_for_design(
            self.store, brief or self.brief, rights or self.rights,
            project_id="platformer-project",
            artifact_digest=ARTIFACT_DIGEST,
            human_approved=human_approved,
            authorized=authorized,
        )

    def test_clears_first_party_rights_record_into_citable_design_context(self):
        packet = self.clear()
        self.assertEqual(packet.project_id, "platformer-project")
        self.assertEqual(packet.knowledge_root, self.brief.knowledge_root)
        self.assertEqual(len(packet.sources), 1)
        self.assertEqual(packet.sources[0].source_text_digest, SOURCE_DIGEST)
        self.assertEqual(packet.sources[0].rights_record_digest, record().rights_binding_digest)
        self.assertTrue(packet.human_approved)
        payload = packet.to_payload()
        self.assertEqual(payload["schema"], "skeleton.game_builder.cleared_research_packet.v1")
        self.assertFalse(payload["build_authority"])
        self.assertFalse(payload["training_authority"])
        self.assertFalse(payload["release_authority"])
        self.assertEqual(payload["citations"][0]["exact_quote"], SOURCE)
        self.assertEqual(len(payload["packet_digest"]), 64)
        require_cleared_research_current(packet, self.store, self.rights, authorized=True)

    def test_wrong_content_digest_rejected_before_ledger_mutation(self):
        ledger = RightsLedger()
        ledger.register_source(record(digest="0" * 64))
        with self.assertRaisesRegex(ResearchHandoffError, "digest"):
            self.clear(rights=ledger)
        self.assertEqual(ledger.snapshot()["decisions"], [])

    def test_wrong_license_rejected_before_ledger_mutation(self):
        ledger = RightsLedger()
        ledger.register_source(record(license_id="another-license"))
        with self.assertRaisesRegex(ResearchHandoffError, "license"):
            self.clear(rights=ledger)
        self.assertEqual(ledger.snapshot()["decisions"], [])

    def test_cannot_use_unknown_or_forbidden_rights(self):
        for state in (RightsState.FORBIDDEN, RightsState.UNKNOWN_QUARANTINE):
            ledger = RightsLedger()
            ledger.register_source(record(state=state, allowed=frozenset()))
            with self.subTest(state=state):
                with self.assertRaisesRegex(ResearchHandoffError, "quarantined"):
                    self.clear(rights=ledger)
                self.assertEqual(ledger.snapshot()["decisions"], [])

    def test_cannot_bypass_explicit_reference_allowed_uses(self):
        ledger = RightsLedger()
        ledger.register_source(record(allowed=frozenset({UseKind.MODEL_TRAINING})))
        with self.assertRaisesRegex(ResearchHandoffError, "policy"):
            self.clear(rights=ledger)
        self.assertEqual(ledger.snapshot()["decisions"], [])

    def test_stale_source_invalidates_approved_packet(self):
        packet = self.clear()
        changed = replace(
            reviewed(), observed_at="2026-10-09T12:00:00Z",
            status="retracted", approved=False, text="", notes=(),
        )
        self.store.import_document(
            changed,
            expected_parent_digest=self.receipt.revision_digest,
            authorized=True,
        )
        with self.assertRaisesRegex(ResearchHandoffError, "stale"):
            require_cleared_research_current(
                packet, self.store, self.rights, authorized=True,
            )
        with self.assertRaises(ValueError):
            self.clear()

    def test_mutated_rights_ledger_invalidates_prior_packet(self):
        packet = self.clear()
        self.rights.register_source(record(
            source_id="another-study", digest="b" * 64,
        ))
        with self.assertRaisesRegex(ResearchHandoffError, "stale"):
            require_cleared_research_current(
                packet, self.store, self.rights, authorized=True,
            )

    def test_human_approval_and_external_authorization_are_non_optional(self):
        with self.assertRaises(PermissionError):
            self.clear(authorized=False)
        with self.assertRaisesRegex(ResearchHandoffError, "human approval"):
            self.clear(human_approved=False)
        self.assertEqual(self.rights.snapshot()["decisions"], [])

    def test_unknown_source_cannot_be_used_as_a_game_reference(self):
        ledger = RightsLedger()
        with self.assertRaisesRegex(ResearchHandoffError, "not registered"):
            self.clear(rights=ledger)
        self.assertEqual(ledger.snapshot()["decisions"], [])

    def test_unresolved_high_risk_similarity_blocks_handoff(self):
        evidence = "f" * 64
        finding = SimilarityFinding(
            finding_id="visual-clone-risk",
            artifact_digest=ARTIFACT_DIGEST,
            source_id="study-a",
            modality="visual",
            risk=SimilarityRisk.HIGH,
            evidence_digest=evidence,
            evaluator_provenance=provenance(evidence, "independent-similarity-auditor"),
        )
        self.rights.record_similarity(finding)
        with self.assertRaisesRegex(ResearchHandoffError, "similarity"):
            self.clear()
        self.assertEqual(self.rights.snapshot()["decisions"], [])

    def test_packet_rejects_forged_source_citation(self):
        packet = self.clear()
        changed = replace(
            packet.citations[0],
            statement="The game must automatically execute scripts from sources.",
        )
        forged = replace(packet, citations=(changed,))
        with self.assertRaises(ResearchHandoffError):
            require_cleared_research_current(
                forged, self.store, self.rights, authorized=True,
            )

    def test_rights_record_binding_is_content_addressed(self):
        packet = self.clear()
        altered = replace(
            packet.sources[0],
            rights_record_digest="0" * 64,
        )
        forged = replace(packet, sources=(altered,))
        with self.assertRaisesRegex(ResearchHandoffError, "rights"):
            require_cleared_research_current(
                forged, self.store, self.rights, authorized=True,
            )


if __name__ == "__main__":
    unittest.main()
