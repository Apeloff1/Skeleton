"""GB-20 digest stability and format."""

from __future__ import annotations

import unittest

from skeleton.spine.chain import default_chain
from skeleton.spine.digest import (
    assert_digest_format,
    blake16,
    chain_digest,
    digest_drift,
    digest_pair,
    digests_equal,
    stable_neutral_digest,
    vertebra_digest,
)
from skeleton.spine.law import DIGEST_ALGO
from skeleton.spine.posture import build_posture


class TestDigestsStable(unittest.TestCase):
    def test_default_digest_stable(self) -> None:
        a = chain_digest(default_chain())
        b = chain_digest(default_chain())
        self.assertEqual(a, b)
        assert_digest_format(a)
        self.assertEqual(len(a), 16)

    def test_digests_equal_same_chain(self) -> None:
        self.assertTrue(digests_equal(default_chain(), default_chain()))

    def test_name_affects_digest(self) -> None:
        self.assertFalse(digests_equal(default_chain("a"), default_chain("b")))

    def test_stable_neutral(self) -> None:
        d = stable_neutral_digest()
        assert_digest_format(d)
        self.assertEqual(d, chain_digest(default_chain("neutral")))

    def test_posture_changes_digest(self) -> None:
        base = default_chain()
        flexed = build_posture("flexion_30", base)
        self.assertNotEqual(chain_digest(base), chain_digest(flexed))
        self.assertGreater(digest_drift(base, flexed), 0)

    def test_digest_pair(self) -> None:
        pair = digest_pair(default_chain())
        self.assertEqual(pair["algo"], DIGEST_ALGO)
        assert_digest_format(pair["chain"])
        assert_digest_format(pair["cranial"])
        assert_digest_format(pair["caudal"])

    def test_vertebra_digest(self) -> None:
        chain = default_chain()
        d = vertebra_digest(chain.cranial())
        assert_digest_format(d)

    def test_blake16_deterministic(self) -> None:
        self.assertEqual(blake16(["a", "b"]), blake16(["a", "b"]))
        self.assertNotEqual(blake16(["a"]), blake16(["b"]))

    def test_bad_format_raises(self) -> None:
        with self.assertRaises(AssertionError):
            assert_digest_format("xyz")
        with self.assertRaises(AssertionError):
            assert_digest_format("0123456789abcdef0")


if __name__ == "__main__":
    unittest.main()
