"""Pack H: forge walk CLI — strict args, era matrix, thermal mode, doctor."""
from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.forge import walk_cli
from skeleton.forge.eras import list_eras
from skeleton.forge.walk_cli import (
    EXIT_FAIL,
    EXIT_OK,
    EXIT_USAGE,
    UsageError,
    parse_walk_args,
    run_doctor,
    run_doctor_checks,
    run_eras,
    run_walk,
)


def _capture():
    lines: list[str] = []
    return lines, lines.append


def test_parse_defaults_match_historical_walk():
    a = parse_walk_args([])
    assert (a.era, a.blend, a.t, a.as_json, a.mode) == ("extraction_now", None, 0.5, False, "ideal")


def test_parse_full_flag_set():
    a = parse_walk_args(["--blend", "soulslike", "roguelike", "--t", "0.25",
                         "--mode", "thermal", "--seed", "abc", "--json", "--steps"])
    assert a.blend == ("soulslike", "roguelike")
    assert a.t == 0.25 and a.mode == "thermal" and a.seed == "abc"
    assert a.as_json and a.steps


@pytest.mark.parametrize("argv", [
    ["--bogus"],
    ["--era"],
    ["--era", "--json"],
    ["--era", "not_an_era"],
    ["--blend", "soulslike"],
    ["--blend", "soulslike", "nope"],
    ["--t", "abc"],
    ["--t", "1.5"],
    ["--mode", "chaos"],
    ["--all-eras", "--blend", "soulslike", "roguelike"],
])
def test_parse_rejects_bad_input(argv):
    with pytest.raises(UsageError):
        parse_walk_args(argv)


def test_main_walk_usage_error_exits_2(capsys):
    assert main(["walk", "--bogus"]) == EXIT_USAGE
    assert "unknown walk option: --bogus" in capsys.readouterr().out


def test_main_walk_keeps_ci_line_format(capsys):
    assert main(["walk", "--era", "soulslike"]) == EXIT_OK
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("extracted=True t=") and " hops=" in first and " cores=" in first


def test_walk_json_payload_and_full_steps():
    lines, out = _capture()
    assert run_walk(["--era", "soulslike", "--json", "--steps"], out) == EXIT_OK
    p = json.loads(lines[0])
    assert p["passed"] is True and p["label"] == "soulslike" and p["mode"] == "ideal"
    assert p["plan"]["era"] == "soulslike"
    assert p["steps"][0] == {"t": 0.0, "room": "r00", "action": "enter", "detail": "spawn"}
    assert p["steps"][-1]["action"] == "extract"
    assert "_steps_full" not in p


def test_walk_is_deterministic_and_seed_is_echoed():
    a, out_a = _capture()
    b, out_b = _capture()
    run_walk(["--era", "roguelike", "--json", "--seed", "s1"], out_a)
    run_walk(["--era", "roguelike", "--json", "--seed", "s1"], out_b)
    assert a == b
    assert json.loads(a[0])["seed"] == "s1"


def test_walk_thermal_mode_reports_heat():
    lines, out = _capture()
    assert run_walk(["--era", "extraction_now", "--mode", "thermal", "--json"], out) in (EXIT_OK, EXIT_FAIL)
    p = json.loads(lines[0])
    assert p["mode"] == "thermal"
    assert "heat_peak" in p and "vents" in p


def test_blend_walk_label():
    lines, out = _capture()
    assert run_walk(["--blend", "soulslike", "roguelike", "--t", "0.3", "--json"], out) == EXIT_OK
    assert json.loads(lines[0])["label"] == "soulslike+roguelike@0.3"


def test_all_eras_matrix_json_covers_every_era():
    lines, out = _capture()
    rc = run_walk(["--all-eras", "--json"], out)
    m = json.loads(lines[0])
    assert m["total"] == len(list_eras())
    assert [w["label"] for w in m["walks"]] == list_eras()
    assert m["passed"] == m["total"] - len(m["failed"])
    assert rc == (EXIT_FAIL if m["failed"] else EXIT_OK)
    assert m["failed"] == [], f"eras failing the walk: {m['failed']}"


def test_all_eras_exit_1_when_any_walk_fails(monkeypatch):
    real = walk_cli.walk_once

    def flaky(era, **kw):
        p = real(era, **kw)
        if era == "soulslike":
            p = dict(p, passed=False, notes=["forced failure"])
        return p

    monkeypatch.setattr(walk_cli, "walk_once", flaky)
    lines, out = _capture()
    assert run_walk(["--all-eras"], out) == EXIT_FAIL
    assert any(l.startswith("FAIL soulslike") and "forced failure" in l for l in lines)
    assert lines[-1].startswith(f"{len(list_eras()) - 1}/{len(list_eras())}")


def test_single_walk_failure_exits_1_with_notes(monkeypatch):
    real = walk_cli.walk_once
    monkeypatch.setattr(walk_cli, "walk_once",
                        lambda era, **kw: dict(real(era, **kw), passed=False, notes=["no path"]))
    lines, out = _capture()
    assert run_walk(["--era", "soulslike"], out) == EXIT_FAIL
    assert "  note: no path" in lines


def test_eras_text_is_unchanged_and_json_is_parseable():
    text, out_t = _capture()
    assert run_eras([], out_t) == EXIT_OK
    assert len(text) == len(list_eras())
    assert text[0].startswith("extraction_now") and "dps=" in text[0] and "speed=" in text[0]
    js, out_j = _capture()
    assert run_eras(["--json"], out_j) == EXIT_OK
    rows = json.loads(js[0])
    assert [r["era"] for r in rows] == list_eras()
    assert run_eras(["--bogus"], out_t) == EXIT_USAGE


def test_doctor_checks_pass_without_godot(tmp_path):
    rep = run_doctor_checks(out_dir=str(tmp_path / "out"), env={"PATH": ""})
    by = {c.name: c for c in rep.checks}
    assert set(by) == {"eras_compile", "walk_smoke", "output_writable", "godot_binary"}
    assert by["godot_binary"].ok is False and by["godot_binary"].required is False
    assert rep.ok is True


def test_doctor_finds_explicit_godot(tmp_path):
    fake = tmp_path / "godot4"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    rep = run_doctor_checks(out_dir=str(tmp_path), env={"GODOT_BIN": str(fake), "PATH": ""})
    g = next(c for c in rep.checks if c.name == "godot_binary")
    assert g.ok and g.detail == str(fake)


def test_doctor_fails_closed_on_unwritable_output(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    rep = run_doctor_checks(out_dir=str(blocker / "sub"), env={"PATH": ""})
    assert rep.ok is False
    assert next(c for c in rep.checks if c.name == "output_writable").ok is False


def test_doctor_cli_json_and_usage(tmp_path):
    lines, out = _capture()
    assert run_doctor(["--out", str(tmp_path), "--json"], out) == EXIT_OK
    assert json.loads(lines[0])["ok"] is True
    assert run_doctor(["--nope"], out) == EXIT_USAGE
    assert run_doctor(["--out"], out) == EXIT_USAGE


def test_main_dispatches_doctor(tmp_path, capsys):
    assert main(["doctor", "--out", str(tmp_path)]) == EXIT_OK
    assert "doctor: ok" in capsys.readouterr().out


def test_ai_mirror_is_byte_identical():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert (root / "forge" / "walk_cli.py").read_bytes() == (root / "ai" / "forge" / "walk_cli.py").read_bytes()
