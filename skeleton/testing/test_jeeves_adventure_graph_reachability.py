"""Regression for canonical adventure planning graph reachability and admission."""
import unittest
from skeleton.jeeves.adventure_game_capability import AdventureGameCapability


class AdventureGraphTests(unittest.TestCase):
    def setUp(self):
        self.cap = AdventureGameCapability()

    def test_all_rooms_reachable_without_skips(self):
        for count in (1, 2, 3, 10, 256):
            graph = self.cap.create_room_graph("Original story", count)
            rooms = {room["id"]: room for room in graph["rooms"]}
            visited = set()
            current = graph["start_room"]
            while current not in visited:
                self.assertIn(current, rooms)
                visited.add(current)
                exits = rooms[current]["exits"]
                if not exits:
                    break
                self.assertEqual(set(exits), {"north"})
                current = exits["north"]
            self.assertEqual(len(visited), count)
            self.assertEqual(current, graph["goal_room"])

    def test_reject_invalid_sizes_and_titles(self):
        for value in (True, False, 0, -1, 257, 1.5, "10", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.cap.create_room_graph("Story", value)
        for title in ("", " ", "x" * 201, None):
            with self.subTest(title=title), self.assertRaises(ValueError):
                self.cap.create_room_graph(title, 2)

    def test_pipeline_uses_reachable_graph(self):
        result = self.cap.full_adventure_pipeline("New world", rooms=3)
        self.assertEqual(result["room_graph"]["goal_room"], "room_03")
        self.assertEqual(result["room_graph"]["rooms"][0]["exits"]["north"], "room_02")
        for era in ("", " ", "x" * 81, None):
            with self.assertRaises(ValueError):
                self.cap.full_adventure_pipeline("New world", era=era)


if __name__ == "__main__":
    unittest.main()
