#!/usr/bin/env python3
"""Validate the canonical P1 required-gate authority and exact-head observations."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

from skeleton.contracts.promotion_gates import (
    GateObservation,
    PromotionGateError,
    canonical_digest,
    evaluate_required_gates,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = Path("machine/p1_required_gate_authority.json")
MASTER_PLAN_PATH = Path("machine/ai_master_plan.json")
EXPECTED_POLICY_ID = "skeleton.p1.required_gate_authority"
EXPECTED_POLICY_VERSION = "1.0.0"
EXPECTED_TASK_ID = "P1-EVID-03"
EXPECTED_ACCOUNTABILITY = "ACC-P1-EVID-03"
EXPECTED_GATE_COUNT = 25
EXPECTED_RULES = {
    "missing_gate": "reject",
    "stale_head": "reject",
    "nonterminal_status": "reject",
    "skipped_conclusion": "reject",
    "cancelled_conclusion": "reject",
    "neutral_conclusion": "reject",
    "failure_conclusion": "reject",
    "duplicate_exact_head_observation": "reject",
    "unknown_gate_observation": "ignore_but_do_not_count",
}
_ALLOWED_GROUPS = {
    "baseline",
    "evidence",
    "integration",
    "portability",
    "product",
    "quality",
    "recovery",
    "repository",
    "runtime",
    "security",
}
_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_GATE_ID_RE = re.compile(r"^GATE-[A-Z0-9]+(?:-[A-Z0-9]+)*$")


class GateAuthorityValidationError(RuntimeError):
    """Authority or observation input could not be validated."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateAuthorityValidationError(f"cannot read {path}") from exc


def _workflow_name(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateAuthorityValidationError(f"cannot read workflow {path}") from exc
    match = _NAME_RE.search(text)
    if match is None:
        raise GateAuthorityValidationError(f"workflow missing name: {path}")
    raw = match.group(1).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        raw = raw[1:-1]
    return raw


def validate_authority(
    root: Path = ROOT,
    *,
    authority_path: Path = AUTHORITY_PATH,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    authority = _load_json(root / authority_path)
    if not isinstance(authority, dict):
        raise GateAuthorityValidationError("authority must be an object")

    master = _load_json(root / MASTER_PLAN_PATH)
    if not isinstance(master, dict):
        errors.append("master plan must be an object")
    else:
        master_authority = master.get("authority")
        if not isinstance(master_authority, dict):
            errors.append("master plan authority must be an object")
        elif master_authority.get("p1_required_gate_authority") != str(
            authority_path
        ):
            errors.append("master plan required-gate authority pointer drift")

    if authority.get("schema_version") != 1:
        errors.append("authority schema_version must equal 1")
    if authority.get("policy_id") != EXPECTED_POLICY_ID:
        errors.append("authority policy_id drift")
    if authority.get("policy_version") != EXPECTED_POLICY_VERSION:
        errors.append("authority policy_version drift")
    if authority.get("authority") != str(authority_path):
        errors.append("authority self-path drift")
    if authority.get("task_id") != EXPECTED_TASK_ID:
        errors.append("authority task_id drift")
    if authority.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        errors.append("authority accountability_ref drift")
    if authority.get("target_event") != "pull_request":
        errors.append("authority target_event must equal pull_request")
    if authority.get("target_branch") != "main":
        errors.append("authority target_branch must equal main")
    if authority.get("exact_head_required") is not True:
        errors.append("authority exact_head_required must be true")
    if authority.get("fail_closed_rules") != EXPECTED_RULES:
        errors.append("authority fail_closed_rules drift")

    gates = authority.get("gates")
    if not isinstance(gates, list):
        errors.append("authority gates must be a list")
        gates = []
    if len(gates) != EXPECTED_GATE_COUNT:
        errors.append(
            f"required gate count drift: expected={EXPECTED_GATE_COUNT} actual={len(gates)}"
        )

    ids: set[str] = set()
    names: set[str] = set()
    paths: set[str] = set()
    groups_seen: dict[str, set[str]] = {}
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            errors.append(f"gate[{index}] must be an object")
            continue
        gate_id = gate.get("id")
        name = gate.get("workflow_name")
        workflow_file = gate.get("workflow_file")
        group = gate.get("group")
        if not isinstance(gate_id, str) or not gate_id:
            errors.append(f"gate[{index}] missing id")
        elif not _GATE_ID_RE.fullmatch(gate_id):
            errors.append(f"invalid gate id: {gate_id}")
        elif gate_id in ids:
            errors.append(f"duplicate gate id: {gate_id}")
        else:
            ids.add(gate_id)
        if not isinstance(name, str) or not name:
            errors.append(f"{gate_id or index}: missing workflow_name")
        elif name in names:
            errors.append(f"duplicate workflow_name: {name}")
        else:
            names.add(name)
        if not isinstance(workflow_file, str) or not workflow_file.startswith(
            ".github/workflows/"
        ):
            errors.append(f"{gate_id or index}: invalid workflow_file")
        elif workflow_file in paths:
            errors.append(f"duplicate workflow_file: {workflow_file}")
        else:
            paths.add(workflow_file)
            full = root / workflow_file
            if not full.is_file():
                errors.append(f"{gate_id or index}: workflow file missing")
            else:
                actual_name = _workflow_name(full)
                if isinstance(name, str) and actual_name != name:
                    errors.append(
                        f"{gate_id}: workflow name mismatch: "
                        f"declared={name!r} actual={actual_name!r}"
                    )
                text = full.read_text(encoding="utf-8")
                if "pull_request:" not in text:
                    errors.append(f"{gate_id}: workflow lacks pull_request trigger")
        if group not in _ALLOWED_GROUPS:
            errors.append(f"{gate_id or index}: invalid group {group!r}")
        elif isinstance(gate_id, str):
            groups_seen.setdefault(group, set()).add(gate_id)
        if gate.get("required_for_terminal_p1_promotion") is not True:
            errors.append(f"{gate_id or index}: gate must be terminal-required")
        if gate.get("accepted_statuses") != ["completed"]:
            errors.append(f"{gate_id or index}: accepted_statuses must be completed-only")
        if gate.get("accepted_conclusions") != ["success"]:
            errors.append(f"{gate_id or index}: accepted_conclusions must be success-only")
        purpose = gate.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            errors.append(f"{gate_id or index}: purpose must be non-empty")

    # Required workflow names are collection identities. Enforce global
    # uniqueness so an unrelated workflow cannot impersonate a required gate
    # merely by reusing its display name.
    workflow_name_paths: dict[str, list[str]] = {}
    workflow_root = root / ".github/workflows"
    for pattern in ("*.yml", "*.yaml"):
        for candidate in sorted(workflow_root.glob(pattern)):
            try:
                candidate_name = _workflow_name(candidate)
            except GateAuthorityValidationError:
                continue
            rel = candidate.relative_to(root).as_posix()
            workflow_name_paths.setdefault(candidate_name, []).append(rel)
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gate_id = gate.get("id")
        name = gate.get("workflow_name")
        workflow_file = gate.get("workflow_file")
        if not isinstance(name, str) or not isinstance(workflow_file, str):
            continue
        matches = workflow_name_paths.get(name, [])
        if matches != [workflow_file]:
            errors.append(
                f"{gate_id}: required workflow name must resolve uniquely "
                f"to {workflow_file}; matches={matches}"
            )

    groups = authority.get("groups")
    if not isinstance(groups, list):
        errors.append("authority groups must be a list")
        groups = []
    declared_groups: dict[str, set[str]] = {}
    seen_group_names: set[str] = set()
    for row in groups:
        if not isinstance(row, dict):
            errors.append("authority group entries must be objects")
            continue
        name = row.get("name")
        refs = row.get("gate_ids")
        if name not in _ALLOWED_GROUPS:
            errors.append(f"invalid authority group name: {name!r}")
            continue
        if name in seen_group_names:
            errors.append(f"duplicate authority group name: {name}")
            continue
        seen_group_names.add(str(name))
        if not isinstance(refs, list) or not refs:
            errors.append(f"group {name}: gate_ids must be non-empty")
            continue
        ref_set = {str(item) for item in refs}
        if len(ref_set) != len(refs):
            errors.append(f"group {name}: duplicate gate id")
        unknown = ref_set - ids
        if unknown:
            errors.append(f"group {name}: unknown gate ids {sorted(unknown)}")
        declared_groups[str(name)] = ref_set
    if set(declared_groups) != _ALLOWED_GROUPS:
        errors.append("authority group inventory drift")
    for group in sorted(_ALLOWED_GROUPS):
        if declared_groups.get(group, set()) != groups_seen.get(group, set()):
            errors.append(f"group {group}: membership drift")

    terminal = authority.get("terminal_policy")
    if not isinstance(terminal, dict):
        errors.append("terminal_policy must be an object")
    else:
        if terminal.get("required_gate_count") != len(gates):
            errors.append("terminal_policy required_gate_count drift")
        expected = {
            "accepted_status": "completed",
            "accepted_conclusion": "success",
            "all_required_gates_must_pass": True,
            "observation_set_must_bind_one_exact_head": True,
            "authority_digest_must_match": True,
            "self_promotion_forbidden": True,
        }
        for key, value in expected.items():
            if terminal.get(key) != value:
                errors.append(f"terminal_policy {key} drift")

    summary = {
        "schema_version": 1,
        "policy_id": authority.get("policy_id"),
        "policy_version": authority.get("policy_version"),
        "task_id": authority.get("task_id"),
        "accountability_ref": authority.get("accountability_ref"),
        "required_gate_count": len(gates),
        "group_count": len(declared_groups),
        "authority_digest": canonical_digest(authority),
        "valid": not errors,
        "errors": errors,
    }
    return errors, summary


def _parse_observation(row: object) -> GateObservation:
    if not isinstance(row, dict):
        raise GateAuthorityValidationError("observation entries must be objects")
    allowed = {
        "workflow_name",
        "head_sha",
        "run_id",
        "run_attempt",
        "event",
        "status",
        "conclusion",
        "completed_at",
    }
    unknown = set(row) - allowed
    if unknown:
        raise GateAuthorityValidationError(
            "observation contains unknown fields: " + ",".join(sorted(unknown))
        )
    try:
        completed_raw = row.get("completed_at")
        completed_at = (
            None
            if completed_raw is None
            else datetime.fromisoformat(
                str(completed_raw).replace("Z", "+00:00")
            )
        )
        return GateObservation(
            workflow_name=row["workflow_name"],
            head_sha=row["head_sha"],
            run_id=str(row["run_id"]),
            run_attempt=row["run_attempt"],
            event=row["event"],
            status=row["status"],
            conclusion=row.get("conclusion"),
            completed_at=completed_at,
        )
    except (KeyError, TypeError, ValueError, PromotionGateError) as exc:
        raise GateAuthorityValidationError(
            f"invalid gate observation: {exc}"
        ) from exc


def evaluate_observations(
    root: Path,
    *,
    observations_path: Path,
    target_sha: str,
    authority_path: Path = AUTHORITY_PATH,
) -> dict[str, Any]:
    errors, summary = validate_authority(root, authority_path=authority_path)
    if errors:
        raise GateAuthorityValidationError(
            "authority is invalid: " + "; ".join(errors)
        )
    authority = _load_json(root / authority_path)
    rows = _load_json(observations_path)
    if not isinstance(rows, list):
        raise GateAuthorityValidationError("observations must be a JSON array")
    observations = tuple(_parse_observation(row) for row in rows)
    decision = evaluate_required_gates(
        authority,
        observations,
        target_sha=target_sha,
    )
    payload = {
        "schema_version": 1,
        "authority": summary,
        "decision": decision.as_dict(),
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", type=Path, default=AUTHORITY_PATH)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--target-sha")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        errors, summary = validate_authority(
            ROOT,
            authority_path=args.authority,
        )
        payload: dict[str, Any] = {"authority": summary}
        if errors:
            if args.print_summary:
                print(json.dumps(payload, indent=2, sort_keys=True))
            for error in errors:
                print(f"P1 gate authority: {error}", file=sys.stderr)
            return 1

        if args.observations is not None or args.target_sha is not None:
            if args.observations is None or args.target_sha is None:
                raise GateAuthorityValidationError(
                    "--observations and --target-sha must be supplied together"
                )
            payload = evaluate_observations(
                ROOT,
                observations_path=args.observations,
                target_sha=args.target_sha,
                authority_path=args.authority,
            )
            if payload["decision"]["accepted"] is not True:
                if args.print_summary:
                    print(json.dumps(payload, indent=2, sort_keys=True))
                print("P1 gate authority: observation set rejected", file=sys.stderr)
                return 1

        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (GateAuthorityValidationError, PromotionGateError) as exc:
        print(f"P1 gate authority: rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
