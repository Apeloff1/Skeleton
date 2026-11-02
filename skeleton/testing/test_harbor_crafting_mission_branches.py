"""Branching mission portfolios, replay custody and portable CLI acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_mission_branches import (
    mission_branch_report, verify_mission_branch_report,
)
from skeleton.game.gameplay.harbor_crafting_sessions import branch_portfolio

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def source():
    return load_source(ROOT / "harbor_lantern_quay.json")


def board():
    return decode((ROOT / "harbor_lantern_quay_missions.json").read_bytes())


def portfolio():
    root = export_bundle(source(), demo_actions()[:-1])
    return branch_portfolio(root, {
        "beacon": [{"op": "choose", "choice": "signal"}],
        "shelter": [{"op": "choose", "choice": "shelter"}],
    })


def test_source_to_save_branches_to_distinct_earned_mission_scorecards():
    report = mission_branch_report(portfolio(), board())
    assert [entry["name"] for entry in report["entries"]] == ["beacon", "shelter"]
    assert [entry["points"] for entry in report["entries"]] == [60, 30]
    assert [entry["ending"] for entry in report["entries"]] == ["beacon", "safe_harbor"]
    assert verify_mission_branch_report(decode(canonical(report))) == [
        {key: entry[key] for key in ("name", "ending", "points", "completed", "terminal_digest")}
        for entry in report["entries"]
    ]
    assert canonical(mission_branch_report(portfolio(), board())) == canonical(report)


@pytest.mark.parametrize("mutation", [
    lambda r: r["entries"][0].update({"points": 10000}),
    lambda r: r["entries"][0]["completed"].append("forged"),
    lambda r: r["entries"][1]["report"].update({"points": 900}),
    lambda r: r["portfolio"]["entries"][0]["bundle"]["state"].update({"reputation": 99}),
    lambda r: r.update({"source_digest": "f" * 64}),
])
def test_resealed_branch_score_forgeries_fail(mutation):
    report = mission_branch_report(portfolio(), board())
    mutation(report)
    report["report_digest"] = digest({k: v for k, v in report.items() if k != "report_digest"})
    with pytest.raises(HarborError):
        verify_mission_branch_report(report)


def test_cli_mission_report_verify_solve_and_branch_comparison(tmp_path):
    source_path = ROOT / "harbor_lantern_quay.json"
    board_path = ROOT / "harbor_lantern_quay_missions.json"
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_bytes(canonical(export_bundle(source(), demo_actions())))
    commands = [
        "mission-report", "verify-mission-report", "solve-missions",
        "mission-portfolio", "verify-mission-portfolio",
    ]
    outputs = {}
    report_path = tmp_path / "mission.json"
    portfolio_path = tmp_path / "portfolio.json"
    branch_path = tmp_path / "branch-report.json"
    portfolio_path.write_bytes(canonical(portfolio()))
    for command in commands:
        args = [
            sys.executable, "-m", "scripts.game.harbor_crafting", command,
            "--source", str(source_path), "--missions", str(board_path),
        ]
        if command == "mission-report":
            args += ["--bundle", str(bundle_path), "--require-all"]
        elif command == "verify-mission-report":
            args += ["--report", str(report_path), "--require-all"]
        elif command == "mission-portfolio":
            args += ["--bundle", str(portfolio_path)]
        elif command == "verify-mission-portfolio":
            args += ["--report", str(branch_path)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, (command, result.stderr)
        outputs[command] = json.loads(result.stdout)
        if command == "mission-report":
            report_path.write_text(result.stdout, encoding="utf-8")
        if command == "mission-portfolio":
            branch_path.write_text(result.stdout, encoding="utf-8")
    assert outputs["mission-report"]["points"] == 60
    assert outputs["verify-mission-report"]["verified"]
    assert outputs["solve-missions"]["points"] == 60
    assert outputs["verify-mission-portfolio"]["verified"]
    assert [e["points"] for e in outputs["verify-mission-portfolio"]["branches"]] == [60, 30]


def test_cli_rejects_forged_report_without_success_receipt(tmp_path):
    forged = mission_branch_report(portfolio(), board())
    forged["entries"][0]["points"] = 999
    forged["report_digest"] = digest({k: v for k, v in forged.items() if k != "report_digest"})
    path = tmp_path / "forged.json"
    path.write_bytes(canonical(forged))
    result = subprocess.run(
        [sys.executable, "-m", "scripts.game.harbor_crafting", "verify-mission-portfolio",
         "--report", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
    assert "mission portfolio replay mismatch" in result.stderr


def test_checkpoint_and_resume_cli_preserve_earned_mission_history(tmp_path):
    source_path = ROOT / "harbor_lantern_quay.json"
    board_path = ROOT / "harbor_lantern_quay_missions.json"
    actions = demo_actions()
    root = export_bundle(source(), actions[:10])
    root_path = tmp_path / "checkpoint.json"
    root_path.write_bytes(canonical(root))
    suffix_path = tmp_path / "suffix.json"
    suffix_path.write_bytes(canonical(actions[10:]))
    base = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    checkpoint = subprocess.run(
        base + ["mission-checkpoint", "--bundle", str(root_path), "--tick", "5",
                "--missions", str(board_path), "--source", str(source_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert checkpoint.returncode == 0, checkpoint.stderr
    assert json.loads(checkpoint.stdout)["completed"] == ["salvage"]
    resumed = subprocess.run(
        base + ["mission-resume", "--bundle", str(root_path),
                "--actions", str(suffix_path),
                "--expected-terminal-digest", root["terminal_digest"],
                "--missions", str(board_path), "--source", str(source_path),
                "--require-all"],
        capture_output=True, text=True, timeout=30,
    )
    assert resumed.returncode == 0, resumed.stderr
    result = json.loads(resumed.stdout)
    assert result["points"] == 60
    assert result["bundle"]["state"]["ending"] == "beacon"
    denied = subprocess.run(
        base + ["mission-resume", "--bundle", str(root_path),
                "--actions", str(suffix_path), "--expected-terminal-digest", "0" * 64,
                "--missions", str(board_path), "--source", str(source_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert denied.returncode == 2
    assert "stale checkpoint" in denied.stderr
