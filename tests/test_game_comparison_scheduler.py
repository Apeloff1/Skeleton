"""Resource guard contracts for ten-game native comparative batches."""

from __future__ import annotations

import unittest

from skeleton.jeeves.game_comparison_schema import ComparativeStudyError
from skeleton.jeeves.game_comparison_studio import _storage_waves


def _game(index, byte_count=None):
    return {
        "id":f"game_{index}",
        "content_bundle": None if byte_count is None else {
            "entrypoint":"disc.cue",
            "files":[{"name":"track.bin","size_bytes":byte_count}],
        }
    }


class ComparativeStorageWaveTests(unittest.TestCase):
    def test_small_games_admit_all_ten(self):
        games=[_game(i) for i in range(10)]
        waves,budget=_storage_waves(games,requested_slots=10,free_temp_bytes=12*1024**3)
        self.assertEqual([len(x) for x in waves],[10])
        self.assertGreater(budget,0)

    def test_disc_games_are_split_without_changing_order(self):
        games=[_game(i,2*1024**3) for i in range(3)]
        waves,budget=_storage_waves(games,requested_slots=10,free_temp_bytes=30*1024**3)
        self.assertEqual([len(x) for x in waves],[2,1])
        self.assertEqual([g["id"] for wave in waves for g in wave],
                         [g["id"] for g in games])

    def test_explicit_concurrency_ceiling(self):
        games=[_game(i) for i in range(10)]
        waves,_=_storage_waves(games,requested_slots=3,free_temp_bytes=32*1024**3)
        self.assertEqual([len(w) for w in waves],[3,3,3,1])

    def test_insufficient_space_rejected_before_launch(self):
        with self.assertRaises(ComparativeStudyError):
            _storage_waves([_game(0,2*1024**3)],
                           requested_slots=10,free_temp_bytes=3*1024**3)


if __name__=="__main__":
    unittest.main()
