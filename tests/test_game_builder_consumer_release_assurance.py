"""Independent release-attestation receipt tests for consumer-grade homebrew policy."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import unittest

from skeleton.ai.game_builder.consumer_release_assurance import (
    EvidenceKind, ReviewerRole, ROLES,
    SignedReleaseEvidence, TrustedReviewer,
    ReleaseEvidenceError, assess_consumer_release,
)
from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.game_builder.original_game_studio import run_original_game_studio
from skeleton.ai.game_builder.playable_world import GameBuildIntent


class ConsumerReleaseAssuranceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.studio = run_original_game_studio(
            GameBuildIntent(
                project_id="original-consumer-release-2026",
                title="Original Native Game",
                subtitle="Verified original with independent release approvals",
                seed=429616, width=11, height=11, levels=1,
                collectibles_per_level=1, hazards_per_level=0,
                theme="arcade", starting_health=3,
            ),
            authorized=True, mirror_attempts=64, companion_practice_games=0,
        )
        cls.now = datetime(2026, 10, 11, tzinfo=timezone.utc)
        cls.trust = {
            kind.value: TrustedReviewer(
                issuer_id=kind.value,
                role=role,
                key=sha256(f"independent-{kind.value}-testing-only".encode()).digest(),
            )
            for kind, role in ROLES.items()
        }

    @classmethod
    def sign(cls, kind, *, subject=None, date=None, key=None, evidence=None):
        signer = cls.trust[kind.value]
        stamp = (date or cls.now).isoformat()
        receipt = SignedReleaseEvidence(
            kind=kind,
            issuer_id=kind.value,
            subject_manifest_digest=subject or cls.studio.package.manifest["manifest_digest"],
            evidence_digest=evidence or sha256(kind.value.encode("utf-8")).hexdigest(),
            observed_at=stamp,
            signature="0" * 64,
        )
        signature = hmac.new(key or signer.key,
                             canonical_json(receipt.signed_body()).encode("utf-8"),
                             sha256).hexdigest()
        return replace(receipt, signature=signature)

    def test_original_game_is_release_blocked_without_independent_evidence(self):
        result = assess_consumer_release(
            self.studio, [], self.trust, now_utc=self.now, authorized=True)
        self.assertFalse(result.proof.approved_for_publication)
        self.assertEqual(result.proof.to_payload()["status"], "release-blocked")
        self.assertFalse(result.proof.blockers == ())
        self.assertEqual(result.source_manifest_digest,
                         self.studio.package.manifest["manifest_digest"])
        self.assertEqual(result.to_payload()["evidence_receipts"], [])

    def test_separate_signed_reviewers_can_clear_all_consumer_gates(self):
        all_rows = tuple(self.sign(kind) for kind in EvidenceKind)
        result = assess_consumer_release(
            self.studio, all_rows, self.trust, now_utc=self.now, authorized=True,
        )
        self.assertFalse(result.proof.blockers)
        self.assertTrue(result.proof.approved_for_publication)
        self.assertEqual(result.proof.to_payload()["status"],
                         "ready-for-authorized-publication")
        self.assertEqual(len(result.reviewers), len(EvidenceKind))
        self.assertEqual(len(result.evidence_receipts), len(EvidenceKind))
        self.assertEqual(result.digest, assess_consumer_release(
            self.studio, all_rows, self.trust, now_utc=self.now,
            authorized=True).digest)
        serialized = result.to_payload()
        self.assertNotIn("key", str(serialized).lower().replace(
            "independent_trust_keys_included", ""))
        self.assertFalse(serialized["independent_trust_keys_included"])

    def test_forged_hmac_wrong_role_and_reused_package_cannot_clear_gates(self):
        good = self.sign(EvidenceKind.MALWARE)
        with self.assertRaisesRegex(ReleaseEvidenceError, "signature"):
            assess_consumer_release(
                self.studio, [replace(good, signature="0" * 64)], self.trust,
                now_utc=self.now, authorized=True,
            )
        forged = self.sign(EvidenceKind.RIGHTS, subject="a" * 64)
        with self.assertRaisesRegex(ReleaseEvidenceError, "different source"):
            assess_consumer_release(
                self.studio, [forged], self.trust, now_utc=self.now,
                authorized=True,
            )
        wrong_role = dict(self.trust)
        wrong_role[good.issuer_id] = TrustedReviewer(
            good.issuer_id, ReviewerRole.PUBLISHER,
            wrong_role[good.issuer_id].key)
        with self.assertRaisesRegex(ReleaseEvidenceError, "outside designated"):
            assess_consumer_release(
                self.studio, [good], wrong_role, now_utc=self.now,
                authorized=True,
            )

    def test_publisher_cannot_self_approve_before_all_separate_gates(self):
        with self.assertRaisesRegex(ReleaseEvidenceError, "all independent"):
            assess_consumer_release(
                self.studio, [self.sign(EvidenceKind.PUBLICATION)],
                self.trust, now_utc=self.now, authorized=True)
        only_quality = [self.sign(kind) for kind in EvidenceKind
                        if kind is not EvidenceKind.PUBLICATION]
        outcome = assess_consumer_release(
            self.studio, only_quality, self.trust, now_utc=self.now,
            authorized=True)
        self.assertEqual(outcome.proof.blockers, ("approved_for_publication",))
        self.assertFalse(outcome.proof.approved_for_publication)

    def test_stale_future_duplicate_missing_identity_and_unauthorized(self):
        stale = self.sign(
            EvidenceKind.MALWARE, date=self.now - timedelta(days=31))
        with self.assertRaisesRegex(ReleaseEvidenceError, "expired"):
            assess_consumer_release(
                self.studio, [stale], self.trust, now_utc=self.now, authorized=True)
        future = self.sign(
            EvidenceKind.MALWARE, date=self.now + timedelta(days=1))
        with self.assertRaisesRegex(ReleaseEvidenceError, "future"):
            assess_consumer_release(
                self.studio, [future], self.trust, now_utc=self.now, authorized=True)
        valid = self.sign(EvidenceKind.MALWARE)
        with self.assertRaisesRegex(ReleaseEvidenceError, "duplicate"):
            assess_consumer_release(
                self.studio, [valid, valid], self.trust, now_utc=self.now, authorized=True)
        with self.assertRaisesRegex(ReleaseEvidenceError, "no configured trust"):
            assess_consumer_release(
                self.studio, [valid], {}, now_utc=self.now, authorized=True)
        with self.assertRaises(PermissionError):
            assess_consumer_release(
                self.studio, [valid], self.trust, now_utc=self.now,
                authorized=False)
        with self.assertRaises(ReleaseEvidenceError):
            TrustedReviewer("fake", ReviewerRole.LEGAL, b"short")


if __name__ == "__main__":
    unittest.main()
