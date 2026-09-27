from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.check_ai_scope_freeze import (
    MASTER_PLAN_PATH,
    REGISTER_PATH,
    validate_repository,
)


ROOT = Path(__file__).resolve().parents[2]
HEAD = "a" * 40


def _copy_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (MASTER_PLAN_PATH, REGISTER_PATH):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _entry(*, status: str = "proposed", requested_id: int = 421) -> dict:
    row = {
        "id": f"ADR-SCOPE-{requested_id:04d}",
        "status": status,
        "requested_volume_id": requested_id,
        "requested_key": f"VOL-{requested_id:03d}",
        "title": "Candidate new top-level domain",
        "requirement": "Represent a requirement claimed not to fit existing domains.",
        "requested_by": "architecture-planning",
        "created_at": "2026-09-27T21:00:00Z",
        "rationale": "Formal review is required before any breadth change.",
        "existing_volume_analysis": [
            {
                "volume_ref": "VOL-002",
                "insufficiency": "System Architecture cannot own the proposed semantic domain.",
            },
            {
                "volume_ref": "VOL-003",
                "insufficiency": "Canonical Contract System cannot represent the domain itself.",
            },
        ],
        "alternatives_considered": [
            "Add a chapter to VOL-002.",
            "Represent the capability as a subdomain of VOL-003.",
        ],
        "approvals": [],
    }
    if status in {"approved_future", "applied"}:
        row.update(
            {
                "decision_summary": "Approved only for a future post-P1 plan revision.",
                "reviewed_at": "2026-09-27T22:00:00Z",
                "approvals": [
                    {
                        "role": "architecture_owner",
                        "signer": "owner-a",
                        "method": "github_identity",
                        "timestamp": "2026-09-27T22:00:00Z",
                        "commit_sha": HEAD,
                        "evidence_refs": ["docs/adr/scope-421-review.md"],
                    },
                    {
                        "role": "independent_verifier",
                        "signer": "verifier-b",
                        "method": "ci_oidc",
                        "timestamp": "2026-09-27T22:05:00Z",
                        "commit_sha": HEAD,
                        "evidence_refs": ["evidence/scope-421-independent.json"],
                    },
                ],
            }
        )
    if status == "applied":
        row["applied_plan_version"] = "2.0.0"
        row["applied_commit_sha"] = HEAD
    return row


def _read(root: Path, relative: Path) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _write(root: Path, relative: Path, payload: dict) -> None:
    (root / relative).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def test_live_scope_freeze_authority_is_valid() -> None:
    errors, summary = validate_repository(ROOT)

    assert errors == []
    assert summary["valid"] is True
    assert summary["frozen_last_top_level_volume"] == 420
    assert summary["frozen_volume_count"] == 421
    assert summary["applied_count"] == 0
    assert len(summary["master_plan_digest"]) == 64
    assert len(summary["adr_register_digest"]) == 64


def test_valid_proposed_adr_does_not_change_active_scope(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    register["entries"] = [_entry()]
    _write(root, REGISTER_PATH, register)

    errors, summary = validate_repository(root)

    assert errors == []
    assert summary["adr_count"] == 1
    assert summary["approved_future_count"] == 0
    assert summary["applied_count"] == 0


def test_approved_future_adr_requires_identity_bound_approvals(
    tmp_path: Path,
) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    row = _entry(status="approved_future")
    row["approvals"] = []
    register["entries"] = [row]
    _write(root, REGISTER_PATH, register)

    errors, _ = validate_repository(root)

    assert any("approvals must cover both required roles" in error for error in errors)
    assert any("distinct signers" in error for error in errors)


def test_valid_approved_future_adr_still_does_not_expand_p1(
    tmp_path: Path,
) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    register["entries"] = [_entry(status="approved_future")]
    _write(root, REGISTER_PATH, register)

    errors, summary = validate_repository(root)

    assert errors == []
    assert summary["approved_future_count"] == 1
    assert summary["applied_count"] == 0


def test_direct_top_level_volume_insertion_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    master = _read(root, MASTER_PLAN_PATH)
    master["volumes"].append(
        {
            "id": 421,
            "key": "VOL-421",
            "title": "Unauthorized breadth",
        }
    )
    _write(root, MASTER_PLAN_PATH, master)

    errors, _ = validate_repository(root)

    assert any("exactly 421 top-level volumes" in error for error in errors)
    assert any("unapproved top-level volume" in error for error in errors)


def test_applied_adr_is_rejected_during_active_p1(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    register["entries"] = [_entry(status="applied")]
    _write(root, REGISTER_PATH, register)

    errors, _ = validate_repository(root)

    assert any("applied scope expansion is forbidden" in error for error in errors)
    assert any("zero applied ADRs" in error for error in errors)


def test_adr_must_analyze_existing_canonical_volumes(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    row = _entry()
    row["existing_volume_analysis"][0]["volume_ref"] = "VOL-999"
    register["entries"] = [row]
    _write(root, REGISTER_PATH, register)

    errors, _ = validate_repository(root)

    assert any("references unknown existing volume" in error for error in errors)


def test_duplicate_requested_volume_id_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    second = _entry()
    second["id"] = "ADR-SCOPE-9999"
    register["entries"] = [_entry(), second]
    _write(root, REGISTER_PATH, register)

    errors, _ = validate_repository(root)

    assert any("duplicate requested_volume_id 421" in error for error in errors)


def test_manual_or_unbound_approval_method_is_rejected(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    row = _entry(status="approved_future")
    row["approvals"][0]["method"] = "manual"
    register["entries"] = [row]
    _write(root, REGISTER_PATH, register)

    errors, _ = validate_repository(root)

    assert any("signature method is not identity-bound" in error for error in errors)


def test_planned_only_approval_evidence_is_rejected(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    row = _entry(status="approved_future")
    row["approvals"][1]["evidence_refs"] = ["planned:future-verification.json"]
    register["entries"] = [row]
    _write(root, REGISTER_PATH, register)

    errors, _ = validate_repository(root)

    assert any("evidence_refs must be materialized" in error for error in errors)


def test_masterplan_authority_pointer_drift_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    master = _read(root, MASTER_PLAN_PATH)
    master["authority"]["p1_scope_freeze_adr_register"] = "machine/wrong.json"
    _write(root, MASTER_PLAN_PATH, master)

    errors, _ = validate_repository(root)

    assert "master plan scope-freeze ADR authority pointer drift" in errors


def test_breadth_freeze_application_policy_cannot_be_weakened(
    tmp_path: Path,
) -> None:
    root = _copy_repo(tmp_path)
    master = _read(root, MASTER_PLAN_PATH)
    master["breadth_freeze"]["p1_application_policy"] = "allow"
    _write(root, MASTER_PLAN_PATH, master)

    errors, _ = validate_repository(root)

    assert "breadth freeze p1_application_policy must equal forbid" in errors


def test_register_application_policy_cannot_be_weakened(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    register = _read(root, REGISTER_PATH)
    register["application_policy"]["p1_mode"] = "allow"
    register["application_policy"]["requires_execution_map_amendment_or_terminal_p1"] = False
    _write(root, REGISTER_PATH, register)

    errors, _ = validate_repository(root)

    assert "scope-freeze application policy p1_mode must be forbid" in errors
    assert any(
        "requires_execution_map_amendment_or_terminal_p1" in error
        for error in errors
    )
