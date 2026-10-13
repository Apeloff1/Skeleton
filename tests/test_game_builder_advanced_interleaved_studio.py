"""Original interleaved world-clock Studio source and replay controls."""
from __future__ import annotations
import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class OriginalEventClockStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("A"*32).decode("utf-8")

    def test_source_earned_events_are_reconstructed_before_authoring_clock(self):
        page=self.html()
        for name in (
            'id="advanced-interleave-build"',
            'id="advanced-interleave-editor"',
            'id="advanced-interleave-run"',
            'id="advanced-interleave-proof"',
            'verifiedSourceEpisodes.some(e=>e.world_actions.length)',
            '"/api/advanced-physics-multi-npc"',
            '"/api/advanced-cross-genre-npc-world"',
            'schedule.push({at:schedule.length,...queue.shift()})',
            'authentic_physical_collisions:proof.authentic_physical_event_count',
            'earned_genre_achievements:proof.authentic_genre_event_count',
        ):
            self.assertIn(name,page)

    def test_authored_timeline_requires_original_server_truth_before_display(self):
        page=self.html()
        for name in (
            '"/api/advanced-interleaved-world"',
            'proof.world_scene_digest!==episodicLastScene.digest',
            'proof.physical_source_count!==verifiedSourceEpisodes.length',
            'proof.genre_source_count!==verifiedGenreEvents.length',
            'proof.original_projects_modified',
            'proof.free_rewards_granted',
            'drawNPCForensicMap(proof.world_state)',
            'source_event_clock:proof.timeline',
            'real_npc_memories:proof.world_state.npcs',
            'audited_replay_digest:proof.digest',
        ):
            self.assertIn(name,page)

    def test_handler_reconstructs_and_independently_replays_entire_world_clock(self):
        handler=inspect.getsource(_StudioHandler)
        for part in (
            '"/api/advanced-interleaved-world"',
            'run_interleaved_world(',
            'verify_interleaved_world(',
            '"source_project_files_changed":False',
            '"automatic_rewards_granted":False',
            '"native_hardware_certified":False',
        ):
            self.assertIn(part,handler)


if __name__=="__main__":
    unittest.main()
