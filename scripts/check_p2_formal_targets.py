#!/usr/bin/env python3
"""Execute the masterplan-bound P2 finite-state formal targets."""
from __future__ import annotations

import argparse
import hashlib
from skeleton.contracts import ai_execution as ai_execution_contract
from skeleton.contracts import operation as operation_contract
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.quality.formal import FormalModelError, check_finite_state_model

ROOT = Path(__file__).resolve().parents[1]
CONTROL = Path("machine/p2_quality_control.json")
MASTER = Path("machine/ai_master_plan.json")
CATALOGUE = Path("machine/state_machine_catalogue.json")

_FORMAL_MODULES = {
    "skeleton.contracts.operation": operation_contract,
    "skeleton.contracts.ai_execution": ai_execution_contract,
}


class FormalTargetError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalTargetError(f"cannot load {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FormalTargetError(f"{path} must contain an object")
    return data


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    control = _load(root / CONTROL)
    master = _load(root / MASTER)
    catalogue = _load(root / CATALOGUE)

    vol = next(
        (v for v in master.get("volumes", []) if v.get("key") == "VOL-081"),
        None,
    )
    if not isinstance(vol, dict):
        raise FormalTargetError("VOL-081 missing from masterplan")
    expected_requirements = {
        f"REQ:VOL-081:{i:03d}"
        for i, _ in enumerate(vol.get("requirements", []), 1)
    }
    if len(expected_requirements) != 3:
        raise FormalTargetError("VOL-081 requirement identity drift")

    by_source = {
        row.get("source"): row
        for row in catalogue.get("state_machines", [])
        if isinstance(row, dict)
    }

    targets = control.get("formal_methods", {}).get("targets")
    if not isinstance(targets, list) or len(targets) != 2:
        raise FormalTargetError("exactly two P0 formal targets are required")

    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            raise FormalTargetError("formal target must be an object")
        target_id = target.get("target_id")
        if not isinstance(target_id, str) or not target_id or target_id in seen:
            raise FormalTargetError(f"invalid/duplicate formal target: {target_id!r}")
        seen.add(target_id)

        source = target.get("source")
        if not isinstance(source, str) or not (root / source).is_file():
            raise FormalTargetError(f"{target_id} source missing: {source!r}")
        if set(target.get("requirement_refs", [])) != expected_requirements:
            raise FormalTargetError(f"{target_id} requirement trace drift")
        test_refs = target.get("test_refs")
        if not isinstance(test_refs, list) or not test_refs:
            raise FormalTargetError(f"{target_id} requires test refs")
        for ref in test_refs:
            if not isinstance(ref, str) or ref.startswith("planned:") or not (root / ref).is_file():
                raise FormalTargetError(f"{target_id} test ref is not executable: {ref!r}")

        cat = by_source.get(source)
        if not isinstance(cat, dict):
            raise FormalTargetError(f"{target_id} source not in state-machine catalogue")
        for field in ("enum_symbol", "transition_symbol", "terminal_symbol"):
            if target.get(field) != cat.get(field):
                raise FormalTargetError(f"{target_id} catalogue {field} drift")

        module_name = target.get("module")
        if module_name not in _FORMAL_MODULES:
            raise FormalTargetError(
                f"{target_id} module is not an approved formal target: {module_name!r}"
            )
        module = _FORMAL_MODULES[module_name]
        try:
            enum_cls = getattr(module, target["enum_symbol"])
            transitions = getattr(module, target["transition_symbol"])
            terminals = getattr(module, target["terminal_symbol"])
        except AttributeError as exc:
            raise FormalTargetError(f"{target_id} source symbol missing") from exc

        states = set(enum_cls)
        try:
            initial = enum_cls(target["initial_state"])
        except (ValueError, TypeError) as exc:
            raise FormalTargetError(f"{target_id} initial state invalid") from exc

        try:
            result = check_finite_state_model(
                states=states,
                transitions=transitions,
                terminals=terminals,
                initial=initial,
            )
        except FormalModelError as exc:
            raise FormalTargetError(f"{target_id} counterexample: {exc}") from exc

        digest = hashlib.sha256((root / source).read_bytes()).hexdigest()
        results.append(
            {
                "target_id": target_id,
                "state_count": result.state_count,
                "edge_count": result.edge_count,
                "terminal_count": result.terminal_count,
                "source_sha256": digest,
            }
        )

    return {"status": "valid", "target_count": len(results), "targets": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except FormalTargetError as exc:
        print(f"p2 formal targets: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
