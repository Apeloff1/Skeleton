from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.verify_vol007_inference import verify_repository


ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/ai_master_plan.json",
        "skeleton/inference/session.py",
        "skeleton/inference/provider_bridge.py",
        "skeleton/inference/replay.py",
        "skeleton/inference/async_runtime.py",
        "skeleton/inference/batching.py",
        "skeleton/inference/speculation.py",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_independent_vol007_accepts_current_implementation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _fixture(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "vol007-head")
    receipt = verify_repository(root)
    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "vol007-head"
    assert receipt["volume"] == "VOL-007"
    assert receipt["checked_invariant_count"] >= 40
    assert len(receipt["source_digests"]) == 6
    assert len(receipt["volume_binding"]["binding_digest"]) == 64
    assert len(receipt["receipt_digest"]) == 64


def test_independent_vol007_rejects_batch_authority_weakening(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "skeleton/inference/batching.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "batch plan cannot grant inference authority",
            "batch may grant inference authority",
        ),
        encoding="utf-8",
    )
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "batch plan cannot grant inference authority" in error
        for error in receipt["errors"]
    )


def test_independent_vol007_rejects_speculation_gate_removal(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "skeleton/inference/speculation.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "speculative candidate diverged from authoritative inference result",
            "speculative divergence accepted",
        ),
        encoding="utf-8",
    )
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "speculative candidate diverged from authoritative inference result"
        in error
        for error in receipt["errors"]
    )


def test_independent_vol007_rejects_replay_integrity_weakening(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "skeleton/inference/replay.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "replay event chain mismatch",
            "replay chain ignored",
        ),
        encoding="utf-8",
    )
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("replay event chain mismatch" in error for error in receipt["errors"])


def test_independent_vol007_rejects_masterplan_binding_loss(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-007")
    volume["tests"].remove("skeleton/testing/test_vol007_speculation.py")
    _write(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("VOL-007 test binding incomplete" in error for error in receipt["errors"])


def test_independent_vol007_rejects_old_implementation_gap(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-007")
    volume["gaps"] = ["speculative decoding requires measured correctness gates"]
    _write(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "VOL-007 gap state must be qualification-only or signed" in receipt["errors"]


def test_independent_vol007_accepts_signed_state(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-007")
    volume["gaps"] = []
    volume["completion_checkbox"] = True
    volume["completion_checkbox_mark"] = "[x]"
    volume["implementation_status"] = "verified"
    _write(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is True
    assert receipt["errors"] == []
