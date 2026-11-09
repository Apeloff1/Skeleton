"""GB-42 parse-pointer tests."""

from __future__ import annotations

import unittest

from skeleton.parse import N_CAP, capabilities, split


class TestAccept(unittest.TestCase):
    def test_two_pointers(self) -> None:
        card = split("see https://arxiv.org/abs/x and github.com/Apeloff1/Skeleton")
        self.assertEqual(card["n"], 2)
        self.assertEqual(card["stored_prose"], 0)
        kinds = {p["kind"] for p in card["pointers"]}
        self.assertEqual(kinds, {"arxiv", "github"})
        self.assertNotIn("see", str(card["pointers"]))

    def test_n_cap_drops(self) -> None:
        urls = " ".join("https://arxiv.org/abs/%d" % i for i in range(12))
        card = split(urls)
        self.assertEqual(card["n"], N_CAP)
        self.assertEqual(card["dropped"], 4)
        self.assertEqual(card["hit"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_caps(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["contract"]["n_cap"], 8)
        self.assertEqual(cap["contract"]["mesh_sentence"], 0)


if __name__ == "__main__":
    unittest.main()
