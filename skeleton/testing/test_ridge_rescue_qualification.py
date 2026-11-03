"""Focused integrated game acceptance; failures are never reported as passes."""
import pytest

from skeleton.game.gameplay.ridge_rescue.qualification import run_matrix, CONTRACT
from skeleton.game.gameplay.ridge_rescue import qualification as module
from skeleton.game.gameplay.ridge_rescue.qualification_cli import main


def test_complete_product_matrix_runs_real_game_contracts():
    report = run_matrix()
    assert report["schema"] == CONTRACT
    assert report["passed"] is True, report["checks"]
    assert report["completed_checks"] == report["expected_checks"] == 6
    assert report["release_certified"] is False
    assert report["ci_certified"] is False
    assert report["device_certified"] is False
    assert report["checks"]["routebook-choices"]["routes"]["protect-route"]["ending"] == "won:protect"
    assert report["checks"]["workbench-editor"]["ending"] == "won:protect"


def test_failed_contract_cannot_be_hidden(monkeypatch):
    def fail():
        raise ValueError("simulated source mismatch")
    monkeypatch.setattr(module, "_world_contract", fail)
    report = run_matrix()
    assert report["passed"] is False
    assert report["checks"]["world-package"]["status"] == "failed"
    assert report["completed_checks"] == 6
    fast = run_matrix(fail_fast=True)
    assert fast["passed"] is False
    assert fast["completed_checks"] == 1


def test_cli_status_matches_real_product_acceptance(capsys):
    status = main([])
    import json
    report = json.loads(capsys.readouterr().out)
    assert status == (0 if report["passed"] else 1)
    assert report["release_certified"] is False


def test_invalid_matrix_option_refused():
    with pytest.raises(ValueError):
        run_matrix(fail_fast=1)
