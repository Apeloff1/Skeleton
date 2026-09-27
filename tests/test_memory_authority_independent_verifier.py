from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.verify_memory_authority_closure import (
    SOURCE_TOKENS,
    verify_repository,
)

ROOT = Path(__file__).resolve().parents[1]


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel in SOURCE_TOKENS:
        src = ROOT / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for rel in (
        "machine/ai_app_construction.json",
        "machine/ai_implementation_handoff.json",
        "machine/ai_closure_evidence.json",
    ):
        src = ROOT / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return root


def test_live_memory_authority_verifier_accepts_closed_contract() -> None:
    receipt = verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["gap_id"] == "gap-memory-durable-authority"
    assert len(receipt["boundary_digests"]) == len(SOURCE_TOKENS)


def test_memory_verifier_rejects_reopened_gap(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    next(
        item
        for item in payload["gap_register"]
        if item["id"] == "gap-memory-durable-authority"
    )["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "durable-memory construction gap is not closed" in receipt["errors"]


def test_memory_verifier_rejects_lost_mongo_authority(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "skeleton/persistence/memory_repository.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace("class MongoMemoryRepository", "class RemovedMongoAuthority")
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("MongoMemoryRepository" in error for error in receipt["errors"])
