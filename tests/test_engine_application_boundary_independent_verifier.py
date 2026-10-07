from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.verify_engine_application_boundary_closure import (
    COMPOSE,
    REQUIRED_BOUNDARIES,
    WORKFLOW,
    verify_repository,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy(root: Path, rel: str) -> None:
    source = ROOT / rel
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel in (
        *REQUIRED_BOUNDARIES,
        COMPOSE,
        WORKFLOW,
        "machine/ai_app_construction.json",
        "machine/ai_implementation_handoff.json",
        "machine/ai_closure_evidence.json",
    ):
        _copy(root, rel)
    return root


def test_live_engine_application_boundary_verifier_accepts_closed_contract() -> None:
    receipt = verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["gap_id"] == "gap-engine-application-execution-boundary"
    assert len(receipt["boundary_digests"]) >= len(REQUIRED_BOUNDARIES) + 2


def test_engine_verifier_rejects_reopened_dependency(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    next(
        item
        for item in payload["gap_register"]
        if item["id"] == "gap-cognitive-execution-loop"
    )["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "Stage-5 has non-closed dependencies" in receipt["errors"]


def test_engine_verifier_rejects_merge_ref_workflow(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / WORKFLOW
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "          ref: ${{ github.event.pull_request.head.sha || github.sha }}\n",
        "",
    )
    source = source.replace("github.event.pull_request.head.sha", "github.sha")
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "github.event.pull_request.head.sha" in error
        for error in receipt["errors"]
    )


def test_engine_verifier_rejects_backend_provider_credential_leak(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    path = root / COMPOSE
    source = path.read_text(encoding="utf-8")
    marker = "  backend:\n"
    assert marker in source
    source = source.replace(
        marker,
        marker + "    environment:\n      OPENAI_API_KEY: leaked\n",
        1,
    )
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "OPENAI_API_KEY leaked into backend service" in receipt["errors"]


def test_engine_verifier_rejects_lost_client_recovery(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "backend/core/engine_client.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "_recover_ambiguous_submit",
        "_removed_ambiguous_submit_recovery",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "backend/core/engine_client.py lost Stage-5 token: _recover_ambiguous_submit"
        in error
        for error in receipt["errors"]
    )
