"""Regression matrix for seven real original-game post-production stages."""
from copy import deepcopy
from dataclasses import replace
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_visual_lab import (
    VisualFrame, original_procedural_preview_frames,
)
from skeleton.jeeves.game_frontier_postproduction import (
    PostProductionPolicy, compile_frame_postproduction, verify_frame_postproduction,
)
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile, author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_cinematics import original_game_storyboard
from skeleton.jeeves.game_frontier_expedition_campaign import (
    compile_original_campaign, verify_original_campaign,
)

WORLD = "8" * 64
GDD = "a" * 64


def original_frames():
    return original_procedural_preview_frames(WORLD, frames=7, width=12, height=10)


def test_seven_stages_generate_actual_ppm_and_source_proof():
    frames = original_frames()
    built = compile_frame_postproduction(frames, expected_world=WORLD)
    proof = built["report"]
    assert proof["input_frames"] == 7
    assert len(proof["spatial"]) == 7
    assert len(proof["temporal"]) == 6
    assert len(proof["journal"]) == 7
    assert proof["receipt_head"] == proof["journal"][-1]["receipt"]
    assert proof["contact_sheet"]["frame_ids"] == proof["selected_keyframes"]
    assert built["contact_sheet_ppm"].startswith("P3\n")
    assert len(proof["contact_sheet"]["sha256"]) == 64
    assert proof["source_kind"] == "original_procedural_preview"
    assert not proof["native_renderer_attested"]
    assert not proof["audio_video_muxed"]
    assert not proof["model_training_performed"]
    assert not proof["production_publication_authorized"]
    assert verify_frame_postproduction(frames, built, expected_world=WORLD)["verified"]


def test_exposure_histogram_and_edge_gradient_are_real_pixel_calculations():
    f1 = VisualFrame(WORLD, 0, 2, 2, bytes([0, 0, 0] * 4),
                     "original_procedural_preview")
    f2 = VisualFrame(WORLD, 1, 2, 2, bytes([255, 255, 255] * 4),
                     "original_procedural_preview")
    report = compile_frame_postproduction((f1, f2), expected_world=WORLD)["report"]
    assert report["spatial"][0]["shadow_fraction"] == 1
    assert report["spatial"][0]["exposure_mean"] == 0
    assert report["spatial"][1]["highlight_fraction"] == 1
    assert report["spatial"][1]["exposure_mean"] == 255
    assert report["temporal"][0]["normalized_pixel_change"] == 1
    assert report["temporal"][0]["scene_cut_candidate"]
    assert "severely_clipped_exposure" in report["issues"]


def test_temporal_freeze_and_discontinuous_capture_are_reported():
    a = VisualFrame(WORLD, 0, 2, 2, bytes([9, 8, 7] * 4),
                    "original_procedural_preview")
    b = replace(a, frame=4)
    r = compile_frame_postproduction((a, b), expected_world=WORLD)["report"]
    assert r["temporal"][0]["frozen"]
    assert r["temporal"][0]["unobserved_intermediate_frames"] == 3
    assert "frozen_or_unchanged_frame_interval" in r["issues"]
    assert "incomplete_frame_coverage" in r["issues"]


def test_frame_identity_cross_world_and_type_laundering_rejected():
    f = original_frames()
    with pytest.raises(ExpeditionError, match="mixed world"):
        compile_frame_postproduction(f[:2] + (replace(f[2], game_digest="b"*64),),
                                     expected_world=WORLD)
    with pytest.raises(ExpeditionError, match="mixed world"):
        compile_frame_postproduction(f[:2] + (replace(f[2], kind="original_runtime_capture"),),
                                     expected_world=WORLD)
    with pytest.raises(ExpeditionError, match="reordered"):
        compile_frame_postproduction((f[1], f[0]), expected_world=WORLD)
    with pytest.raises(ExpeditionError, match="scope"):
        compile_frame_postproduction(f[:1], expected_world=WORLD)


def test_contact_sheet_keyframes_are_bounded_and_replay_deterministic():
    f = original_frames()
    p = PostProductionPolicy(max_selected=3, min_frame_spacing=2)
    x = compile_frame_postproduction(f, expected_world=WORLD, policy=p)
    y = compile_frame_postproduction(f, expected_world=WORLD, policy=p)
    assert x == y
    assert len(x["report"]["selected_keyframes"]) <= 3
    assert x["report"]["selected_keyframes"][0] == 0
    assert x["report"]["selected_keyframes"][-1] == 6
    assert len(x["report"]["contact_sheet"]["frame_ids"]) <= 3


def test_fail_closed_resource_limits_stop_mosaic_explosion():
    f = original_procedural_preview_frames(WORLD, frames=5, width=64, height=64)
    with pytest.raises(ExpeditionError, match="pixel budget"):
        compile_frame_postproduction(f, expected_world=WORLD,
                                     policy=PostProductionPolicy(max_sheet_pixels=1024))


def test_cinematic_source_annotations_are_not_render_attestation():
    f = original_frames()
    w = author_archipelago("original", WORLD, ArchipelagoProfile(seed=5, islands=5))
    board = original_game_storyboard(w, GDD)
    clips = [x.clip_id for x in board.clips]
    # Rebind frames to this independently authored world.
    orig = original_procedural_preview_frames(w.digest, frames=7)
    anchors = {0: clips[0], 2: clips[1], 6: clips[2]}
    p = compile_frame_postproduction(orig, expected_world=w.digest,
                                     storyboard=board, anchors=anchors)
    assert p["report"]["story"]["complete_storyboard_coverage"]
    assert not p["report"]["story"]["authoritative_clip_attribution"]
    verify_frame_postproduction(orig, p, expected_world=w.digest,
                                storyboard=board, anchors=anchors)
    with pytest.raises(ExpeditionError, match="missing frames"):
        compile_frame_postproduction(orig, expected_world=w.digest, storyboard=board,
                                     anchors={99: clips[0]})
    with pytest.raises(ExpeditionError, match="source-bound"):
        compile_frame_postproduction(f, expected_world=WORLD, storyboard=board,
                                     anchors={0: clips[0]})


def test_adversarial_spatial_statistics_receipt_and_ppm_edits_rejected():
    frames = original_frames()
    original = compile_frame_postproduction(frames, expected_world=WORLD)
    for path in ("spatial", "temporal", "journal", "selected_keyframes"):
        altered = deepcopy(original)
        if path == "spatial":
            altered["report"][path][0]["gradient_strength"] = 10000
        elif path == "temporal":
            altered["report"][path][0]["frozen"] = True
        elif path == "journal":
            altered["report"][path][-1]["receipt"] = "0"*64
        else:
            altered["report"][path].reverse()
        with pytest.raises(ExpeditionError, match="differ"):
            verify_frame_postproduction(frames, altered, expected_world=WORLD)
    altered = deepcopy(original)
    altered["contact_sheet_ppm"] += "# forged"
    with pytest.raises(ExpeditionError, match="differ"):
        verify_frame_postproduction(frames, altered, expected_world=WORLD)


def test_policy_rejects_invalid_spacing_cut_and_freeze():
    with pytest.raises(ExpeditionError, match="threshold"):
        PostProductionPolicy(freeze_fraction=.9, scene_cut_fraction=.2)
    with pytest.raises(ExpeditionError, match="limits"):
        PostProductionPolicy(max_selected=500)
    with pytest.raises(ExpeditionError, match="threshold"):
        PostProductionPolicy(scene_cut_fraction=float("nan"))


def test_campaign_exports_and_independently_recompiles_real_visual_assets():
    candidate = compile_original_campaign("visual_production", gdd_digest=GDD,
                                          seed=17, islands=5)
    manifest = candidate["manifest"]
    files = candidate["files"]
    assert manifest["postproduction_receipt"] == candidate["postproduction"]["report"]["receipt_digest"]
    assert files["game/frontier/contact_sheet.ppm"].startswith("P3\n")
    assert "original_procedural_preview" in files["game/frontier/postproduction.json"]
    assert not manifest["native_rgb_frames_captured_by_compiler"]
    assert verify_original_campaign(candidate, project_id="visual_production",
                                    gdd_digest=GDD, seed=17,
                                    islands=5)["all_source_bytes_verified"]
    forged = deepcopy(candidate)
    forged["files"]["game/frontier/contact_sheet.ppm"] += "0 "
    with pytest.raises(ExpeditionError, match="differs"):
        verify_original_campaign(forged, project_id="visual_production",
                                 gdd_digest=GDD, seed=17, islands=5)
