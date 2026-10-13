"""Real SQLite regression tests for the consented Dragon Family gameplay plane."""
from __future__ import annotations

from hashlib import sha256
import sqlite3
import unittest

from skeleton.ai.webcrawler.dragon_family import (
    DragonFamily, IdleBroodRunner, IdleWindow, SourceReceipt, SourceSeed,
)

OWNER = "owner-a"
OTHER = "owner-b"
BASE = 1_800_000_000.
TRUSTED = "a" * 64


def receipt(source: str, value: str, at: float = BASE + 700,
            improvement: str = "") -> SourceReceipt:
    return SourceReceipt(source, sha256(value.encode()).hexdigest(), TRUSTED, at, improvement)


def idle(*, now: float = BASE + 720, last: float = BASE,
         busy: int = 0, foreground: bool = False, consent: bool = True,
         capacity: bool = True) -> IdleWindow:
    return IdleWindow(now, last, busy, foreground, consent, capacity)


def seed(source: str, kind: str = "article",
         tags: tuple[str, ...] = ("game",)) -> SourceSeed:
    return SourceSeed(source, f"https://example.org/source/{source}", kind, tags)


class DragonFamilyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sqlite3.connect(":memory:")
        # This simulates the canonical producer verifying the review receipt.
        # A production adapter must also check source custody and byte hashes.
        self.family = DragonFamily(self.db, approval=lambda row: row.review_digest == TRUSTED)

    def tearDown(self) -> None:
        self.db.close()

    def complete(self, *sources: SourceSeed) -> None:
        self.family.enroll(OWNER, tuple(sources), authorized=True, now=BASE)
        self.assertTrue(self.family.seal_inventory(OWNER, authorized=True, now=BASE + 0.5))
        for index, item in enumerate(sources):
            self.assertTrue(self.family.consume(
                OWNER, receipt(item.source_id, "original-" + item.source_id, BASE + index + 10),
                authorized=True))

    def test_parent_hatches_levels_and_lays_exactly_three_eggs(self) -> None:
        sources = tuple(seed("web-" + str(i)) for i in range(5))
        self.family.enroll(OWNER, sources, authorized=True, now=BASE)
        with self.assertRaises(PermissionError):
            self.family.consume(OWNER, receipt(sources[0].source_id, "premature", BASE + 1),
                                authorized=True)
        self.assertTrue(self.family.seal_inventory(OWNER, authorized=True, now=BASE + 0.5))
        self.assertEqual(self.family.snapshot(OWNER, authorized=True)["parent"]["stage"], "egg")
        for i, expected in enumerate(("hatchling", "juvenile", "adolescent", "adolescent", "adult")):
            proof = receipt(sources[i].source_id, "original-" + str(i), BASE + i + 1)
            self.assertTrue(self.family.consume(OWNER, proof, authorized=True))
            self.assertEqual(self.family.snapshot(OWNER, authorized=True)["parent"]["stage"], expected)
        snap = self.family.snapshot(OWNER, authorized=True)
        self.assertTrue(snap["parent"]["complete"])
        self.assertEqual(snap["parent"]["consumed"], 5)
        self.assertEqual([c["stage"] for c in snap["children"]], ["egg"] * 3)
        self.assertEqual([c["id"] for c in snap["children"]], ["article", "video", "monitor"])
        self.assertEqual(sum(e["action"] == "three_eggs_laid" for e in snap["history"]), 1)
        self.assertFalse(self.family.consume(
            OWNER, receipt("web-4", "original-4", BASE + 99), authorized=True))
        self.assertEqual(sum(e["action"] == "three_eggs_laid"
                             for e in self.family.history(OWNER, authorized=True)), 1)
        self.family.enroll(OWNER, (seed("late-1"),), authorized=True, now=BASE + 200)
        with self.assertRaises(ValueError):
            self.family.consume(OWNER, receipt("late-1", "late"), authorized=True)
        self.assertEqual(self.family.snapshot(OWNER, authorized=True)["parent"]["source_total"], 5)

    def test_source_specialization_content_changes_and_history(self) -> None:
        self.complete(seed("web-1"), seed("vid-1", "video"), seed("monitor-1"))
        first = receipt("web-1", "web-revision-2", improvement="better pathfinding examples")
        self.assertTrue(self.family.digest_idle(
            OWNER, "article", first, authorized=True, window=idle(), task_topics=("game",)))
        self.assertFalse(self.family.digest_idle(
            OWNER, "article", first, authorized=True, window=idle(), task_topics=("game",)))
        self.assertTrue(self.family.digest_idle(
            OWNER, "video", receipt("vid-1", "video-revision-2"),
            authorized=True, window=idle(), task_topics=("game",)))
        self.assertTrue(self.family.digest_idle(
            OWNER, "monitor", receipt("monitor-1", "monitor-revision-2",
                                     improvement="API documentation changed"),
            authorized=True, window=idle(), task_topics=("game",)))
        snap = self.family.snapshot(OWNER, authorized=True)
        self.assertEqual([c["stage"] for c in snap["children"]], ["hatchling"] * 3)
        self.assertEqual([c["discoveries"] for c in snap["children"]], [1, 1, 1])
        self.assertTrue(snap["children"][0]["last_grew_at"].endswith("Z"))
        self.assertTrue(any("(improved: better pathfinding examples)" in row["change"]
                            for row in snap["history"]))
        self.assertTrue(any("(updated: new verified source revision)" in row["change"]
                            for row in snap["history"]))
        self.assertTrue(all("T" in row["at"] and row["at"].endswith("Z")
                            for row in snap["history"]))
        self.assertTrue(all(len(row["digest"]) == 64 for row in snap["history"]))

    def test_only_idle_and_not_busy_or_foreground(self) -> None:
        self.complete(seed("web-1"))
        proof = receipt("web-1", "new-material")
        for window in (idle(now=BASE + 200), idle(foreground=True), idle(busy=1),
                       idle(consent=False), idle(capacity=False),
                       idle(last=BASE + 650)):
            with self.subTest(window=window), self.assertRaises(PermissionError):
                self.family.digest_idle(
                    OWNER, "article", proof, authorized=True,
                    window=window, task_topics=("game",))
        self.assertEqual(self.family.snapshot(OWNER, authorized=True)["children"][0]["discoveries"], 0)

    def test_adjacent_task_relevance_requires_explicit_topic(self) -> None:
        self.complete(seed("web-1", tags=("physics",)))
        update = receipt("web-1", "revised-physics")
        with self.assertRaises(ValueError):
            self.family.digest_idle(
                OWNER, "article", update, authorized=True,
                window=idle(), task_topics=("game",), adjacent_topics=())
        self.assertTrue(self.family.digest_idle(
            OWNER, "article", update, authorized=True, window=idle(),
            task_topics=("game",), adjacent_topics=("physics",)))
        self.assertTrue(any("adjacent task knowledge" in h["change"]
                            for h in self.family.history(OWNER, authorized=True)))

    def test_global_revision_novelty_and_monotonic_source_observation(self) -> None:
        self.complete(seed("web-1"))
        new = receipt("web-1", "rev2", BASE + 700)
        self.assertTrue(self.family.digest_idle(
            OWNER, "monitor", new, authorized=True, window=idle(), task_topics=("game",)))
        # A second sibling cannot farm the identical captured bytes.
        self.assertFalse(self.family.digest_idle(
            OWNER, "article", receipt("web-1", "rev2", BASE + 701),
            authorized=True, window=idle(), task_topics=("game",)))
        with self.assertRaisesRegex(ValueError, "advance"):
            self.family.digest_idle(
                OWNER, "article", receipt("web-1", "rev3", BASE + 699),
                authorized=True, window=idle(), task_topics=("game",))
        self.assertTrue(self.family.digest_idle(
            OWNER, "article", receipt("web-1", "rev3", BASE + 702),
            authorized=True, window=idle(), task_topics=("game",)))
        self.assertEqual([c["discoveries"] for c in self.family.snapshot(
            OWNER, authorized=True)["children"]], [1, 0, 1])

    def test_sealed_source_quest_never_prematurely_lays_eggs(self) -> None:
        self.family.enroll(OWNER, (seed("web-1"),), authorized=True, now=BASE)
        with self.assertRaisesRegex(PermissionError, "sealed"):
            self.family.consume(OWNER, receipt("web-1", "one", BASE + 1),
                                authorized=True)
        self.family.enroll(OWNER, (seed("web-2"),), authorized=True, now=BASE + 1)
        self.family.seal_inventory(OWNER, authorized=True, now=BASE + 2)
        with self.assertRaisesRegex(PermissionError, "sealed"):
            self.family.enroll(OWNER, (seed("web-3"),), authorized=True, now=BASE + 3)
        self.family.consume(OWNER, receipt("web-1", "one", BASE + 4), authorized=True)
        self.assertFalse(self.family.snapshot(OWNER, authorized=True)["parent"]["complete"])
        self.family.consume(OWNER, receipt("web-2", "two", BASE + 5), authorized=True)
        self.assertTrue(self.family.snapshot(OWNER, authorized=True)["parent"]["complete"])
        self.assertFalse(self.family.seal_inventory(OWNER, authorized=True, now=BASE + 6))

    def test_no_ingest_without_authority_and_no_rogue_promotion(self) -> None:
        reader = DragonFamily(self.db)
        with self.assertRaises(PermissionError):
            reader.enroll(OWNER, (seed("new-1"),), authorized=True, now=BASE)
        with self.assertRaises(PermissionError):
            self.family.enroll(OWNER, (seed("new-1"),), authorized=False, now=BASE)
        self.complete(seed("web-1"))
        with self.assertRaises(PermissionError):
            self.family.digest_idle(
                OWNER, "article", SourceReceipt("web-1", "b" * 64, "c" * 64, BASE + 700),
                authorized=True, window=idle(), task_topics=("game",))
        with self.assertRaises(PermissionError):
            reader.consume(OWNER, receipt("web-1", "updated"), authorized=True)
        self.assertEqual(reader.snapshot(OWNER, authorized=True)["children"][0]["discoveries"], 0)
        with self.assertRaises(PermissionError):
            reader.snapshot(OWNER, authorized=False)

    def test_specialized_media_and_monitor_revision_only(self) -> None:
        self.complete(seed("web-1"), seed("vid-1", "video"))
        with self.assertRaises(ValueError):
            self.family.digest_idle(
                OWNER, "video", receipt("web-1", "new"), authorized=True,
                window=idle(), task_topics=("game",))
        with self.assertRaises(ValueError):
            self.family.digest_idle(
                OWNER, "article", receipt("vid-1", "new"), authorized=True,
                window=idle(), task_topics=("game",))
        # A monitor cannot grow on a metadata-only recheck.
        self.assertFalse(self.family.digest_idle(
            OWNER, "monitor", receipt("web-1", "original-web-1"),
            authorized=True, window=idle(), task_topics=("game",)))
        self.assertTrue(self.family.digest_idle(
            OWNER, "monitor", receipt("web-1", "a-verified-update"),
            authorized=True, window=idle(), task_topics=("game",)))
        self.assertFalse(self.family.digest_idle(
            OWNER, "monitor", receipt("web-1", "a-verified-update"),
            authorized=True, window=idle(), task_topics=("game",)))

    def test_cross_owner_isolation_and_hash_chain_refuses_tampering(self) -> None:
        self.complete(seed("web-1"))
        self.family.enroll(OTHER, (seed("other-1"),), authorized=True, now=BASE)
        self.assertEqual(self.family.snapshot(OTHER, authorized=True)["parent"]["consumed"], 0)
        self.assertEqual(self.family.snapshot(OTHER, authorized=True)["children"][0]["stage"], "unborn")
        self.assertEqual(len(self.family.history(OTHER, authorized=True)), 1)
        self.db.execute("""UPDATE dragon_family_events SET details='FORGED'
            WHERE owner=? AND sequence=1""", (OWNER,))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.family.history(OWNER, authorized=True)
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.family.snapshot(OWNER, authorized=True)
        self.assertEqual(len(self.family.history(OTHER, authorized=True)), 1)

    def test_source_register_conflicts_rollback_atomically(self) -> None:
        self.family.enroll(OWNER, (seed("web-1"),), authorized=True, now=BASE)
        with self.assertRaises(ValueError):
            self.family.enroll(OWNER, (seed("added-1"), seed("web-1", "video")),
                               authorized=True, now=BASE + 1)
        self.assertEqual(self.family.snapshot(OWNER, authorized=True)["parent"]["source_total"], 1)

    def test_worker_rechecks_idle_after_fetch_and_budgets_tasks(self) -> None:
        self.complete(seed("web-1"), seed("vid-1", "video"))
        ticks = iter((idle(), idle(foreground=True)))
        invoked = []
        runner = IdleBroodRunner(self.family, max_per_tick=1)
        output = runner.tick(
            OWNER, (("article", lambda: (invoked.append(1) or receipt("web-1", "new"))),),
            authorized=True, idle_state=lambda: next(ticks), task_topics=("game",))
        self.assertEqual(output, {"attempted": 0, "grown": 0, "paused": True})
        self.assertEqual(invoked, [1])
        self.assertEqual(self.family.snapshot(OWNER, authorized=True)["children"][0]["discoveries"], 0)
        output = runner.tick(
            OWNER, (("article", lambda: receipt("web-1", "new")),
                    ("video", lambda: receipt("vid-1", "new"))),
            authorized=True, idle_state=idle, task_topics=("game",))
        self.assertEqual(output, {"attempted": 1, "grown": 1, "paused": False})
        self.assertEqual([c["discoveries"] for c in self.family.snapshot(
            OWNER, authorized=True)["children"]], [1, 0, 0])

    def test_admission_rechecks_canonical_consent_inside_write_transaction(self) -> None:
        counter = {"calls": 0}

        def one_time_approval(proof: SourceReceipt) -> bool:
            counter["calls"] += 1
            return counter["calls"] == 1

        db = sqlite3.connect(":memory:")
        family = DragonFamily(db, approval=one_time_approval)
        family.enroll(OWNER, (seed("web-1"),), authorized=True, now=BASE)
        family.seal_inventory(OWNER, authorized=True, now=BASE + 1)
        with self.assertRaisesRegex(PermissionError, "approval changed"):
            family.consume(OWNER, receipt("web-1", "original", BASE + 2), authorized=True)
        status = family.snapshot(OWNER, authorized=True)
        self.assertEqual(status["parent"]["consumed"], 0)
        self.assertFalse(status["parent"]["complete"])
        self.assertEqual(sum(x["action"] == "consumed" for x in status["history"]), 0)
        db.close()

    def test_bounded_idle_runner_fairly_dispatches_distinct_specialists(self) -> None:
        self.complete(seed("web-1"), seed("vid-1", "video"))
        calls = []
        def capture(label, source, contents):
            calls.append(label)
            return receipt(source, contents)
        output = IdleBroodRunner(self.family, max_per_tick=3).tick(
            OWNER, (
                ("article", lambda: capture("first article", "web-1", "rev-1")),
                ("article", lambda: capture("duplicate article", "web-1", "rev-2")),
                ("video", lambda: capture("video", "vid-1", "rev-1")),
            ), authorized=True, idle_state=idle, task_topics=("game",))
        self.assertEqual(output, {"attempted": 2, "grown": 2, "paused": False})
        self.assertEqual(calls, ["first article", "video"])
        self.assertEqual([c["discoveries"] for c in self.family.snapshot(
            OWNER, authorized=True)["children"]], [1, 1, 0])

    def test_invalid_input_and_no_progress_from_old_receipt(self) -> None:
        self.complete(seed("web-1"))
        with self.assertRaises(ValueError):
            self.family.digest_idle(
                OWNER, "article", receipt("web-1", "new", at=BASE + 999),
                authorized=True, window=idle(), task_topics=("game",))
        with self.assertRaises(ValueError):
            self.family.digest_idle(
                OWNER, "article", receipt("web-1", "new"),
                authorized=True, window=idle(), task_topics=("not valid !",))
        with self.assertRaises(ValueError):
            self.family.enroll(OWNER, (SourceSeed("bad-1", "http://unsafe.test", "article",
                                                  ("game",)),), authorized=True, now=BASE)


if __name__ == "__main__":
    unittest.main()
