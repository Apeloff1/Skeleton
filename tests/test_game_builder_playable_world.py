"""Executable world generation and headless game simulation integration tests."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
import unittest

from skeleton.ai.game_builder.playable_world import (
    DIRECTIONS,
    GameBuildIntent, PlayableWorld, PlayableWorldError, TileLevel,
    generate_playable_world, solve_safe_path,
)
from skeleton.ai.game_builder.playable_simulation import (
    ActionReceipt, GameReplay, GameplayError, PlayState,
    advance, demonstrate_solvable, initial_state, play_actions, verify_replay,
)


def intent(**changes):
    data = {
        "project_id": "grid-game-01",
        "title": "Skyward Maze",
        "subtitle": "Explore original paths and find the exit.",
        "seed": 1042,
        "width": 19,
        "height": 15,
        "levels": 3,
        "collectibles_per_level": 3,
        "hazards_per_level": 8,
        "theme": "space",
        "starting_health": 4,
    }
    data.update(changes)
    return GameBuildIntent(**data)


def route_to(world, target):
    """Shortest route to a tile, treating hazards as blocked until destination."""
    level = world.levels[0]
    queue = deque([level.start])
    previous = {level.start: None}
    moves = {level.start: None}
    while queue and target not in previous:
        x, y = queue.popleft()
        for name, dx, dy in DIRECTIONS:
            xx, yy = x + dx, y + dy
            if not 0 <= xx < level.width or not 0 <= yy < level.height:
                continue
            if (xx, yy) in previous:
                continue
            tile = level.rows[yy][xx]
            if tile in "#H" and (xx, yy) != target:
                continue
            previous[(xx, yy)] = (x, y)
            moves[(xx, yy)] = name
            queue.append((xx, yy))
    if target not in previous:
        return None
    out = []
    current = target
    while current != level.start:
        out.append(moves[current])
        current = previous[current]
    return tuple(reversed(out))


class PlayableWorldTests(unittest.TestCase):
    def test_multiples_of_seed_are_content_deterministic(self):
        one = generate_playable_world(intent(), authorized=True)
        two = generate_playable_world(intent(), authorized=True)
        self.assertEqual(one, two)
        self.assertEqual(one.digest, two.digest)
        self.assertEqual(one.to_payload(), two.to_payload())
        self.assertEqual(len(one.digest), 64)

    def test_changed_seed_produces_distinct_generated_world(self):
        first = generate_playable_world(intent(), authorized=True)
        second = generate_playable_world(intent(seed=1043), authorized=True)
        self.assertNotEqual(first.digest, second.digest)

    def test_complete_real_game_with_all_objectives(self):
        game = generate_playable_world(intent(), authorized=True)
        proof = demonstrate_solvable(game, authorized=True)
        self.assertEqual(proof.final_state.status, "won")
        self.assertEqual(proof.final_state.level_index, 2)
        self.assertEqual(proof.final_state.health, game.intent.starting_health)
        self.assertEqual(proof.final_state.score, 3 * (3 * 10 + 100))
        self.assertEqual(proof.final_state.steps, len(proof.action_receipts))
        verify_replay(game, proof, authorized=True)

    def test_levels_have_visible_locks_and_safe_paths(self):
        world = generate_playable_world(intent(), authorized=True)
        for index, level in enumerate(world.levels):
            self.assertEqual(level.index, index)
            self.assertEqual(len(level.collectibles), 3)
            self.assertEqual(level.rows[1][1], "S")
            self.assertEqual(level.safe_solution, solve_safe_path(level.rows))
            self.assertEqual(len(level.rows), world.intent.height)
            self.assertEqual(len(level.rows[0]), world.intent.width)
            self.assertEqual(sum(row.count("G") for row in level.rows), 1)
            self.assertEqual(sum(row.count("C") for row in level.rows), 3)
            self.assertTrue(all(direction in ("up", "down", "left", "right")
                                for direction in level.safe_solution))

    def test_varied_dimensions_and_density_stay_solvable(self):
        for seed in range(8):
            with self.subTest(seed=seed):
                game = generate_playable_world(intent(
                    width=9 + (seed % 4) * 4,
                    height=9 + (seed % 3) * 4,
                    levels=1 + seed % 3,
                    collectibles_per_level=1 + seed % 4,
                    hazards_per_level=seed * 3,
                    seed=seed,
                ), authorized=True)
                proof = demonstrate_solvable(game, authorized=True)
                self.assertEqual(proof.final_state.status, "won")

    def test_starts_in_expected_room(self):
        game = generate_playable_world(intent(), authorized=True)
        state = initial_state(game, authorized=True)
        self.assertEqual((state.x, state.y), (1, 1))
        self.assertEqual(state.level_index, 0)
        self.assertEqual(state.status, "playing")
        self.assertEqual(state.score, 0)
        self.assertEqual(state.collected, ())

    def test_wall_move_does_not_clip_through_geometry(self):
        game = generate_playable_world(intent(), authorized=True)
        state = initial_state(game, authorized=True)
        blocked = advance(game, state, "up", authorized=True)
        self.assertEqual((blocked.x, blocked.y), (state.x, state.y))
        self.assertEqual(blocked.steps, 1)
        self.assertEqual(blocked.health, state.health)

    def test_collectible_score_is_not_repeatable_by_reentry(self):
        game = generate_playable_world(intent(levels=1), authorized=True)
        target = game.levels[0].collectibles[0]
        route = route_to(game, target)
        self.assertIsNotNone(route)
        state = initial_state(game, authorized=True)
        for action in route:
            state = advance(game, state, action, authorized=True)
        self.assertIn(target, state.collected)
        self.assertEqual(state.score, 10 * len(state.collected))
        for action in ("up", "left", "right", "down"):
            other = advance(game, state, action, authorized=True)
            self.assertEqual(other.score, 10 * len(other.collected))

    def test_stepping_into_hazard_consumes_health(self):
        game = generate_playable_world(intent(levels=1, hazards_per_level=18), authorized=True)
        for hazard in game.levels[0].hazards:
            route = route_to(game, hazard)
            if route:
                state = initial_state(game, authorized=True)
                for action in route:
                    state = advance(game, state, action, authorized=True)
                self.assertEqual(state.health, game.intent.starting_health - 1)
                break
        else:
            self.fail("expected at least one reachable generated hazard")

    def test_invalid_world_intent_is_rejected(self):
        for change in (
            {"width": 10}, {"height": 8}, {"levels": 9},
            {"collectibles_per_level": 7}, {"seed": True},
            {"starting_health": 0}, {"hazards_per_level": -1},
            {"title": "\ud800"}, {"project_id": "../../unsafe"},
            {"theme": "malicious"}, {"width": 43},
        ):
            with self.subTest(change=change):
                with self.assertRaises(PlayableWorldError):
                    intent(**change)

    def test_unauthorized_generation_and_gameplay_are_rejected(self):
        with self.assertRaises(PermissionError):
            generate_playable_world(intent(), authorized=False)
        game = generate_playable_world(intent(), authorized=True)
        with self.assertRaises(PermissionError):
            initial_state(game, authorized=False)
        with self.assertRaises(PermissionError):
            advance(game, initial_state(game, authorized=True), "up", authorized=False)
        with self.assertRaises(PermissionError):
            demonstrate_solvable(game, authorized=False)

    def test_foreign_world_state_and_unknown_action_fail_closed(self):
        game = generate_playable_world(intent(), authorized=True)
        another = generate_playable_world(intent(seed=8), authorized=True)
        state = initial_state(game, authorized=True)
        with self.assertRaisesRegex(GameplayError, "world"):
            advance(another, state, "up", authorized=True)
        with self.assertRaisesRegex(GameplayError, "action"):
            advance(game, state, "fly", authorized=True)
        with self.assertRaises(GameplayError):
            advance(game, state, True, authorized=True)

    def test_replay_is_deterministic_and_tampering_is_detected(self):
        game = generate_playable_world(intent(), authorized=True)
        actions = game.levels[0].safe_solution[:30]
        first = play_actions(game, actions, authorized=True)
        second = play_actions(game, actions, authorized=True)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.action_receipts, second.action_receipts)
        with self.assertRaises(GameplayError):
            verify_replay(game, replace(
                first,
                action_receipts=(replace(first.action_receipts[0], after_digest="0" * 64),)
                + first.action_receipts[1:],
            ), authorized=True)
        with self.assertRaises(GameplayError):
            verify_replay(game, replace(first, initial_state_digest="0" * 64), authorized=True)

    def test_premature_goal_does_not_advance_level(self):
        game = generate_playable_world(intent(), authorized=True)
        goal = game.levels[0].exit
        route = route_to(game, goal)
        self.assertIsNotNone(route)
        state = initial_state(game, authorized=True)
        transitioned = False
        for direction in route:
            previous = state
            state = advance(game, state, direction, authorized=True)
            if previous.level_index == 0 and state.level_index == 1:
                # Reaching the exit after collecting all crystals is valid.
                # advance() clears collection on entry to the next level,
                # so checking only the terminal state's collection count
                # would misclassify a legitimate transition as premature.
                self.assertEqual(
                    len(previous.collected), game.intent.collectibles_per_level)
                transitioned = True
                break
        if not transitioned:
            self.assertEqual(state.level_index, 0)
            self.assertEqual(state.status, "playing")
            self.assertLess(
                len(state.collected), game.intent.collectibles_per_level)

    def test_corrupted_generated_level_proof_is_rejected(self):
        game = generate_playable_world(intent(), authorized=True)
        level = game.levels[0]
        with self.assertRaises(PlayableWorldError):
            replace(level, safe_solution=("up",))
        with self.assertRaises(PlayableWorldError):
            replace(level, rows=level.rows[:-1] + ("." * level.width,))

    def test_replay_budget_and_typing(self):
        game = generate_playable_world(intent(levels=1), authorized=True)
        with self.assertRaises(GameplayError):
            play_actions(game, ("up",) * 20001, authorized=True)
        with self.assertRaises(GameplayError):
            play_actions(game, "up", authorized=True)
        state = initial_state(game, authorized=True)
        with self.assertRaises(GameplayError):
            replace(state, steps=True)
        with self.assertRaises(GameplayError):
            replace(state, collected=((2, 1), (2, 1)))

    def test_same_path_finite_and_no_hazard_for_many_seeds(self):
        for seed in range(20):
            game = generate_playable_world(intent(
                levels=1, width=15, height=11,
                collectibles_per_level=2, hazards_per_level=8, seed=seed,
            ), authorized=True)
            state = demonstrate_solvable(game, authorized=True).final_state
            self.assertEqual(state.status, "won")
            self.assertEqual(state.health, game.intent.starting_health)


if __name__ == "__main__":
    unittest.main()
