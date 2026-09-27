from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_streaming_protocol_closure import (
    BOUNDARIES,
    DEPENDENCIES,
    MIRROR_PAIRS,
    verify_repository,
)


def _write_machine(root: Path, *, closed: bool = True) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    gap_status = "closed" if closed else "open"
    handoff_status = "closed" if closed else "implemented_pending_closure"
    closure_status = "closed" if closed else "open"
    blueprint_status = "closed" if closed else "implemented-pending-closure"

    gap_register = [
        {"id": dep, "status": "closed"} for dep in sorted(DEPENDENCIES)
    ]
    gap_register.append({"id": "gap-streaming-protocol", "status": gap_status})
    construction = {
        "gap_register": gap_register,
        "realtime_delivery_blueprint": {
            "gap": "gap-streaming-protocol",
            "status": blueprint_status,
        },
    }
    handoff = {
        "entries": [
            {
                "gap": "gap-streaming-protocol",
                "implementation_status": handoff_status,
                "depends_on": sorted(DEPENDENCIES),
            }
        ]
    }
    closure = {
        "entries": [
            {
                "gap": "gap-streaming-protocol",
                "closure_decision": closure_status,
                "implementation_state": closure_status,
                "outstanding_evidence": [] if closed else ["exact-head gate"],
                "blockers": [] if closed else ["exact-head gate"],
                "evidence_present": [
                    "browser-session reconnect proof",
                    "Mongo shared-network authority proof",
                    "cancel-complete terminal race proof",
                    "shared-network replay proof",
                ],
            }
        ]
    }
    (machine / "ai_app_construction.json").write_text(
        json.dumps(construction), encoding="utf-8"
    )
    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps(handoff), encoding="utf-8"
    )
    (machine / "ai_closure_evidence.json").write_text(
        json.dumps(closure), encoding="utf-8"
    )


def _repo(tmp_path: Path, *, closed: bool = True) -> Path:
    root = tmp_path
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"# {token}" for token in tokens) + "\n",
            encoding="utf-8",
        )
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(source.read_bytes())
    _write_machine(root, closed=closed)
    return root


def test_streaming_verifier_accepts_closed_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _repo(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "stream-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "stream-head"
    assert receipt["machine"]["gap_status"] == "closed"
    assert set(receipt["dependency_graph"]) == DEPENDENCIES
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)


def test_streaming_verifier_rejects_missing_browser_journey(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    path = root / "frontend/scripts/test-operation-stream-session.mjs"
    source = path.read_text(encoding="utf-8").replace(
        "# browser disconnect and reconnect resumes from persisted accepted cursor\n",
        "",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "lost Stage-6 token" in error
        and "browser disconnect and reconnect" in error
        for error in receipt["errors"]
    )


def test_streaming_verifier_rejects_canonical_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    mirror = root / "skeleton/ai/runtime/frontier/operation_stream.py"
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("canonical mirror drift" in error for error in receipt["errors"])


def test_streaming_verifier_rejects_closed_gap_with_open_dependency(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "closed Stage-6 gap has non-closed dependencies" in error
        for error in receipt["errors"]
    )


def test_streaming_verifier_rejects_closed_gap_with_open_closure_record(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    path = root / "machine/ai_closure_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["closure_decision"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "closed Stage-6 gap requires closed closure decision" in error
        for error in receipt["errors"]
    )
