"""Source-bound patrol action guidance and fail-closed forecasts."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_patrol import build_patrol
from skeleton.game.gameplay.harbor_crafting_patrol_guidance import patrol_hints
from skeleton.game.gameplay.harbor_crafting_patrol_cli import main
from skeleton.testing.test_harbor_crafting_patrol import inputs, actions


def test_hints_only_show_replayable_actions():
    source, board = inputs()
    report = build_patrol(source, board, actions()[:3])
    hints = patrol_hints(report)
    assert hints["report_digest"] == report["report_digest"]
    assert hints["goal"] == [2, 1]
    assert {"op": "collect", "objective": "tide_registry"} in [
        option["action"] for option in hints["legal"]
    ]
    for option in hints["legal"]:
        replay = build_patrol(source, board, report["actions"] + [option["action"]])
        assert option["report_digest"] == replay["report_digest"]
        assert option["guards"] == replay["state"]["guards"]
    assert hints["recommended"] in [o["action"] for o in hints["legal"]]


def test_unearned_extract_never_advertised():
    source, board = inputs()
    hints = patrol_hints(build_patrol(source, board, []))
    assert {"op": "extract"} not in [o["action"] for o in hints["legal"]]


def test_terminal_has_no_legal_actions():
    source, board = inputs()
    report = build_patrol(source, board, actions(), require_complete=True)
    hints = patrol_hints(report)
    assert hints["terminal"] is True
    assert hints["legal"] == []
    assert hints["recommended"] is None


def test_recomputed_digest_forgery_rejected():
    source, board = inputs()
    report = build_patrol(source, board, actions()[:3])
    forged = deepcopy(report)
    forged["state"]["score"] = 100
    forged["report_digest"] = digest({k: v for k, v in forged.items()
                                       if k != "report_digest"})
    with pytest.raises(HarborError):
        patrol_hints(forged)


def test_cli_hints_are_user_reachable(tmp_path, capsys):
    import json
    source, board = inputs()
    report = build_patrol(source, board, actions()[:3])
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    assert main(["hint", "--report", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["goal"] == [2, 1]


def test_cli_hint_never_falls_through_to_default_world(tmp_path, capsys, monkeypatch):
    """A report-only command must not open unrelated default source inputs."""
    import json
    from skeleton.game.gameplay import harbor_crafting_patrol_cli as cli

    source, board = inputs()
    report = build_patrol(source, board, actions()[:3])
    path = tmp_path / "patrol.json"
    path.write_text(json.dumps(report))
    read = cli._read
    opened = []

    def guarded_read(filename, maximum):
        opened.append(filename)
        if filename in (str(cli.DEFAULT_SOURCE), str(cli.DEFAULT_BOARD)):
            raise AssertionError("report-only hint must not load default world")
        return read(filename, maximum)

    monkeypatch.setattr(cli, "_read", guarded_read)
    assert cli.main(["hint", "--report", str(path)]) == 0
    assert opened == [str(path)]
    assert json.loads(capsys.readouterr().out)["report_digest"] == report["report_digest"]

def test_harbor_studio_workflow_qualifies_immutable_pr_head():
    """A synthetic merge checkout must not masquerade as exact-head evidence."""
    from pathlib import Path

    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github/workflows/harbor-studio-source-qualification.yml"
    ).read_text(encoding="utf-8")
    expected_ref = 'ref: ${{ github.event.pull_request.head.sha }}'
    expected_guard = 'run: test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"'
    assert workflow.count(expected_ref) == 1
    assert workflow.count(expected_guard) == 1
    assert 'EXPECTED_SHA: ${{ github.event.pull_request.head.sha }}' in workflow
    assert workflow.index(expected_ref) < workflow.index(expected_guard)
    assert "persist-credentials: false" in workflow
    assert "fetch-depth: 1" in workflow
