"""Catalog audits must reject altered/missing content and never infer release."""
from pathlib import Path
from shutil import copytree

from scripts.check_studio_ecosystem_catalog import audit
from skeleton.ai.game_builder.studio_ecosystem_catalog import ROOT, catalog_index


def test_full_source_audit_has_no_padding_or_unearned_claim():
    receipt = audit()
    assert receipt["status"] == "source_valid", receipt["errors"][:3]
    assert receipt["projects"] == 512
    assert receipt["documents"] == 4096
    assert receipt["unique_source_digests"] == 4096
    assert receipt["genres"] == 32
    assert receipt["release_certified"] is False


def test_audit_rejects_missing_section(tmp_path: Path):
    # Minimal index with one project still must retain exact eight sections.
    record = catalog_index()[0]
    root = tmp_path / "catalog"
    root.mkdir()
    import json
    index = json.loads((ROOT / "index.json").read_text())
    index["projects"] = [record]
    index["project_count"] = 1
    (root / "index.json").write_text(json.dumps(index))
    copytree(ROOT / record["id"], root / record["id"])
    (root / record["id"] / "scene.json").unlink()
    result = audit(root=root)
    assert result["status"] == "source_rejected"
    assert result["errors"]
