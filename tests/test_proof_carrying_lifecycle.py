"""Fail-closed tests for PR #3482 seam proof_carrying_lifecycle."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.proof_carrying_lifecycle")


class TestProofCarryingLifecycle(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3482", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "proof-lifecycle")

    def test_rejects_prose(self):
        with self.assertRaises(PermissionError):
            mod.card(True, stored_prose=1)

    def test_pointer_bound(self):
        with self.assertRaises(ValueError):
            mod._id("has\nnewline", "x")
        with self.assertRaises(ValueError):
            mod._u(-1, "n")
        with self.assertRaises(ValueError):
            mod._u(True, "n")



    def test_promote_requires_hold(self):
        base = [mod.Proof.create(p, "claim-1", "d-"+p) for p in ("propose", "admit", "hold")]
        self.assertEqual(mod.advance(base).phase, "hold")
        promo = base + [mod.Proof.create("promote", "claim-1", "d-promote")]
        self.assertEqual(mod.advance(promo).phase, "promote")
        naked = [mod.Proof.create(p, "claim-1", "d-"+p) for p in ("propose", "admit", "promote")]
        with self.assertRaises(PermissionError):
            mod.advance(naked)

    def test_forged_proof_identity_is_rejected(self):
        original = mod.Proof.create("propose", "claim-1", "pointer-1")
        with self.assertRaisesRegex(PermissionError, "proof identity"):
            mod.Proof("proof-sha256:" + "0" * 64, original.phase, original.claim_id, original.digest)

    def test_lifecycle_identity_and_proof_refs_are_not_rebindable(self):
        proofs = tuple(mod.Proof.create(phase, "claim-1", "pointer-" + phase)
                       for phase in ("propose", "admit", "hold"))
        lifecycle = mod.advance(proofs)
        with self.assertRaisesRegex(PermissionError, "lifecycle identity"):
            mod.Lifecycle("life-sha256:" + "0" * 64, lifecycle.claim_id,
                          lifecycle.proof_ids, lifecycle.phase)
        with self.assertRaisesRegex(PermissionError, "duplicate lifecycle proof"):
            mod.Lifecycle(lifecycle.life_id, lifecycle.claim_id,
                          (lifecycle.proof_ids[0],) * 2, lifecycle.phase)

    def test_proof_card_authority_is_not_overridable(self):
        for name, value in (
            ("law", "stored_prose=1"),
            ("citation", "https://example.org/"),
            ("kind", "production-approved"),
            ("hit", True),
        ):
            with self.assertRaisesRegex(PermissionError, "immutable"):
                mod.card(False, **{name: value})
        with self.assertRaises(TypeError):
            mod.advance((object(),))
        with self.assertRaises(TypeError):
            mod.exit_card(object())

if __name__ == "__main__":
    unittest.main()
