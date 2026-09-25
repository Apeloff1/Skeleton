from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from skeleton.ai.integrations.xai_oss import (
    LicenseDisposition,
    SOURCES,
)


ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_xai_grok_oss_assimilation.py"
MANIFEST = ROOT / "machine/xai_grok_oss_assimilation.json"


def _validator():
    spec = importlib.util.spec_from_file_location("check_xai_grok_oss_assimilation", CHECK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_xai_oss_snapshots_are_exact_and_quarantined() -> None:
    assert _validator().validate() == []


def test_runtime_registry_matches_machine_provenance() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    admitted = {
        key: value
        for key, value in SOURCES.items()
        if value.disposition is LicenseDisposition.RUNTIME_ADMITTED
    }
    assert set(data["sources"]) == set(admitted)
    for source_id, runtime in admitted.items():
        machine = data["sources"][source_id]
        assert machine["repository"] == runtime.repository
        assert machine["commit_sha"] == runtime.commit_sha
        assert machine["license_expression"] == runtime.license_expression
        assert machine["snapshot_root"] == runtime.snapshot_root


def test_non_permissive_sources_remain_metadata_only() -> None:
    assert SOURCES["grok-prompts"].license_expression == "AGPL-3.0-only"
    assert SOURCES["grok-prompts"].disposition is LicenseDisposition.METADATA_ONLY
    assert SOURCES["grok-prompts"].snapshot_root is None

    assert SOURCES["xai-cookbook"].license_expression == "LicenseRef-xAI-Beta-Testing"
    assert SOURCES["xai-cookbook"].disposition is LicenseDisposition.METADATA_ONLY
    assert SOURCES["xai-cookbook"].snapshot_root is None


def test_all_copied_source_material_is_non_executable() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for source in data["sources"].values():
        for item in source["files"]:
            assert item["destination_path"].endswith(".txt")
            assert (ROOT / item["destination_path"]).is_file()
