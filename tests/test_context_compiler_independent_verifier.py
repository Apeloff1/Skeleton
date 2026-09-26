from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.verify_context_compiler_closure import (
    BOUNDARY_FILES,
    MIRROR_PAIRS,
    VERIFIER_ID,
    verify,
)


ROOT = Path(__file__).resolve().parents[1]


def test_repository_context_compiler_independent_verifier_is_green() -> None:
    receipt = verify(ROOT, head_sha="exact-head-test")

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["verifier"] == VERIFIER_ID
    assert receipt["head_sha"] == "exact-head-test"
    assert len(receipt["boundary_digests"]) == len(BOUNDARY_FILES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert all(item["equal"] for item in receipt["mirror_pairs"])
    assert receipt["handoff_digest"]


def test_context_compiler_independent_verifier_detects_mirror_drift(
    tmp_path: Path,
) -> None:
    for canonical, mirror in MIRROR_PAIRS:
        for relative in (canonical, mirror):
            source = ROOT / relative
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for relative in BOUNDARY_FILES:
        source = ROOT / relative
        target = tmp_path / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    mirror = tmp_path / MIRROR_PAIRS[0][1]
    mirror.write_text(
        mirror.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    receipt = verify(tmp_path)

    assert receipt["valid"] is False
    assert any("context mirror drift" in item for item in receipt["errors"])


def test_context_compiler_independent_verifier_detects_dependency_drift(
    tmp_path: Path,
) -> None:
    for canonical, mirror in MIRROR_PAIRS:
        for relative in (canonical, mirror):
            source = ROOT / relative
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for relative in BOUNDARY_FILES:
        source = ROOT / relative
        target = tmp_path / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    handoff_path = tmp_path / "machine/ai_implementation_handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in handoff["entries"]
        if item["gap"] == "gap-context-compiler-convergence"
    )
    entry["depends_on"] = ["gap-invented"]
    handoff_path.write_text(
        json.dumps(handoff, indent=2) + "\n",
        encoding="utf-8",
    )

    receipt = verify(tmp_path)

    assert receipt["valid"] is False
    assert "context compiler dependency graph is invalid" in receipt["errors"]
