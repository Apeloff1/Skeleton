from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from skeleton.ai.integrations.openai_oss import SOURCES


ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_openai_oss_assimilation.py"
MANIFEST = ROOT / "machine/openai_oss_assimilation.json"


def _validator():
    spec = importlib.util.spec_from_file_location("check_openai_oss_assimilation", CHECK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openai_oss_snapshots_are_exact_and_quarantined() -> None:
    assert _validator().validate() == []


def test_runtime_registry_matches_machine_provenance() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(data["sources"]) == set(SOURCES)
    for source_id, runtime in SOURCES.items():
        machine = data["sources"][source_id]
        assert machine["repository"] == runtime.repository
        assert machine["commit_sha"] == runtime.commit_sha
        assert machine["license_spdx"] == runtime.license_spdx
        assert machine["snapshot_root"] == runtime.snapshot_root


def test_snapshots_are_non_executable_source_material() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for source in data["sources"].values():
        for item in source["files"]:
            destination = item["destination_path"]
            if destination.endswith("LICENSE.upstream.txt"):
                continue
            assert destination.endswith(".txt")
            assert (ROOT / destination).is_file()
