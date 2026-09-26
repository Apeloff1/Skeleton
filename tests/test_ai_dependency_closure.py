from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_ai_dependency_closure import (
    CLOSURE_SURFACES,
    PREREQUISITES,
    TOOL_RUNTIME_GAP,
    verify_repository,
)


def _write_surfaces(root: Path) -> None:
    for surface in CLOSURE_SURFACES.values():
        workflow = root / surface["workflow"]
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(
            "\n".join(
                [
                    f"name: {surface['workflow_name']}",
                    "jobs:",
                    "  verify:",
                    "    steps:",
                    "      - uses: actions/checkout@deadbeef",
                    "        with:",
                    "          persist-credentials: false",
                    "          ref: ${{ github.event.pull_request.head.sha || github.sha }}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        verifier = root / surface["verifier"]
        verifier.parent.mkdir(parents=True, exist_ok=True)
        verifier.write_text(
            "\n".join(
                [
                    f'VERIFIER = "{surface["verifier_identity"]}"',
                    'HEAD = os.environ.get("GITHUB_SHA", "")',
                    "",
                ]
            ),
            encoding="utf-8",
        )


def _write_machine(
    root: Path,
    *,
    statuses: dict[str, str] | None = None,
    clean_closed: bool = False,
) -> None:
    statuses = statuses or {}
    relevant = (*PREREQUISITES, TOOL_RUNTIME_GAP)
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)

    construction = {
        "gap_register": [
            {"id": gap_id, "status": statuses.get(gap_id, "open")}
            for gap_id in relevant
        ]
    }
    evidence_entries = []
    handoff_entries = []
    for gap_id in relevant:
        status = statuses.get(gap_id, "open")
        closed = status == "closed"
        unresolved = [] if (closed and clean_closed) else ["fresh exact-head gate"]
        evidence_entries.append(
            {
                "gap": gap_id,
                "gap_status": status,
                "closure_decision": "closed" if closed else "open",
                "blockers": list(unresolved),
                "outstanding_evidence": list(unresolved),
            }
        )
        handoff_entries.append(
            {
                "gap": gap_id,
                "depends_on": list(PREREQUISITES) if gap_id == TOOL_RUNTIME_GAP else [],
                "implementation_status": "closed" if closed else "implemented_pending_verification",
                "remaining": list(unresolved),
            }
        )

    (machine / "ai_app_construction.json").write_text(
        json.dumps(construction), encoding="utf-8"
    )
    (machine / "ai_closure_evidence.json").write_text(
        json.dumps({"entries": evidence_entries}), encoding="utf-8"
    )
    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps({"entries": handoff_entries}), encoding="utf-8"
    )


def _valid_repo(tmp_path: Path) -> Path:
    _write_surfaces(tmp_path)
    _write_machine(tmp_path)
    return tmp_path


def test_dependency_closure_accepts_open_consistent_graph(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "dependency-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["head_sha"] == "dependency-head"
    assert receipt["prerequisites_closed"] is False
    assert receipt["tool_runtime_status"] == "open"
    assert len(receipt["closure_surface_digests"]) == len(CLOSURE_SURFACES) * 2


def test_dependency_closure_rejects_status_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "ai_closure_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    entry = next(x for x in payload["entries"] if x["gap"] == "gap-cost-admission")
    entry["gap_status"] = "closed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("gap-cost-admission construction/evidence status mismatch" in e for e in receipt["errors"])


def test_dependency_closure_rejects_tool_closed_before_prerequisites(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)

    path = root / "machine" / "ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    next(x for x in payload["gap_register"] if x["id"] == TOOL_RUNTIME_GAP)["status"] = "closed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    path = root / "machine" / "ai_closure_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    entry = next(x for x in payload["entries"] if x["gap"] == TOOL_RUNTIME_GAP)
    entry.update(
        gap_status="closed",
        closure_decision="closed",
        blockers=[],
        outstanding_evidence=[],
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    path = root / "machine" / "ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    next(x for x in payload["entries"] if x["gap"] == TOOL_RUNTIME_GAP)["remaining"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("tool-runtime is closed before prerequisites" in e for e in receipt["errors"])


def test_dependency_closure_rejects_non_exact_head_workflow(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    surface = CLOSURE_SURFACES["gap-provider-surface-convergence"]
    path = root / surface["workflow"]
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "github.event.pull_request.head.sha || github.sha",
            "github.sha",
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("workflow is not bound to exact PR head" in e for e in receipt["errors"])


def test_dependency_closure_accepts_clean_closed_graph(tmp_path: Path) -> None:
    statuses = {gap_id: "closed" for gap_id in (*PREREQUISITES, TOOL_RUNTIME_GAP)}
    _write_surfaces(tmp_path)
    _write_machine(tmp_path, statuses=statuses, clean_closed=True)

    receipt = verify_repository(tmp_path)

    assert receipt["valid"] is True
    assert receipt["prerequisites_closed"] is True
    assert receipt["tool_runtime_status"] == "closed"
