#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-019 world-model simulation boundaries.

This verifier intentionally does not import the simulation runtime. It derives
qualification from canonical plan bindings, source/mirror identity, and
independently inspected fail-closed boundary invariants. Behavioral execution
remains a separate workflow job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
PAIRS = (
    (Path("skeleton/simulation/environment.py"), Path("skeleton/ai/simulation/environment.py")),
    (Path("skeleton/simulation/world_model.py"), Path("skeleton/ai/simulation/world_model.py")),
    (Path("skeleton/simulation/scenario_runtime.py"), Path("skeleton/ai/simulation/scenario_runtime.py")),
)
REQUIRED_PATHS = {path.as_posix() for path, _ in PAIRS}
REQUIRED_TESTS = {"skeleton/testing/test_vol019_world_model_contract.py"}

TOKENS = {
    "environment.py": (
        'evidence_class: str = "simulation"',
        "def can_support_real_world_fact",
        "return False",
        "simulation evidence cannot be promoted to real-world fact evidence",
        "reward must be finite numeric",
        "terminal must be boolean",
        "uncertainty must be in [0, 1]",
    ),
    "world_model.py": (
        'evidence_class: str = "simulation"',
        "def can_support_real_world_fact",
        "def can_satisfy_real_postcondition",
        "return False",
        "simulation result cannot satisfy a real-world postcondition",
        "uncertainty propagation must be monotonic",
        "simulation uncertainty cannot decrease across rollout",
        "counterfactual case count exceeds max_cases",
        "for case_id, actions in sorted(normalized)",
    ),
    "scenario_runtime.py": (
        'effect_scope: str = "simulation_only"',
        "simulation authority can never authorize a real-world side effect",
        "simulation action cannot be promoted into real-effect authority",
        "max_total_actions",
        "max_cost_units",
        "max_nodes",
        "uncertainty propagation regressed",
    ),
}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    rows = master.get("volumes")
    volume = next(
        (
            row for row in rows
            if isinstance(row, dict) and row.get("key") == "VOL-019"
        ),
        None,
    ) if isinstance(rows, list) else None
    if not isinstance(volume, dict):
        errors.append("masterplan missing VOL-019")
        volume = {}

    if volume.get("title") != "World Models & Simulation":
        errors.append("VOL-019 title drift")
    if volume.get("implementation_status") not in {"implemented", "hardened", "verified"}:
        errors.append("VOL-019 implementation status below implemented")
    if volume.get("scope") != "canonical-plan":
        errors.append("VOL-019 scope drift")
    missing_paths = sorted(REQUIRED_PATHS - set(volume.get("implementation_paths") or []))
    if missing_paths:
        errors.append("VOL-019 implementation binding incomplete: " + ", ".join(missing_paths))
    missing_tests = sorted(REQUIRED_TESTS - set(volume.get("tests") or []))
    if missing_tests:
        errors.append("VOL-019 test binding incomplete: " + ", ".join(missing_tests))

    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    for phrase in (
        "separated from real-world authority",
        "uncertainty and model assumptions",
        "simulated success to count as real postcondition evidence",
    ):
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"VOL-019 requirement invariant lost: {phrase}")

    source_digests: dict[str, str] = {}
    mirror_digests: dict[str, str] = {}
    for canonical_rel, mirror_rel in PAIRS:
        canonical_path = root / canonical_rel
        mirror_path = root / mirror_rel
        try:
            canonical_bytes = canonical_path.read_bytes()
            mirror_bytes = mirror_path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read simulation source pair {canonical_rel.name}: {type(exc).__name__}")
            continue
        source_digests[canonical_rel.as_posix()] = _sha(canonical_bytes)
        mirror_digests[mirror_rel.as_posix()] = _sha(mirror_bytes)
        if canonical_bytes != mirror_bytes:
            errors.append(f"VOL-019 source/AI mirror drift: {canonical_rel.name}")
        source = canonical_bytes.decode("utf-8")
        for token in TOKENS[canonical_rel.name]:
            if token not in source:
                errors.append(f"VOL-019 invariant missing from {canonical_rel.name}: {token}")

    binding = {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "completion_checkbox_mark": volume.get("completion_checkbox_mark"),
        "gaps": list(volume.get("gaps") or []),
        "implementation_paths": sorted(set(volume.get("implementation_paths") or [])),
        "tests": sorted(set(volume.get("tests") or [])),
    }
    binding["binding_digest"] = _digest_json(binding)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol019-world-model-v1",
        "volume": "VOL-019",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "source_digests": source_digests,
        "mirror_digests": mirror_digests,
        "volume_binding": binding,
        "checked_invariant_count": sum(len(values) for values in TOKENS.values()),
        "errors": errors,
        "valid": not errors,
    }
    receipt["receipt_digest"] = _digest_json(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        receipt = {
            "schema_version": 1,
            "verifier": "independent-vol019-world-model-v1",
            "volume": "VOL-019",
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _digest_json(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(f"VOL-019 independent world-model verification: OK ({receipt['receipt_digest']})")
    else:
        print("VOL-019 independent world-model verification: FAIL")
        for error in receipt["errors"]:
            print(f" - {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
