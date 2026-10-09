import unittest

from ai_tree_fill.chamber import AuthorityGrant, Chamber, CourtSeal, RivalChallenge, RivalProposal, ToolSchema
from ai_tree_fill.ed25519_hold import Ed25519Hold


class ChamberTests(unittest.TestCase):
    def test_walk_seals_a_signed_root(self):
        chamber = Chamber()
        card = chamber.walk("github.com/Apeloff1/Skeleton VOL-113 GB-16 AIFT-CHAMBER")
        self.assertEqual(card["hit"], 1)
        self.assertEqual(card["contradiction"], "reconciled")
        self.assertEqual(card["stream"]["mismatch_at"], 1)
        hold = Ed25519Hold.from_seed_hex(chamber.hold.export_private_hex())
        envelope = hold.sign(card["root"].encode())
        self.assertEqual(envelope.key_id, card["key_id"])
        seal = chamber.seal()
        self.assertEqual(seal["events"], 1)
        self.assertFalse(seal["sealed"])

    def test_widened_grant_and_bad_schema_seal(self):
        parent = AuthorityGrant("root", frozenset({"read"}))
        with self.assertRaises(CourtSeal):
            parent.subset(AuthorityGrant("child", frozenset({"read", "destructive"})))
        with self.assertRaises(CourtSeal):
            ToolSchema("x", ("a",), ("b",), "read", 1000).validate({"a": 1, "extra": 2})

    def test_rival_strike_only_when_axis_fails(self):
        proposal = RivalProposal.from_stimulus("forge", "VOL-9 github.com/Apeloff1/Skeleton", {"fun": 0.2})
        card = RivalChallenge("cut", "forge", "fun", proposal.pointers[0]).strike(proposal)
        self.assertEqual(card["failed_axis"], "fun")
        held = RivalProposal.from_stimulus("forge", "VOL-9 github.com/Apeloff1/Skeleton", {"fun": 0.9})
        with self.assertRaises(CourtSeal):
            RivalChallenge("cut", "forge", "fun", held.pointers[0]).strike(held)


if __name__ == "__main__":
    unittest.main()
