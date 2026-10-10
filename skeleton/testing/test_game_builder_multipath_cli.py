"""Offline, fail-closed user-facing CLI scenarios for real route design."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from skeleton.ai.game_builder.multipath_cli import main
from skeleton.ai.game_builder.multipath_design import RouteProblem, cycle_rank

GRID = [
    "#########",
    "#S..C..G#",
    "#.......#",
    "#.#.#.#.#",
    "#...H...#",
    "#.#.#.#.#",
    "#.......#",
    "#.......#",
    "#########",
]


def _write(tmp_path: Path, rows=GRID) -> Path:
    path = tmp_path / "owned-level.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    return path


def test_inspect_reports_actual_loops_and_no_qualified_human_playtest(tmp_path, capsys):
    path = _write(tmp_path)
    assert main(["--input", str(path), "--mode", "inspect"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "analyzed"
    assert payload["report"]["independent_topological_loops"] > 0
    assert payload["report"]["safe_solution_steps"] == 6
    assert payload["report"]["human_enjoyment_verified"] is False


def test_solve_outputs_replayable_routes_without_false_native_binary(tmp_path, capsys):
    path = _write(tmp_path)
    assert main(["--input", str(path), "--mode", "solve",
                 "--portfolio-size", "3"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "solved"
    assert result["minimum_safe_moves"] == 6
    assert result["minimum_safe_actions"] == ["right"] * 6
    assert len(result["solutions"]) >= 2
    assert result["native_binary_verified"] is False
    assert result["player_enjoyment_verified"] is False


def test_evolution_requires_explicit_authority_and_emits_replay_bound_design(tmp_path, capsys):
    path = _write(tmp_path)
    base = RouteProblem.from_rows(GRID)
    arguments = [
        "--input", str(path), "--mode", "evolve", "--min-loops",
        str(cycle_rank(base)), "--add-hazards", "1",
    ]
    assert main(arguments) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "rejected"
    assert main(arguments + ["--authorize-edit"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "edited_design_only"
    assert result["result_digest"] != base.digest
    assert result["native_binary_verified"] is False
    assert result["release_authorized"] is False
    assert result["edit_digests"]
    altered = RouteProblem.from_rows(result["rows"])
    assert len(altered.hazards) == len(base.hazards) + 1


@pytest.mark.parametrize("contents", [
    b"",
    b'{"rows":[]}',
    b'{"rows":[],"authority":"approved"}',
    b'{"rows":NaN}',
    b"\xff\xfe",
    b"X" * 16_385,
])
def test_bad_or_overbudget_inputs_fail_closed(tmp_path, capsys, contents):
    path = tmp_path / "bad.json"
    path.write_bytes(contents)
    assert main(["--input", str(path)]) == 2
    result = json.loads(capsys.readouterr().err)
    assert result["status"] == "rejected"
    assert result["reason"] in {"MultipathError", "ValueError"}


def test_file_symlink_is_never_treated_as_original_source(tmp_path, capsys):
    path = _write(tmp_path)
    link = tmp_path / "substituted.json"
    try:
        link.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    assert main(["--input", str(link)]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "rejected"
