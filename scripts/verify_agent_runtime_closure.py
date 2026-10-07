#!/usr/bin/env python3
"""Independent verifier for VOL-016 durable agent runtime closure.

The verifier intentionally does not import the agent runtime implementation.
It inspects repository files directly so implementation bugs cannot redefine
the verification rules that judge them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]

CANONICAL = "skeleton/automation/agents/agent_runtime.py"
MIRROR = "skeleton/ai/agents/core/agent_runtime.py"
FACADE = "skeleton/agents/agent_runtime.py"
RUNTIME_TEST = "skeleton/testing/test_agent_runtime_durable.py"
AUTO02_WORKFLOW = ".github/workflows/p1-agent-delegation-qualification.yml"

REQUIRED_TOKENS = (
    "class AgentDescriptor",
    "class AgentCheckpoint",
    "class AgentResourceUsage",
    "class SQLiteAgentRuntimeStore",
    "class DurableAgentSupervisor",
    "AgentDelegationAuthority",
    "DelegationBudget",
    "agent_runtime_registration",
    "agent_runtime_checkpoint",
    "checkpoint_digest",
    "previous_digest",
    "active_task_ids",
    "record_usage",
    "max_parallel_tasks",
    "max_steps",
    "max_tokens",
    "max_cost_units",
    "max_wall_time_s",
    "require_live_authority",
    "delegation authority is expired",
)

FORBIDDEN_TOKENS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "from openai",
    "import openai",
    "requests.",
    "httpx.",
    "subprocess.",
    "os.system",
)


class AgentRuntimeVerificationError(RuntimeError):
    """The independent verifier could not safely inspect repository state."""


def _read(root: Path, relative: str) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AgentRuntimeVerificationError(
            f"cannot read {relative}"
        ) from exc


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(root: Path, relative: str) -> dict[str, Any]:
    try:
        payload = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentRuntimeVerificationError(
            f"cannot parse {relative}"
        ) from exc
    if not isinstance(payload, dict):
        raise AgentRuntimeVerificationError(f"{relative} must be an object")
    return payload


def _find_volume(value: object, key: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("key") == key:
            return value
        for child in value.values():
            match = _find_volume(child, key)
            if match is not None:
                return match
    elif isinstance(value, list):
        for child in value:
            match = _find_volume(child, key)
            if match is not None:
                return match
    return None


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []

    canonical_path = root / CANONICAL
    mirror_path = root / MIRROR
    facade_path = root / FACADE
    test_path = root / RUNTIME_TEST
    workflow_path = root / AUTO02_WORKFLOW

    required_paths = (
        canonical_path,
        mirror_path,
        facade_path,
        test_path,
        workflow_path,
        root / "machine/ai_master_plan.json",
    )
    for path in required_paths:
        if not path.is_file():
            errors.append(
                "agent-runtime required file missing: "
                + path.relative_to(root).as_posix()
            )

    canonical = ""
    mirror = ""
    facade = ""
    workflow = ""
    if canonical_path.is_file():
        canonical = _read(root, CANONICAL)
        for token in REQUIRED_TOKENS:
            if token not in canonical:
                errors.append(
                    f"{CANONICAL} lost durable runtime token: {token}"
                )
        for token in FORBIDDEN_TOKENS:
            if token in canonical:
                errors.append(
                    f"{CANONICAL} owns forbidden execution/provider token: {token}"
                )

    if mirror_path.is_file():
        mirror = _read(root, MIRROR)
    if canonical and mirror and canonical.encode() != mirror.encode():
        errors.append(f"canonical AI mirror drift: {CANONICAL} != {MIRROR}")

    if facade_path.is_file():
        facade = _read(root, FACADE)
        expected = (
            "from skeleton.automation.agents.agent_runtime import *  "
            "# noqa: F401,F403"
        )
        if expected not in facade:
            errors.append("legacy agent-runtime facade does not delegate canonically")
        if "class " in facade or "sqlite3" in facade:
            errors.append("legacy agent-runtime facade regained implementation ownership")

    if workflow_path.is_file():
        workflow = _read(root, AUTO02_WORKFLOW)
        for required in (
            "skeleton/automation/agents/agent_runtime.py",
            "skeleton/ai/agents/core/agent_runtime.py",
            "skeleton/testing/test_agent_runtime_durable.py",
        ):
            if required not in workflow:
                errors.append(
                    f"AUTO-02 workflow does not bind durable agent runtime: {required}"
                )

    try:
        plan = _load_json(root, "machine/ai_master_plan.json")
        volume = _find_volume(plan, "VOL-016")
    except AgentRuntimeVerificationError as exc:
        errors.append(str(exc))
        volume = None

    if volume is None:
        errors.append("VOL-016 is missing from canonical masterplan")
    else:
        requirements = tuple(str(item) for item in volume.get("requirements", ()))
        required_phrases = (
            "agent identity",
            "delegated authority",
            "checkpoint state",
        )
        joined = " ".join(requirements).lower()
        for phrase in required_phrases:
            if phrase not in joined:
                errors.append(
                    f"VOL-016 requirement drift: missing phrase {phrase!r}"
                )
        capabilities = set(str(item) for item in volume.get("capabilities", ()))
        for capability in (
            "agent lifecycle",
            "delegation",
            "agent checkpointing",
        ):
            if capability not in capabilities:
                errors.append(
                    f"VOL-016 capability drift: {capability}"
                )
        gaps = set(str(item) for item in volume.get("gaps", ()))
        expected_gap_markers = {
            "durable agent supervisor needs implementation",
            "agent resource accounting needs convergence",
        }
        if gaps and not gaps.issubset(expected_gap_markers):
            errors.append(
                "VOL-016 contains unexpected implementation gaps: "
                + ", ".join(sorted(gaps - expected_gap_markers))
            )

    boundary_digests: dict[str, str] = {}
    for relative in (CANONICAL, MIRROR, FACADE, RUNTIME_TEST, AUTO02_WORKFLOW):
        path = root / relative
        if path.is_file():
            boundary_digests[relative] = _digest(path.read_bytes())

    return {
        "schema_version": 1,
        "verifier": "independent-agent-runtime-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "canonical": CANONICAL,
        "mirror": MIRROR,
        "boundary_digests": boundary_digests,
        "mirror_digest": (
            None if not mirror else _digest(mirror.encode("utf-8"))
        ),
        "canonical_digest": (
            None if not canonical else _digest(canonical.encode("utf-8"))
        ),
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except AgentRuntimeVerificationError as exc:
        print(f"independent-agent-runtime: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("independent-agent-runtime: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "independent-agent-runtime: OK "
        f"(boundaries={len(receipt['boundary_digests'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
