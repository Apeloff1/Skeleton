"""Real source replay across cohorts and fail-closed preadmission coverage."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import os
import shutil

import pytest

from skeleton.ai.game_builder.dual_runtime_export import (
    export_dual_runtime_package, render_dual_runtime_package,
)
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.ai.game_builder.offline_export_batch import SCHEMA as BATCH_SCHEMA, MAX_TOTAL_VERIFIED_BYTES
from skeleton.ai.game_builder.offline_portfolio import (
    SCHEMA, PortfolioBudget, PortfolioError, verify_portfolio,
)
from skeleton.ai.game_builder.offline_portfolio_cli import main


def write_index(path, value):
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


@pytest.fixture
def portfolio(tmp_path):
    root = tmp_path / "portfolio"
    root.mkdir()
    cohorts = []
    for i in range(2):
        directory = root / f"cohort-{i}"
        directory.mkdir()
        intent = GameBuildIntent(
            project_id=f"original-portfolio-{i}", title=f"Original Portfolio {i}",
            subtitle="Independent portfolio test", seed=1729 + i,
            levels=1, width=9, height=9, collectibles_per_level=1,
            hazards_per_level=0, starting_health=3,
        )
        game = compile_original_game(intent, authorized=True)
        package = render_dual_runtime_package(game, authorized=True)
        exported = export_dual_runtime_package(package, directory / "game", authorized=True)
        pin = sha256((exported / "release.json").read_bytes()).hexdigest()
        batch_pin = write_index(directory / "batch.json", {
            "schema": BATCH_SCHEMA, "packages": [
                {"project_id": intent.project_id, "package_dir": "game", "release_sha256": pin}
            ],
        })
        cohorts.append({"cohort_id": f"cohort-{i}", "directory": directory.name,
                        "index_sha256": batch_pin})
    pin = write_index(root / "portfolio.json", {"schema": SCHEMA, "cohorts": cohorts})
    return root, pin, cohorts


def test_real_multi_cohort_replay(portfolio):
    root, pin, _ = portfolio
    first = verify_portfolio(root, expected_index_sha256=pin, authorized=True)
    assert first["verified_cohorts"] == first["verified_packages"] == 2
    assert first["verified_bytes"] > 0
    assert first["verified_files"] > 0
    assert first["replayed_actions"] > 0
    assert not first["godot_executed"] and not first["release_certified"]
    assert first == verify_portfolio(root, expected_index_sha256=pin, authorized=True)


def test_operator_and_budget_reject_before_replay(portfolio, monkeypatch):
    from skeleton.ai.game_builder import offline_portfolio as owner
    root, pin, _ = portfolio
    def forbidden(*args, **kwargs):
        pytest.fail("replay before admission")
    monkeypatch.setattr(owner, "verify_export_batch", forbidden)
    with pytest.raises(PermissionError):
        verify_portfolio(root, expected_index_sha256=pin, authorized=False)
    with pytest.raises(PortfolioError):
        verify_portfolio(root, expected_index_sha256=pin, authorized=True,
                         budget=PortfolioBudget(packages=1))
    with pytest.raises(PortfolioError):
        verify_portfolio(root, expected_index_sha256=pin, authorized=True,
                         budget=PortfolioBudget(verified_bytes=MAX_TOTAL_VERIFIED_BYTES))


def test_duplicate_project_across_cohorts_rejected(portfolio, monkeypatch):
    from skeleton.ai.game_builder import offline_portfolio as owner
    root, _, rows = portfolio
    left = json.loads((root / "cohort-0" / "batch.json").read_bytes())
    rows[1]["index_sha256"] = write_index(root / "cohort-1" / "batch.json", left)
    pin = write_index(root / "portfolio.json", {"schema": SCHEMA, "cohorts": rows})
    monkeypatch.setattr(owner, "verify_export_batch",
                        lambda *a, **k: pytest.fail("duplicate replay"))
    with pytest.raises(PortfolioError, match="duplicate project"):
        verify_portfolio(root, expected_index_sha256=pin, authorized=True)


@pytest.mark.parametrize("attack", ["index", "unlisted", "source", "duplicate-cohort", "traversal"])
def test_hostile_portfolio(portfolio, attack):
    root, pin, rows = portfolio
    if attack == "index":
        pin = "0" * 64
    elif attack == "unlisted":
        (root / "unlisted").mkdir()
    elif attack == "source":
        (root / "cohort-1" / "game" / "index.html").write_text("tampered")
    elif attack == "duplicate-cohort":
        rows[1]["cohort_id"] = rows[0]["cohort_id"]
        pin = write_index(root / "portfolio.json", {"schema": SCHEMA, "cohorts": rows})
    else:
        rows[1]["directory"] = "../cohort-1"
        pin = write_index(root / "portfolio.json", {"schema": SCHEMA, "cohorts": rows})
    with pytest.raises(PortfolioError):
        verify_portfolio(root, expected_index_sha256=pin, authorized=True)


@pytest.mark.skipif(os.name != "posix", reason="descriptor safety")
def test_replacement_of_verified_cohort_fenced(portfolio, monkeypatch, tmp_path):
    from skeleton.ai.game_builder import offline_portfolio as owner
    root, pin, _ = portfolio
    real = owner.verify_export_batch
    calls = 0
    def swap(*args, **kwargs):
        nonlocal calls
        receipt = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            moved = tmp_path / "moved"
            (root / "cohort-0").rename(moved)
            shutil.copytree(moved, root / "cohort-0")
        return receipt
    monkeypatch.setattr(owner, "verify_export_batch", swap)
    with pytest.raises(PortfolioError, match="changed"):
        verify_portfolio(root, expected_index_sha256=pin, authorized=True)


def test_installed_route_real_receipt(portfolio, tmp_path, capsys):
    from skeleton.__main__ import main as root_main
    root, pin, _ = portfolio
    target = tmp_path / "portfolio-receipt.json"
    assert root_main(["studio-portfolio-verify", "--root", str(root),
                      "--expected-index-sha256", pin, "--trusted-local-operator",
                      "--receipt-output", str(target)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert json.loads(target.read_bytes()) == result
    assert main(["--root", str(root), "--expected-index-sha256", pin]) == 2
