#!/usr/bin/env python3
"""Fail-closed PR impact resolution for the P2 traceability spine."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

_TRACE_CONTROL_EXACT = {
    ".github/workflows/p2-traceability-spine.yml",
    "docs/architecture/P2_TRACEABILITY_SPINE.md",
    "machine/requirement_registry.json",
    "machine/capability_taxonomy.json",
    "machine/nfr_registry.json",
    "machine/behavior_specifications.json",
    "machine/state_machine_catalogue.json",
    "machine/interface_standard.json",
    "machine/schema_registry.json",
    "machine/compatibility_model.json",
    "machine/protocol_registry.json",
    "machine/maturity_registry.json",
    "machine/master_traceability.json",
    "scripts/check_master_traceability.py",
    "scripts/check_nfr_registry.py",
    "scripts/check_traceability_spine.py",
    "scripts/check_trace_pr_impact.py",
    "tests/test_master_traceability.py",
    "tests/test_nfr_registry.py",
    "tests/test_traceability_spine.py",
    "tests/test_internal_protocol_envelope.py",
}
_TRACE_CONTROL_PREFIXES = (
    "machine/traceability/",
)


class TraceImpactError(RuntimeError):
    pass


def _load_validator(root: Path):
    path = root / "scripts/check_traceability_spine.py"
    spec = importlib.util.spec_from_file_location("check_traceability_spine", path)
    if spec is None or spec.loader is None:
        raise TraceImpactError("cannot load traceability spine validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _changed_files(root: Path, base: str, head: str) -> list[str]:
    for value, name in ((base, "base"), (head, "head")):
        if not value or any(ch not in "0123456789abcdefABCDEF" for ch in value):
            raise TraceImpactError(f"{name} must be a hexadecimal Git object id")
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRT", base, head, "--"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TraceImpactError(f"git diff failed: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise TraceImpactError(f"git diff failed with exit {proc.returncode}: {detail}")
    result = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if len(result) > 10000:
        raise TraceImpactError("changed-file set exceeds impact-analysis bound")
    return result


def _is_control_path(path: str) -> bool:
    return path in _TRACE_CONTROL_EXACT or any(
        path.startswith(prefix) for prefix in _TRACE_CONTROL_PREFIXES
    )


def validate(root: Path, base: str, head: str) -> dict[str, object]:
    root = root.resolve()
    changed = _changed_files(root, base, head)
    if not changed:
        raise TraceImpactError("PR impact set is empty")

    module = _load_validator(root)
    try:
        spine = module.validate(root, changed_files=changed)
    except Exception as exc:
        raise TraceImpactError(f"traceability validation failed: {exc}") from exc

    impact = spine.get("impact")
    if not isinstance(impact, dict):
        raise TraceImpactError("traceability validator did not return impact data")

    master_unmapped = set(impact.get("unmapped_changed_files", []))
    unresolved = sorted(
        path
        for path in master_unmapped
        if not _is_control_path(path)
        and path not in impact.get("maturity_invalidation_by_file", {})
    )
    if unresolved:
        raise TraceImpactError(
            "changed implementation files have no trace/maturity/control mapping: "
            + ", ".join(unresolved)
        )

    control = sorted(path for path in changed if _is_control_path(path))
    resolved = sorted(set(changed) - set(unresolved))
    return {
        "status": "valid",
        "base": base.lower(),
        "head": head.lower(),
        "changed_file_count": len(changed),
        "changed_files": changed,
        "resolved_file_count": len(resolved),
        "control_file_count": len(control),
        "control_files": control,
        "combined_impacted_volume_refs": impact.get(
            "combined_impacted_volume_refs", []
        ),
        "maturity_invalidated_volume_refs": impact.get(
            "maturity_invalidated_volume_refs", []
        ),
        "unresolved_files": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(
            Path(args.repo_root),
            args.base,
            args.head,
        )
    except TraceImpactError as exc:
        print(f"trace PR impact: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "trace PR impact: OK "
            f"({result['changed_file_count']} changed files, "
            f"{len(result['combined_impacted_volume_refs'])} impacted volumes)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
