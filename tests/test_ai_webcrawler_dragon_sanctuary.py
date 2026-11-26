"""Cross-expedition aggregation is bounded, consent-scoped and deduplicated."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from skeleton.ai.webcrawler.dragon_sanctuary import SanctuarySource, project_sanctuary

A = ("Orbital mechanics uses eccentricity, angular momentum and gravitational constants "
     "to calculate trajectories. Measurements include velocity vectors, inclination, "
     "periapsis coordinates, observation uncertainties and numerical integration.")
B = ("Orbital mechanics observations compare spacecraft rendezvous maneuvers with "
     "restricted three body systems. Engineers estimate transfer windows, atmospheric "
     "drag, resonance, perturbation and long duration navigation using calibrated instruments.")
NOW = 100.


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def source(session, url, text, media="text/html", stamp=1.):
    return SanctuarySource(session, digest(url+text), digest(text), url,
                           media, text, "orbital mechanics", stamp, 1000.)


def revisions(*sessions):
    return [{"session_id": key, "version": 1, "snapshot_digest": digest(key)} for key in sessions]


def build(rows, sessions=("alpha", "beta"), **extra):
    return project_sanctuary(rows, as_of=NOW, selected_sessions=revisions(*sessions),
                              excluded_sessions=0, candidate_limit_reached=False, **extra)


class SanctuaryTests(unittest.TestCase):
    def test_exact_copy_from_second_expedition_not_earned_twice(self):
        first = source("alpha", "https://example.org/research", A)
        mirror = source("beta", "https://example.net/research", A, stamp=2.)
        base = build([first])
        repeat = build([first, mirror])
        self.assertEqual(repeat["collection_index"], base["collection_index"])
        self.assertEqual(repeat["exact_duplicates"], 1)
        self.assertEqual(repeat["credited_sources"], 1)
        self.assertEqual(repeat["distinct_origins"], 1)
        self.assertEqual(repeat["contributing_expeditions"], 1)
        self.assertNotEqual(repeat["revision_digest"], base["revision_digest"])

    def test_distinct_evidence_adds_collection_across_expeditions(self):
        first = source("alpha", "https://example.org/research", A)
        second = source("beta", "https://example.net/report", B, "text/plain", 2.)
        one = build([first])
        both = build([second, first])
        self.assertGreater(both["collection_index"], one["collection_index"])
        self.assertEqual(both["credited_sources"], 2)
        self.assertEqual(both["habitats"], {"web": 1, "text": 1})
        self.assertEqual(both["contributing_expeditions"], 2)
        self.assertEqual(both, build([first, second]))
        self.assertFalse(both["source_text_returned"])
        self.assertFalse(both["network_authority_expanded"])

    def test_revocation_and_expiration_are_not_permanent_rewards(self):
        first = source("alpha", "https://example.org/research", A)
        second = source("beta", "https://example.net/report", B, stamp=2.)
        current = build([first, second])
        revoked = build([first], sessions=("alpha",))
        self.assertLess(revoked["collection_index"], current["collection_index"])
        self.assertFalse(revoked["persistent_reward_wallet"])
        with self.assertRaises(ValueError):
            build([replace(second, valid_until=NOW)])
        with self.assertRaises(ValueError):
            build([second], sessions=("alpha",))
        with self.assertRaises(ValueError):
            build([first, first])

    def test_no_raw_text_return_and_bounded_candidate_count(self):
        one = source("alpha", "https://example.org/research", A)
        view = build([one])
        self.assertEqual(view["source_refs"][0]["source_id"], one.source_id)
        self.assertNotIn(A, str(view))
        self.assertNotIn(one.fetched_url, str(view))
        self.assertNotIn(one.query, str(view))
        with self.assertRaises(ValueError):
            build([one]*129)
        with self.assertRaises(ValueError):
            build([], sessions=tuple(str(i) for i in range(9)))


if __name__ == "__main__":
    unittest.main()
