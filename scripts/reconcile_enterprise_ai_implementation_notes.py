#!/usr/bin/env python3
"""Reconcile derived enterprise dossiers from the canonical AI masterplan.

Dry-run/check by default. --write is a privileged, explicitly requested
maintenance operation. This never creates signature evidence, changes the
authoritative plan, or upgrades a volume's enterprise-grade target.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
INDEX = Path("machine/enterprise_ai_implementation_notes_index.json")
FIELDS = {
    "requirements": ("requirements", 4),
    "capabilities": ("capabilities", 4),
    "contracts": ("contracts", 6),
    "canonical_paths": ("implementation_paths", 8),
    "risks": ("risks", 4),
    "gaps": ("gaps", 4),
    "tests": ("tests", 8),
    "evaluations": ("evaluations", 6),
    "existing_evidence": ("evidence", 8),
}
META = {
    "title": "title",
    "depth_pass": "depth_pass",
    "legacy_implementation_status": "implementation_status",
    "enterprise_grade_state": "enterprise_grade_state",
    "enterprise_grade_target": "enterprise_grade_target",
    "enterprise_superiority_profile": "enterprise_superiority_profile",
}


class DossierReconciliationError(ValueError):
    pass


def _distinct_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DossierReconciliationError(f"duplicate object key: {key}")
        out[key] = value
    return out


def _reject_constant(value):
    raise DossierReconciliationError(f"non-finite JSON: {value}")


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_distinct_pairs, parse_constant=_reject_constant)
    if not isinstance(data, dict):
        raise DossierReconciliationError(f"expected object: {path}")
    return data


def _canonical(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def project_dossier(dossier: dict[str, Any], master: dict[str, Any]) -> tuple[int, int]:
    """Mutate only fields explicitly derived from the matching source volume."""
    if not isinstance(dossier, dict) or not isinstance(master, dict):
        raise DossierReconciliationError("dossier/master must be objects")
    if dossier.get("volume_ref") != master.get("key"):
        raise DossierReconciliationError("dossier cannot project another volume")
    summary = dossier.get("implementation_summary")
    if not isinstance(summary, dict) or set(summary) != set(FIELDS):
        raise DossierReconciliationError("exact derived summary field set required")
    # No source data may be synthesized: absent/malformed master arrays fail
    # rather than concealing loss as an empty summary.
    projected = {}
    for field, (source, limit) in FIELDS.items():
        value = master.get(source)
        if not isinstance(value, list):
            raise DossierReconciliationError(
                f"{dossier['volume_ref']}: source {source} must be an array")
        projected[field] = value[:limit]
    m = s = 0
    for dest, source in META.items():
        if source not in master:
            if dest in dossier:
                del dossier[dest]
                m += 1
        elif dossier.get(dest) != master[source]:
            dossier[dest] = master[source]
            m += 1
    for field, value in projected.items():
        if summary[field] != value:
            summary[field] = value
            s += 1
    # Intentionally leave independent verification records, completion_rule,
    # evidence_policy and implementation_levels untouched.
    return s, m


def reconcile(root: Path, *, write: bool = False) -> dict[str, Any]:
    index = _read(root / INDEX)
    master = _read(root / MASTER)
    volumes = master.get("volumes")
    if not isinstance(volumes, list) or len(volumes) != 421:
        raise DossierReconciliationError("expected canonical 421-volume masterplan")
    by_key = {}
    for volume in volumes:
        if not isinstance(volume, dict):
            raise DossierReconciliationError("invalid volume")
        key = volume.get("key")
        if not isinstance(key, str) or key in by_key:
            raise DossierReconciliationError("duplicate or malformed master volume")
        by_key[key] = volume
    expected = {f"VOL-{i:03d}" for i in range(421)}
    if set(by_key) != expected:
        raise DossierReconciliationError("masterplan has missing/unknown volumes")
    entries = index.get("dossier_files")
    if not isinstance(entries, list) or len(entries) != 11:
        raise DossierReconciliationError("exact 11 verified dossier batches required")

    changed: list[tuple[Path, str]] = []
    found = set()
    summary_changes = metadata_changes = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise DossierReconciliationError("invalid dossier index row")
        name = entry.get("path")
        if not isinstance(name, str) or not name.startswith(
                "machine/enterprise_volume_notes/DP-") or not name.endswith(".json"):
            raise DossierReconciliationError("unsafe dossier path")
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise DossierReconciliationError("non-canonical dossier path")
        path = root / name
        doc = _read(path)
        if doc.get("depth_pass") != entry.get("depth_pass"):
            raise DossierReconciliationError("dossier depth-pass identity drift")
        dossiers = doc.get("dossiers")
        if not isinstance(dossiers, list):
            raise DossierReconciliationError("dossiers must be an array")
        for item in dossiers:
            key = item.get("volume_ref") if isinstance(item, dict) else None
            if key not in by_key or key in found:
                raise DossierReconciliationError("unknown or duplicated volume")
            found.add(key)
            a, b = project_dossier(item, by_key[key])
            summary_changes += a
            metadata_changes += b
        text = _canonical(doc)
        if text != path.read_text(encoding="utf-8"):
            changed.append((path, text))
    if found != expected:
        raise DossierReconciliationError("dossier coverage must be precisely 421 volumes")

    if write:
        # Validate ALL projections and paths before touching any on-disk file.
        # Write individual files atomically; a re-run is idempotent after crash.
        for path, data in changed:
            fd, temp = tempfile.mkstemp(prefix=".enterprise-reconcile-",
                                        suffix=".json", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
                    out.write(data)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)

    return {
        "schema": "skeleton.enterprise_ai.dossier_reconciliation.v1",
        "masterplan_version": master.get("plan_version"),
        "volume_count": len(found),
        "changed_files": [path.relative_to(root).as_posix() for path, _ in changed],
        "summary_changes": summary_changes,
        "metadata_changes": metadata_changes,
        "write_performed": write and bool(changed),
        "current": not changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true",
                        help="Explicitly rewrite derived fields from masterplan")
    args = parser.parse_args()
    try:
        receipt = reconcile(args.root.resolve(), write=args.write)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"dossier reconciliation blocked: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    # Check mode is a strict verifier; write mode reports the work performed.
    return 0 if args.write or receipt["current"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
