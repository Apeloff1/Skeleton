"""Reward and completability bridges against test doubles (B028 / solver not merged)."""
from __future__ import annotations

from collections import deque
import unittest

from skeleton.ai.game_builder.quest_completability_bridge import (
    CompletabilitySolver, CompletabilityVerdict, Door, Room, keys_held,
)
from skeleton.ai.game_builder.quest_rewards_bridge import QuestRewardBoard, QuestRewardBridge
from skeleton.ai.game_builder.quest_scene_engine import DirectorState
from skeleton.frontier.progression.quests import ObjectiveProgress, QuestProgressState


class FakeBoard:
    """Same shape and refusal behaviour as B028 QuestBoard."""

    def __init__(self, full=False):
        self.done, self.full = set(), full

    def completed(self, owner, quest_id):
        return (owner, quest_id) in self.done

    def complete(self, owner, quest_id, tick):
        if (owner, quest_id) in self.done:
            raise ValueError("quest already completed")
        if self.full:
            raise ValueError("inventory full")
        self.done.add((owner, quest_id))
        return {"money": 25, "items": {"herb": 2}}


class ReachabilityDouble:
    """Trivial test double: BFS, picking up keys as rooms are reached."""

    def check(self, rooms, start, keys_held):
        by, keys, seen = {r.key: r for r in rooms}, set(keys_held), set()
        changed = True
        while changed:
            changed, todo, seen = False, deque([start]), {start}
            while todo:
                r = by[todo.popleft()]
                if not set(r.keys) <= keys:
                    keys |= set(r.keys)
                    changed = True
                for d in r.doors:
                    if d.to not in seen and (d.requires is None or d.requires in keys):
                        seen.add(d.to)
                        todo.append(d.to)
        ok = any(by[k].goal for k in seen)
        return CompletabilityVerdict(ok, not ok, "" if ok else "goal unreachable")


def done(qid, status="completed"):
    return QuestProgressState(qid, status, {"0": ObjectiveProgress(1, 1, True)})


class RewardBridgeTests(unittest.TestCase):
    def test_pays_once_and_respects_status(self):
        board = FakeBoard()
        self.assertIsInstance(board, QuestRewardBoard)
        bridge = QuestRewardBridge(board)
        out = bridge.claim("p1", done("q1"), 5)
        self.assertEqual((out.status, out.money, dict(out.items)), ("paid", 25, {"herb": 2}))
        self.assertEqual(bridge.claim("p1", done("q1"), 6).status, "already_paid")
        self.assertEqual(bridge.claim("p1", done("q2", "active"), 6).status, "not_complete")
        self.assertEqual(bridge.claim("p1", done("q3", "failed"), 6).status, "failed")

    def test_refusal_is_reported_not_raised(self):
        out = QuestRewardBridge(FakeBoard(full=True)).claim("p1", done("q1"), 1)
        self.assertEqual((out.status, out.reason), ("refused", "inventory full"))
        with self.assertRaises(TypeError):
            QuestRewardBridge(object())


class CompletabilityTests(unittest.TestCase):
    ROOMS = (Room("hall", (Door("vault", "gold_key"), Door("cellar"))),
             Room("cellar", (Door("hall"),), keys=("gold_key",)),
             Room("vault", goal=True))

    def test_double_satisfies_protocol_and_keys_come_from_director(self):
        solver = ReachabilityDouble()
        self.assertIsInstance(solver, CompletabilitySolver)
        self.assertTrue(solver.check(self.ROOMS, "hall", frozenset()).completable)
        locked = (self.ROOMS[0], Room("cellar", (Door("hall"),)), self.ROOMS[2])
        self.assertTrue(solver.check(locked, "hall", frozenset()).softlocked)
        state = DirectorState("w", "hall", 0, (), (), (), ("gold_key",), (), (), ())
        self.assertTrue(solver.check(locked, "hall", keys_held(state)).completable)


if __name__ == "__main__":
    unittest.main()
