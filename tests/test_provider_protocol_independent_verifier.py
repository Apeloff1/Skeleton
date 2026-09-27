from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.verify_provider_protocol_closure import (
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
    mirror_src = ROOT / "skeleton/ai/runtime/provider_runtime.py"
    mirror_dst = root / "skeleton/ai/runtime/provider_runtime.py"
    mirror_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mirror_src, mirror_dst)
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


def test_live_provider_protocol_verifier_accepts_closed_contract() -> None:
    receipt = verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["gap_id"] == "gap-provider-interaction-protocol"
    assert receipt["provider_mirror_digest"]


def test_provider_protocol_verifier_rejects_mirror_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    mirror = root / "skeleton/ai/runtime/provider_runtime.py"
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "provider runtime AI mirror drifted" in receipt["errors"]


def test_provider_protocol_verifier_rejects_unoffered_tool_guard_loss(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    path = root / "skeleton/testing/test_provider_contract.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "test_sync_openai_rejects_unoffered_tool_call",
        "removed_unoffered_tool_guard",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "test_sync_openai_rejects_unoffered_tool_call" in error
        for error in receipt["errors"]
    )
