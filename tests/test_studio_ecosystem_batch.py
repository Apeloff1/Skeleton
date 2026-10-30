"""Batch produces only operator-authorized, verified, immutable preview products."""
from __future__ import annotations

from pathlib import Path
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_batch import materialize_previews
from skeleton.ai.game_builder.studio_ecosystem_catalog import (
    StudioEcosystemError, list_blueprints,
)


def test_materialize_real_preview_and_proof(tmp_path: Path):
    project = list_blueprints(genre="puzzle_expedition")[0]["id"]
    with pytest.raises(PermissionError):
        materialize_previews(tmp_path, authorized=False, project_ids=(project,))
    batch = materialize_previews(tmp_path, authorized=True, project_ids=(project,))
    assert batch["project_count"] == 1
    assert batch["release_certified"] is False
    html = tmp_path / project / "index.html"
    receipt = json.loads((tmp_path / project / "receipt.json").read_text())
    assert "<html" in html.read_text().lower()
    assert receipt["winning_replay"]
    assert not receipt["genre_runtime_implemented"] and not receipt["release_certified"]
    with pytest.raises(StudioEcosystemError):
        materialize_previews(tmp_path, authorized=True, project_ids=(project,))


def test_rejects_source_scope_and_invalid_budget(tmp_path: Path):
    project = list_blueprints(genre="puzzle_expedition")[0]["id"]
    with pytest.raises(StudioEcosystemError):
        materialize_previews(tmp_path, authorized=True, project_ids=("unknown",))
    with pytest.raises(StudioEcosystemError):
        materialize_previews(tmp_path, authorized=True, project_ids=(project,),
                             max_artifact_bytes=1)
    assert not (tmp_path / project).exists()
    with pytest.raises(StudioEcosystemError):
        materialize_previews(tmp_path, authorized=True, project_ids=(project, project))
