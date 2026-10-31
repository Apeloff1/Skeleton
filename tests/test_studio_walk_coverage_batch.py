"""Real registered catalog page audit and fail-closed pagination tests."""
from __future__ import annotations

import json
import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_coverage_batch as batch
from skeleton.ai.game_builder.studio_ecosystem_catalog import (
    StudioEcosystemError, list_blueprints,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def test_real_catalog_page_is_deterministic_and_source_bound():
    result = batch.audit_catalog_walk_choices(authorized=True, limit=1)
    assert result == batch.audit_catalog_walk_choices(authorized=True, limit=1)
    assert result["projects_examined"] == 1
    assert result["projects"][0]["project_id"] == list_blueprints()[0]["id"]
    assert result["catalog_digest"] and len(result["catalog_digest"]) == 64
    assert result["audit_digest"] and len(result["audit_digest"]) == 64
    assert result["release_certified"] is False
    assert result["all_branch_combinations_verified"] is False
    assert result["next_offset"] == 1


@pytest.mark.parametrize("offset,limit", [
    (-1, 1), (True, 1), (0, 0), (0, 5), (0, True), (1.0, 1),
])
def test_rejects_invalid_page_contract(offset, limit):
    with pytest.raises(StudioQuestError):
        batch.audit_catalog_walk_choices(
            authorized=True, offset=offset, limit=limit,
        )


def test_denies_unauthorized_before_catalog_read(monkeypatch):
    monkeypatch.setattr(batch, "list_blueprints",
                        lambda **_: pytest.fail("unauthorized catalog read"))
    with pytest.raises(PermissionError):
        batch.audit_catalog_walk_choices(authorized=False)


def test_invalid_project_is_reported_not_certified(monkeypatch):
    monkeypatch.setattr(batch, "list_blueprints",
                        lambda **_: ({"id": "studio_invalid"},))
    monkeypatch.setattr(batch, "read_blueprint",
                        lambda _: (_ for _ in ()).throw(
                            StudioEcosystemError("invalid original source")))
    result = batch.audit_catalog_walk_choices(authorized=True, limit=1)
    assert result["projects"][0]["status"] == "invalid_source"
    assert result["complete_page_coverage"] is False
    assert result["complete_catalog_coverage"] is False
    assert result["projects"][0]["coverage_digest"] is None


def test_index_change_between_page_reads_fails_closed(monkeypatch):
    calls = 0
    def changing(**_):
        nonlocal calls
        calls += 1
        return ({"id": "studio_one"},) if calls == 1 else (
            {"id": "studio_two"},)
    monkeypatch.setattr(batch, "list_blueprints", changing)
    monkeypatch.setattr(batch, "read_blueprint",
                        lambda _: (_ for _ in ()).throw(
                            StudioEcosystemError("unavailable")))
    with pytest.raises(StudioQuestError, match="catalog changed"):
        batch.audit_catalog_walk_choices(authorized=True, limit=1)


def test_cli_catalog_audit_and_mode_exclusion(monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "list_blueprints", lambda **_: ())
    monkeypatch.setattr(batch, "list_blueprints", lambda **_: ())
    assert cli.main(["--walk-audit-catalog"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["filtered_project_count"] == 0
    assert result["complete_catalog_coverage"] is True
    with pytest.raises(SystemExit) as error:
        cli.main(["--walk-audit-catalog", "--play-walk", "--project", "x"])
    assert error.value.code == 2
