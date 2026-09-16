from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repo_intel.py"
INTEL = ROOT / "repo-intel"


def load(name: str):
    return json.loads((INTEL / name).read_text(encoding="utf-8"))


def test_hundred_batch_graph_is_unique_and_acyclic():
    payload = load("batches.json")
    batches = payload["batches"]
    assert payload["batch_count"] == 100
    assert len(batches) == 100
    by_id = {item["id"]: item for item in batches}
    assert len(by_id) == 100

    for batch in batches:
        assert batch["title"].strip()
        assert batch["success"].strip()
        assert batch["wave"] >= 1
        assert batch["id"] not in batch.get("depends_on", [])
        assert set(batch.get("depends_on", [])).issubset(by_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(batch_id: str) -> None:
        if batch_id in visited:
            return
        assert batch_id not in visiting, f"cycle detected at {batch_id}"
        visiting.add(batch_id)
        for dep in by_id[batch_id].get("depends_on", []):
            visit(dep)
        visiting.remove(batch_id)
        visited.add(batch_id)

    for batch_id in by_id:
        visit(batch_id)
    assert len(visited) == 100


def test_game_capability_ids_are_unique_and_actionable():
    payload = load("game-capabilities.json")
    capabilities = payload["capabilities"]
    ids = [item["id"] for item in capabilities]
    assert len(ids) == len(set(ids))
    assert len(capabilities) >= 40
    assert {item["category"] for item in capabilities} >= {
        "creator", "gameplay", "ai", "assets", "runtime", "network", "build", "quality", "security"
    }
    for item in capabilities:
        assert item["anchors"], item["id"]
        assert item["build_note"].strip(), item["id"]
        assert 1 <= item["priority"] <= 4


def test_cli_contract_validation_passes():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "check"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "100 batches" in proc.stdout


def test_snapshot_materializes_machine_and_human_maps(tmp_path: Path):
    out = tmp_path / "repo-intel"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "snapshot", "--out", str(out)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    expected = {
        "index.json",
        "build-map.json",
        "gaps.json",
        "security-quality.json",
        "notes.md",
    }
    assert expected.issubset({p.name for p in out.iterdir()})

    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert len(index["source_digest"]) == 64
    assert index["tracked_files"] > 0
    assert any(row["path"] == "Makefile" for row in index["files"])
    assert all(item["bytes"] >= 50 * 1024 * 1024 for item in index["large_tracked_files"])

    gaps = json.loads((out / "gaps.json").read_text(encoding="utf-8"))
    assert len(gaps["capabilities"]) >= 40
    assert set(gaps["counts"]).issubset({"present-surface", "partial-surface", "missing-surface"})

    sq = json.loads((out / "security-quality.json").read_text(encoding="utf-8"))
    assert "pip" in sq["dependabot_ecosystems"]
    assert "npm" in sq["dependabot_ecosystems"]
    assert "github-actions" in sq["dependabot_ecosystems"]

    notes = (out / "notes.md").read_text(encoding="utf-8")
    assert "Noticeable gaps ready for build augmentation" in notes
    assert "Security and quality notes" in notes
    assert "Agent/build handoff contract" in notes
