"""Deterministic live-grid route advice, obstruction, and restart custody."""
import unittest

from skeleton.game.gameplay.offline_grid_campaign import Campaign, Command, Session


def campaign(rows, objects=None):
    return Campaign.load({
        "version": 1, "game_id": "route_game", "title": "RouteGame",
        "license": "CC0-1.0", "author": "OriginalAuthor",
        "rows": rows, "objects": objects or [], "quests": [],
        "endings": [{"id": "win", "requires_quests": [], "outcome": "victory"}],
    })


class GoalRouteTests(unittest.TestCase):
    def test_route_executes_to_actual_goal_and_ending(self):
        source = campaign(["#####", "#S.G#", "#####"])
        state = Session.new(source)
        route = state.shortest_goal_route()
        self.assertEqual(route, ("east", "east"))
        for i, direction in enumerate(route):
            state = state.step(Command(f"move_{i}", "move", direction))
        self.assertEqual(state.shortest_goal_route(), ())
        state = state.step(Command("finish_1", "finish", "win"))
        self.assertEqual(state.ending, "win")

    def test_walls_and_living_enemy_fail_closed(self):
        source = campaign(["#####", "#S.G#", "#####"], [
            {"id": "guard", "kind": "enemy", "x": 2, "y": 1, "hp": 2, "attack": 0}
        ])
        state = Session.new(source)
        self.assertIsNone(state.shortest_goal_route())
        state = state.step(Command("hit_1", "strike", "guard"))
        self.assertEqual(state.shortest_goal_route(), ("east", "east"))
        self.assertEqual(Session.restore(source, state.snapshot()).shortest_goal_route(),
                         ("east", "east"))

    def test_quest_target_navigation_and_replay(self):
        source = campaign(["#######", "#S...G#", "#.....#", "#######"], [
            {"id": "guide", "kind": "npc", "x": 3, "y": 2}
        ])
        state = Session.new(source)
        route = state.shortest_route_to(3, 2)
        self.assertEqual(len(route), 3)
        for i, direction in enumerate(route):
            state = state.step(Command(f"quest_move_{i}", "move", direction))
        self.assertEqual((state.x, state.y), (3, 2))
        state = state.step(Command("quest_talk", "talk", "guide"))
        restored = Session.restore(source, state.snapshot())
        self.assertEqual(restored.shortest_route_to(3, 2), ())
        self.assertIn("guide", restored.spoken)

    def test_invalid_destinations_fail_closed_and_do_not_mutate(self):
        from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
        state = Session.new(campaign(["#####", "#S.G#", "#####"]))
        original = state.snapshot()
        for x, y in [(True, 1), (1, False), (-1, 1), (99, 1), (0, 0), (1.0, 1)]:
            with self.subTest(x=x, y=y):
                with self.assertRaises(GameplayContractError):
                    state.shortest_route_to(x, y)
        self.assertEqual(state.snapshot(), original)

    def test_wall_separates_goal_without_false_route(self):
        state = Session.new(campaign(["#####", "#S#G#", "#####"]))
        self.assertIsNone(state.shortest_goal_route())
        self.assertEqual(state.tick, 0)
        self.assertEqual(state.events, ())


if __name__ == "__main__":
    unittest.main()
