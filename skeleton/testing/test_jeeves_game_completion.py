"""Jeeves resumed production and pixel-accurate upscaling contract tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.developer.game_cli import run_game_cli
from skeleton.developer import jeeves_game_production as prod
from skeleton.jeeves.game_console_assets import png_rgba, decode_png


def workspace(tmp_path: Path) -> Path:
    result = run_game_cli(["init", "persistent-game", "--dir", str(tmp_path),
                           "--vision", "An original production-scale adventure"])
    assert result["ok"], result
    return tmp_path / "persistent-game"


def initialize(root: Path) -> dict:
    return run_game_cli(["jeeves", "production-init", "--project", str(root),
                         "--target", "eight_bit_tile_1983", "--genre", "Platformer",
                         "--period", "1985-1989"])


def test_indefinite_project_lifetime_and_immutable_quality_policy(tmp_path):
    root = workspace(tmp_path)
    first = initialize(root)
    assert first["ok"], first
    assert not first["existing"]
    assert initialize(root)["existing"]
    status = run_game_cli(["jeeves", "production-status", "--project", str(root)])
    assert status["no_lifetime_attempt_limit"] is True
    assert status["no_automatic_evidence_pruning"] is True
    assert status["quality_floor"] == 90
    assert status["remaining_gates"] == len(prod.REQUIRED_GATES)
    assert status["project_complete"] is False
    policy = root / ".jeeves" / "production" / "policy.json"
    before = json.loads(policy.read_text())
    assert before["total_attempt_cap"] is None
    assert before["project_deadline"] is None
    assert before["market_dual_top_quartile"] is True
    before["asset_qa_floor"] = 80
    policy.write_text(json.dumps(before), encoding="utf-8")
    assert not run_game_cli(["jeeves", "production-status",
                             "--project", str(root)])["ok"]


def test_resumable_failure_retries_are_appended_without_total_cap(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    assert initialize(root)["ok"]
    counter = {"n": 0}
    def probe(_root, policy, gate):
        counter["n"] += 1
        receipt = hashlib.sha256(str(counter["n"]).encode()).hexdigest()
        return ("failed", receipt, "canonical_source", "Still fails: restore prerequisites")
    monkeypatch.setattr(prod, "_probe", probe)
    for _ in range(4):
        outcome = run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                                "--gate", "source_integrity", "--passes", "8"])
        assert outcome["ok"], outcome
        assert not outcome["project_complete"]
        assert outcome["quality_threshold_lowered"] is False
    status = run_game_cli(["jeeves", "production-status", "--project", str(root)])
    assert status["recorded_events"] == 32
    assert status["no_lifetime_attempt_limit"] is True
    assert status["passed_gates"] == 0
    assert status["remaining_gates"] == len(prod.REQUIRED_GATES)
    # A new process reading the journal has the same chained evidence.
    assert prod.status(root)["recorded_events"] == status["recorded_events"]
    first = root / ".jeeves" / "production" / "events" / "000000000001.json"
    assert first.is_file()


def test_identical_failed_gate_records_every_parse_without_claiming_novelty(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    assert initialize(root)["ok"]
    const_digest = "a" * 64
    monkeypatch.setattr(prod, "_probe", lambda *args:
                        ("failed", const_digest, "canonical_source", "unchanged source"))
    result = run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                           "--gate", "source_integrity", "--passes", "8"])
    assert result["ok"]
    assert result["recorded_events"] == 8
    assert result["observations"][0]["new_evidence"] is True
    assert result["observations"][-1]["new_evidence"] is False
    again = run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                          "--gate", "source_integrity", "--passes", "2"])
    assert again["recorded_events"] == 10
    assert all(not item["new_evidence"] for item in again["observations"])
    assert not again["project_complete"]


def test_event_hash_chain_rejects_tampering_or_deleted_history(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    assert initialize(root)["ok"]
    n = {"v": 0}
    def probe(*args):
        n["v"] += 1
        return ("failed", hashlib.sha256(str(n["v"]).encode()).hexdigest(),
                "canonical_source", "evidence changed")
    monkeypatch.setattr(prod, "_probe", probe)
    assert run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                         "--gate", "source_integrity", "--passes", "2"])["recorded_events"] == 2
    first = root / ".jeeves" / "production" / "events" / "000000000001.json"
    record = json.loads(first.read_text())
    record["outcome"] = "passed"
    first.write_text(json.dumps(record), encoding="utf-8")
    denied = run_game_cli(["jeeves", "production-status", "--project", str(root)])
    assert denied["ok"] is False
    assert "hash mismatch" in denied["error"]


def test_observing_boot_never_marks_complete_game(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    initialize(root)
    monkeypatch.setattr(prod, "_probe", lambda *args:
                        ("passed", "b" * 64, "godot_boot", "verified headless boot"))
    result = run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                           "--gate", "runtime_boot"])
    assert result["ok"]
    status = run_game_cli(["jeeves", "production-status", "--project", str(root)])
    assert status["passed_gates"] == 1
    assert not status["project_complete"]
    assert "full_playthrough" in status["next_work"]


def test_upscale_png_really_scales_and_preserves_colors(tmp_path):
    root = workspace(tmp_path)
    pixels = bytes((
        255, 0, 0, 255, 0, 255, 0, 255,
        0, 0, 255, 255, 255, 255, 0, 255,
    ))
    raw = png_rgba(pixels, 2, 2)
    src = root / "assets" / "source.png"
    src.write_bytes(raw)
    plan = run_game_cli(["jeeves", "fidelity-plan", "--project", str(root),
                         "--target", "eight_bit_tile_1983"])
    assert plan["ok"], plan
    assert "integer_scale_only" in plan["art_direction_rules"]
    cmd = ["jeeves", "upscale", "--project", str(root),
           "--target", "eight_bit_tile_1983", "--source", "assets/source.png",
           "--output", "assets/output.png", "--mode", "nearest", "--factor", "2"]
    dry = run_game_cli(cmd + ["--dry-run"])
    assert dry["ok"], dry
    assert not (root / "assets" / "output.png").exists()
    made = run_game_cli(cmd)
    assert made["ok"], made
    assert made["source_unchanged"]
    assert made["no_new_colors"]
    assert made["dimensions_out"] == [4, 4]
    assert made["input_sha256"] == hashlib.sha256(raw).hexdigest()
    assert not made["production_qualified"]
    w, h, rgba = decode_png((root / "assets" / "output.png").read_bytes())
    assert (w, h) == (4, 4)
    # Nearest pixel blocks are exactly 2x2 copies of each original pixel.
    for y in range(4):
        for x in range(4):
            p = (y * 4 + x) * 4
            q = ((y // 2) * 2 + (x // 2)) * 4
            assert rgba[p:p+4] == pixels[q:q+4]
    assert src.read_bytes() == raw
    assert not run_game_cli(cmd)["ok"]  # never overwrite


def test_edge_aware_scale2x_uses_only_existing_palette(tmp_path):
    root = workspace(tmp_path)
    pixels = b"".join(bytes((x * 13 % 256, x * 29 % 256,
                             x * 7 % 256, 255)) for x in range(9))
    (root / "assets" / "small.png").write_bytes(png_rgba(pixels, 3, 3))
    value = run_game_cli(["jeeves", "upscale", "--project", str(root),
                          "--target", "sixteen_bit_raster_1989",
                          "--source", "assets/small.png", "--output", "assets/large.png",
                          "--mode", "scale2x", "--factor", "4"])
    assert value["ok"], value
    assert value["dimensions_out"] == [12, 12]
    assert value["no_new_colors"]
    assert value["native_console_quality_verified"] is False


@pytest.mark.parametrize("malicious", ["assets/../secrets.png", "/etc/out.png",
                                        "assets\\evil.png"])
def test_upscale_rejects_unsafe_paths(tmp_path, malicious):
    root = workspace(tmp_path)
    (root / "assets" / "source.png").write_bytes(png_rgba(bytes((0,0,0,255)),1,1))
    result = run_game_cli(["jeeves", "upscale", "--project", str(root),
                           "--target", "eight_bit_tile_1983",
                           "--source", "assets/source.png", "--output", malicious])
    assert not result["ok"]


def test_unknown_console_cannot_masquerade_as_supported_hardware(tmp_path):
    root = workspace(tmp_path)
    result = run_game_cli(["jeeves", "fidelity-plan", "--project", str(root),
                           "--target", "fictional_unbuilt_console"])
    assert not result["ok"]



def test_upscale_technical_verifier_reconstructs_all_pixels(tmp_path):
    root = workspace(tmp_path)
    pixels = bytes((17, 42, 86, 255, 200, 120, 63, 255,
                    90, 99, 100, 255, 255, 0, 255, 255))
    (root / "assets" / "source.png").write_bytes(png_rgba(pixels, 2, 2))
    cmd = ["jeeves", "upscale", "--project", str(root),
           "--target", "nes", "--source", "assets/source.png",
           "--output", "assets/upscaled.png", "--mode", "scale2x", "--factor", "2"]
    made = run_game_cli(cmd)
    assert made["ok"], made
    verification = run_game_cli(
        ["jeeves", "upscale-verify", "--project", str(root), "--target", "nes",
         "--source", "assets/source.png", "--output", "assets/upscaled.png",
         "--mode", "scale2x", "--factor", "2", "--passes", "5"]
    )
    assert verification["ok"], verification
    assert verification["scrutiny_passes"] == 5
    assert len(verification["checks"]) == 5
    assert all(row["algorithm_reconstruction_exact"] for row in verification["checks"])
    assert all(not row["evidence_independent"] for row in verification["checks"])
    bad = root / "assets" / "upscaled.png"
    w, h, rgba = decode_png(bad.read_bytes())
    corrupted = bytearray(rgba)
    corrupted[0] ^= 0x10
    bad.write_bytes(png_rgba(bytes(corrupted), w, h))
    result = run_game_cli(
        ["jeeves", "upscale-verify", "--project", str(root), "--target", "nes",
         "--source", "assets/source.png", "--output", "assets/upscaled.png",
         "--mode", "scale2x", "--factor", "2"]
    )
    assert result["ok"] is False
    assert "differ" in result["error"]


def test_legacy_pixel_aspect_and_pillarboxes_are_not_stretched(tmp_path):
    root = workspace(tmp_path)
    plan = run_game_cli([
        "jeeves", "display-plan", "--project", str(root),
        "--target", "nes", "--native-width", "256", "--native-height", "240",
        "--screen-width", "1920", "--screen-height", "1080",
    ])
    assert plan["ok"], plan
    assert plan["integer_scale"] == 4
    assert plan["presented_pixels"] == [1024, 960]
    assert plan["letterbox_pixels"] == {
        "left": 448, "right": 448, "top": 60, "bottom": 60}
    assert plan["stretching_permitted"] is False
    assert plan["tiled_or_gpu_render_required"] is False
    par = run_game_cli([
        "jeeves", "display-plan", "--project", str(root),
        "--target", "nes", "--native-width", "128", "--native-height", "120",
        "--screen-width", "1920", "--screen-height", "1080",
        "--pixel-aspect-num", "3", "--pixel-aspect-den", "2",
    ])
    assert par["ok"], par
    assert par["physical_block_size"] == [12, 8]
    assert par["presented_pixels"] == [1536, 960]
    assert par["aspect_ratio_preserved"] is True
    assert not run_game_cli([
        "jeeves", "display-plan", "--project", str(root),
        "--target", "nes", "--native-width", "256", "--native-height", "240",
        "--screen-width", "1920", "--screen-height", "1080",
        "--pixel-aspect-num", "0",
    ])["ok"]


def test_real_console_inventory_names_every_declared_target_and_gaps(tmp_path):
    root = workspace(tmp_path)
    matrix = run_game_cli(["jeeves", "fidelity-matrix", "--project", str(root)])
    assert matrix["ok"], matrix
    assert matrix["declared_console_targets"] >= 20
    by_id = {r["target_id"]: r for r in matrix["targets"]}
    assert "nes" in by_id and "ps1" in by_id
    assert by_id["nes"]["upscale_kind"] == "native_grid_integer_and_scale2x"
    assert by_id["ps1"]["upscale_kind"] == "texture_plus_bounded_reference_raster"
    assert by_id["ps1"]["historical_3d_reference_raster"] is True
    assert by_id["ps5"]["modern_render_graph_evidence"] is True
    assert matrix["any_console_fully_certified_by_this_tool"] is False
    assert matrix["missing_native_production_qualifications"] == matrix["declared_console_targets"]


def test_repair_rechecks_original_gate_and_does_not_overwrite_quality_bar(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    initialize(root)
    checks = {"n": 0, "repairs": 0}
    def probe(*args):
        checks["n"] += 1
        return ("failed" if checks["n"] == 1 else "passed",
                hashlib.sha256(str(checks["n"]).encode()).hexdigest(),
                "canonical_source", "quality gate rechecked")
    def build(root, options):
        checks["repairs"] += 1
        assert options.overwrite is True
        assert options.repair_mode == "apply"
        return {"ok": True}
    monkeypatch.setattr(prod, "_probe", probe)
    monkeypatch.setattr("skeleton.developer.game_cli._build", build)
    result = run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                           "--gate", "source_integrity", "--repair-generated", "--passes", "2"])
    assert result["ok"], result
    assert checks["repairs"] == 1
    assert checks["n"] >= 2
    assert result["repairs_attempted"] == ["source_integrity"]
    assert result["quality_threshold_lowered"] is False
    assert result["project_complete"] is False


def test_unknown_quality_gate_cannot_be_deleted_or_lowered(tmp_path):
    root = workspace(tmp_path)
    initialize(root)
    result = run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                           "--gate", "remove_gameplay_checks", "--passes", "3"])
    assert not result["ok"]
    assert not run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                             "--passes", "0"])["ok"]
    assert not run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                             "--passes", "9"])["ok"]



def test_only_observed_real_checker_fail_to_pass_pairs_enter_training_queue(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    initialize(root)
    result_seq = iter(("failed", "passed", "failed", "passed"))
    calls = {"count": 0}
    def probe(*args):
        calls["count"] += 1
        return (
            next(result_seq),
            hashlib.sha256(str(calls["count"]).encode()).hexdigest(),
            "canonical_source",
            "real source evidence rechecked",
        )
    monkeypatch.setattr(prod, "_probe", probe)
    assert run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                         "--gate", "source_integrity", "--passes", "4"])["ok"]
    reviewed = run_game_cli(["jeeves", "production-training", "--project", str(root),
                             "--page", "0", "--page-size", "1"])
    assert reviewed["ok"], reviewed
    assert reviewed["total_observed_transitions"] == 2
    assert len(reviewed["examples"]) == 1
    assert reviewed["next_page"] == 1
    assert reviewed["examples"][0]["model_weights_updated"] is False
    assert reviewed["examples"][0]["eligible_for_training_promotion"] is False
    second = run_game_cli(["jeeves", "production-training", "--project", str(root),
                           "--page", "1", "--page-size", "1"])
    assert second["total_observed_transitions"] == 2
    assert second["next_page"] is None
    assert second["examples"][0]["failed_event_sha256"] != reviewed["examples"][0]["failed_event_sha256"]
    assert second["all_history_still_retained"]
    assert not second["neural_network_training_performed"]


def test_production_training_does_not_classify_operator_reviews_as_training_proof(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    initialize(root)
    n = {"v": 0}
    def probe(*args):
        n["v"] += 1
        return ("failed" if n["v"] == 1 else "passed",
                hashlib.sha256(str(n["v"]).encode()).hexdigest(),
                "operator_observation", "self-reported original artwork quality")
    monkeypatch.setattr(prod, "_probe", probe)
    assert run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                         "--gate", "original_assets", "--passes", "2"])["ok"]
    checked = run_game_cli(["jeeves", "production-training", "--project", str(root)])
    assert checked["ok"] and checked["examples"] == []
    assert checked["total_observed_transitions"] == 0
