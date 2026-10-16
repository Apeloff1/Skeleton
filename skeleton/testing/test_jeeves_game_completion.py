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


def test_identical_failed_gate_does_not_inflate_evidence_counter(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    assert initialize(root)["ok"]
    const_digest = "a" * 64
    monkeypatch.setattr(prod, "_probe", lambda *args:
                        ("failed", const_digest, "canonical_source", "unchanged source"))
    result = run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                           "--gate", "source_integrity", "--passes", "8"])
    assert result["ok"]
    assert result["recorded_events"] == 1
    assert result["observations"][-1]["new_evidence"] is False
    again = run_game_cli(["jeeves", "production-cycle", "--project", str(root),
                          "--gate", "source_integrity", "--passes", "2"])
    assert again["recorded_events"] == 1
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
    pixels = bytes((x * 13 % 256, x * 29 % 256, x * 7 % 256, 255)
                   for x in range(9) for _ in range(1))
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
