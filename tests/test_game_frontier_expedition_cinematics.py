"""Original frame-addressed source cinematics with an executable Godot scene."""
from dataclasses import replace
import pytest
from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_cinematics import (
    CameraKey,Cinematic,Storyboard,original_game_storyboard,
    camera_at,storyboard_frame_receipts,export_storyboard_godot,
)
from tests.test_game_frontier_expedition_godot import world


GDD="c"*64


def test_three_original_cinematics_are_attached_to_real_game_locations():
    w=world()
    board=original_game_storyboard(w,GDD)
    board.validate(w)
    assert len(board.clips)==3
    assert [c.waypoint for c in board.clips]==[
        w.arrival,w.waypoints[1].waypoint_id,w.destinations[0]]
    assert all(len(c.keys)==3 for c in board.clips)
    assert len(board.digest)==64


def test_all_frames_have_real_interpolated_camera_positions():
    clip=original_game_storyboard(world(),GDD).clips[0]
    assert camera_at(clip,0)==clip.keys[0]
    assert camera_at(clip,71)==clip.keys[-1]
    middle=camera_at(clip,17)
    assert middle.x!=clip.keys[0].x
    assert middle.frame==17
    assert clip.keys[0].frame<middle.frame<clip.keys[1].frame
    assert 30<=middle.fov<=115


def test_every_frame_generates_nonrepeated_chained_evidence():
    board=original_game_storyboard(world(),GDD)
    proof=storyboard_frame_receipts(board)
    assert proof["frames_checked"]==216
    assert len(proof["history"])==216
    assert len({row["receipt"] for row in proof["history"]})==216
    assert proof["first"]==proof["history"][0]["receipt"]
    assert proof["last"]==proof["history"][-1]["receipt"]
    assert not proof["native_frames_rendered"]
    assert proof==storyboard_frame_receipts(board)


def test_godot_cinematic_source_has_camera_execution_and_scene_data():
    w=world()
    board=original_game_storyboard(w,GDD)
    files=export_storyboard_godot(board,w)
    assert len(files)==3
    assert "game/frontier/cinematic.tscn" in files
    script=files["game/frontier/cinematic.gd"]
    for key in ("extends Node3D","Camera3D.new()",
                "func play_clip(","camera.look_at(",
                "EXPEDITION_CINEMATIC_COMPLETE"):
        assert key in script


def test_cinematic_rejects_incomplete_unordered_and_foreign_world_sources():
    board=original_game_storyboard(world(),GDD)
    clip=board.clips[0]
    with pytest.raises(ExpeditionError,match="ordered full"):
        replace(clip,keys=(clip.keys[0],clip.keys[0],clip.keys[-1]))
    with pytest.raises(ExpeditionError,match="frame out of range"):
        CameraKey(-1,0,0,0,0,0,0)
    with pytest.raises(ExpeditionError,match="source world"):
        board.validate(world(seed=99) if False else
                       __import__("dataclasses").replace(world(),source_digest="e"*64))


def test_cinematic_replay_rejects_frame_outside_source_timeline():
    clip=original_game_storyboard(world(),GDD).clips[0]
    with pytest.raises(ExpeditionError,match="unavailable"):
        camera_at(clip,72)
    with pytest.raises(ExpeditionError,match="sampling bound"):
        storyboard_frame_receipts(original_game_storyboard(world(),GDD),
                                  sample_stride=0)
