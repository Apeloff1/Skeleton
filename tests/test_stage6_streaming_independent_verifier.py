from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_stage6_streaming_closure import (
    BOUNDARIES,
    EXPECTED_DEPENDENCIES,
    MIRROR_PAIRS,
    verify_repository,
)


def _machine_contracts(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)

    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "gap": "gap-streaming-protocol",
                        "depends_on": sorted(EXPECTED_DEPENDENCIES),
                        "implementation_status": "implemented_pending_closure",
                        "closure_gate": (
                            "frontend can lose transport and resume without "
                            "duplicating side effects or losing terminal state"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    closure_evidence = [
        "durable replay",
        "browser reconnect",
        "cancel race",
    ]
    gaps = [
        {
            "id": "gap-streaming-protocol",
            "status": "open",
            "closure_evidence": closure_evidence,
        }
    ]
    gaps.extend(
        {"id": gap_id, "status": "open"}
        for gap_id in sorted(EXPECTED_DEPENDENCIES)
    )
    (machine / "ai_app_construction.json").write_text(
        json.dumps(
            {
                "gap_register": gaps,
                "realtime_delivery_blueprint": {
                    "gap": "gap-streaming-protocol",
                    "status": "implemented-pending-closure",
                    "tests": [
                        "disconnect/reconnect replay",
                        "slow-client bounded queue",
                        "cancel/complete race",
                        "multi-worker projection lease fencing/takeover",
                        "browser-session disconnect/reconnect persisted cursor journey",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (machine / "ai_closure_evidence.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "gap": "gap-streaming-protocol",
                        "gap_status": "open",
                        "closure_decision": "open",
                        "closure_evidence_required": closure_evidence,
                        "outstanding_evidence": ["exact-head signoff"],
                        "blockers": ["exact-head signoff"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _valid_repo(tmp_path: Path) -> Path:
    for rel, tokens in BOUNDARIES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"# {token}" for token in tokens) + "\n",
            encoding="utf-8",
        )
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = tmp_path / source_rel
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# synthetic Stage-6 source\n", encoding="utf-8")
        mirror = tmp_path / mirror_rel
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(source.read_bytes())
    _machine_contracts(tmp_path)
    return tmp_path


def test_stage6_verifier_accepts_complete_open_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "stage6-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "stage6-head"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert set(receipt["dependency_graph"]) == EXPECTED_DEPENDENCIES


def test_stage6_verifier_rejects_browser_journey_loss(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
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


def test_stage6_verifier_rejects_mongo_mirror_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    mirror = (
        root / "skeleton/ai/runtime/persistence/operation_store_mongo.py"
    )
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("canonical AI mirror drift" in error for error in receipt["errors"])


def test_stage6_verifier_rejects_dependency_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["depends_on"] = ["gap-state-authority-convergence"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("Stage-6 dependency graph mismatch" in error for error in receipt["errors"])


def test_stage6_verifier_rejects_false_closed_state(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    app_path = root / "machine/ai_app_construction.json"
    app = json.loads(app_path.read_text(encoding="utf-8"))
    app["gap_register"][0]["status"] = "closed"
    app["realtime_delivery_blueprint"]["status"] = "complete"
    app_path.write_text(json.dumps(app), encoding="utf-8")

    closure_path = root / "machine/ai_closure_evidence.json"
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    closure["entries"][0].update(
        {
            "gap_status": "closed",
            "closure_decision": "closed",
            "outstanding_evidence": [],
            "blockers": [],
        }
    )
    closure_path.write_text(json.dumps(closure), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "closed Stage-6 gap has non-closed dependencies" in error
        for error in receipt["errors"]
    )


def test_stage6_verifier_accepts_closed_state_when_dependencies_closed(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    app_path = root / "machine/ai_app_construction.json"
    app = json.loads(app_path.read_text(encoding="utf-8"))
    for item in app["gap_register"]:
        item["status"] = "closed"
    app["realtime_delivery_blueprint"]["status"] = "complete"
    app_path.write_text(json.dumps(app), encoding="utf-8")

    handoff_path = root / "machine/ai_implementation_handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["entries"][0]["implementation_status"] = "closed"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    closure_path = root / "machine/ai_closure_evidence.json"
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    closure["entries"][0].update(
        {
            "gap_status": "closed",
            "closure_decision": "closed",
            "outstanding_evidence": [],
            "blockers": [],
        }
    )
    closure_path.write_text(json.dumps(closure), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["gap_status"] == "closed"
