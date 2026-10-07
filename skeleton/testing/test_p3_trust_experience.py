from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from skeleton.cognition.trust_experience import (
    AccessibilitySurface,
    AccessibilityValidator,
    ComplianceControl,
    ComplianceRegistry,
    ExplanationBundle,
    ExplanationClaim,
    InteractionKind,
    LocalePolicy,
    TrustExperienceError,
)


NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


class P3TrustExperienceTests(unittest.TestCase):
    def test_explanation_claims_bind_operation_and_evidence(self) -> None:
        bundle = ExplanationBundle(
            explanation_id="exp-1",
            operation_ref="operation:abc",
            claims=(
                ExplanationClaim(
                    claim_id="claim-1",
                    statement="The operation used local model evidence.",
                    operation_ref="operation:abc",
                    evidence_refs=("provider:local:receipt-1",),
                    confidence_label="verified",
                ),
            ),
            provenance_refs=("trace:operation:abc",),
            caveats=("Explanation is evidence-derived, not hidden-chain disclosure.",),
        )
        self.assertEqual(bundle.evidence_refs, ("provider:local:receipt-1",))
        self.assertEqual(len(bundle.digest), 64)

    def test_explanation_rejects_operation_provenance_drift(self) -> None:
        with self.assertRaisesRegex(TrustExperienceError, "operation provenance drift"):
            ExplanationBundle(
                explanation_id="exp-1",
                operation_ref="operation:a",
                claims=(
                    ExplanationClaim(
                        claim_id="claim-1",
                        statement="claim",
                        operation_ref="operation:b",
                        evidence_refs=("evidence:1",),
                    ),
                ),
                provenance_refs=("trace:a",),
            )

    def _accessible_surfaces(self):
        return tuple(
            AccessibilitySurface(
                surface_id=f"surface-{kind.value}",
                kind=kind,
                semantic_name=f"{kind.value} control",
                keyboard_reachable=True,
                screen_reader_exposed=True,
                visual_only=False,
                text_equivalent=f"{kind.value} text",
            )
            for kind in AccessibilityValidator.REQUIRED
        )

    def test_accessibility_requires_semantic_non_visual_critical_paths(self) -> None:
        receipt = AccessibilityValidator().validate(self._accessible_surfaces())
        self.assertTrue(receipt.passed)
        self.assertIn("cancellation", receipt.required_kinds)
        self.assertIn("approval", receipt.required_kinds)

    def test_accessibility_rejects_visual_only_error(self) -> None:
        surfaces = list(self._accessible_surfaces())
        index = next(i for i, item in enumerate(surfaces) if item.kind is InteractionKind.ERROR)
        surfaces[index] = AccessibilitySurface(
            surface_id="surface-error",
            kind=InteractionKind.ERROR,
            semantic_name="error",
            keyboard_reachable=True,
            screen_reader_exposed=False,
            visual_only=True,
        )
        with self.assertRaisesRegex(TrustExperienceError, "acceptance failed"):
            AccessibilityValidator().validate(surfaces)

    def test_locale_policy_normalizes_presentation_but_not_machine_numbers(self) -> None:
        policy = LocalePolicy(
            default_locale="en-US",
            supported_locales=("en-US", "nb-NO", "de-DE"),
            fallback_locale="en-US",
        )
        self.assertEqual(policy.resolve("nb_no"), "nb-NO")
        self.assertEqual(policy.resolve("fr-FR"), "en-US")
        self.assertEqual(policy.parse_machine_number("1234.50"), 1234.5)
        with self.assertRaisesRegex(TrustExperienceError, "locale-independent"):
            policy.parse_machine_number("1.234,50")

    def test_compliance_registry_requires_current_owned_evidence(self) -> None:
        registry = ComplianceRegistry()
        registry.register(
            ComplianceControl(
                control_id="control-retention",
                control_family="data-governance",
                applicability=("product:eu",),
                owner_id="owner:privacy",
                evidence_refs=("evidence:retention-policy",),
                source_refs=("source:control-registry",),
                valid_from=NOW - timedelta(days=1),
                valid_until=NOW + timedelta(days=30),
            )
        )
        decision = registry.evaluate(
            scope="product:eu",
            required_control_ids=("control-retention",),
            at=NOW,
        )
        self.assertTrue(decision.complete)
        self.assertEqual(decision.owner_ids, ("owner:privacy",))
        self.assertEqual(decision.evidence_refs, ("evidence:retention-policy",))

    def test_compliance_registry_rejects_expired_control(self) -> None:
        registry = ComplianceRegistry()
        registry.register(
            ComplianceControl(
                control_id="expired",
                control_family="test",
                applicability=("product:eu",),
                owner_id="owner:test",
                evidence_refs=("evidence:old",),
                source_refs=("source:registry",),
                valid_from=NOW - timedelta(days=10),
                valid_until=NOW - timedelta(days=1),
            )
        )
        with self.assertRaisesRegex(TrustExperienceError, "not current"):
            registry.evaluate(
                scope="product:eu",
                required_control_ids=("expired",),
                at=NOW,
            )

    def test_compliance_registry_does_not_infer_undeclared_scope(self) -> None:
        registry = ComplianceRegistry()
        registry.register(
            ComplianceControl(
                control_id="control-us",
                control_family="test",
                applicability=("product:us",),
                owner_id="owner:test",
                evidence_refs=("evidence:test",),
                source_refs=("source:registry",),
                valid_from=NOW - timedelta(days=1),
            )
        )
        with self.assertRaisesRegex(TrustExperienceError, "does not declare scope"):
            registry.evaluate(
                scope="product:eu",
                required_control_ids=("control-us",),
                at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
