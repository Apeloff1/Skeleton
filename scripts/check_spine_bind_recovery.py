#!/usr/bin/env python3
"""Fail-closed control for the P2 bind recovery checkpoint tranche."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any


class SpineBindRecoveryControlError(RuntimeError):
    """The bind recovery control found drift or an incomplete evidence surface."""


MODULES = (
    "spine_bind_snapshot.py",
    "spine_bind_recovery.py",
    "spine_bind_checkpoint.py",
    "spine_bind_checkpoint_replay.py",
    "spine_bind_checkpoint_tenant.py",
    "spine_bind_checkpoint_chain.py",
    "spine_bind_bundle.py",
    "spine_bind_bundle_verify.py",
    "spine_bind_restore_receipt.py",
    "spine_bind_restore_verify.py",
    "spine_bind_restore_journal.py",
    "spine_bind_restore_replay.py",
    "spine_bind_restore_tenant.py",
    "spine_bind_restore_chain.py",
    "spine_bind_restore_continuity.py",
    "spine_bind_restore_export.py",
    "spine_bind_restore_export_verify.py",
)

MIRRORED = ("__init__.py", "spine_manifest.py", "spine_masterplan.py", *MODULES)

EXPECTED_SEAMS = {
    "bind-snapshot": "bind-snapshot-stays-unactivated",
    "bind-recovery": "recovery-plan-does-not-activate",
    "bind-checkpoint": "checkpoint-is-immutable-and-unactivated",
    "bind-checkpoint-replay": "checkpoint-replay-does-not-insert",
    "bind-checkpoint-tenant": "checkpoint-tenant-isolated",
    "bind-checkpoint-chain": "checkpoint-hash-chain",
    "bind-bundle": "checkpoint-bundle-is-not-activation",
    "bind-bundle-verify": "bundle-verification-does-not-activate",
    "bind-restore-receipt": "restore-receipt-is-not-activation",
    "bind-restore-verify": "restore-verification-does-not-activate",
    "bind-restore-journal": "restore-journal-is-append-only",
    "bind-restore-replay": "restore-replay-does-not-insert",
    "bind-restore-tenant": "restore-journal-tenant-isolated",
    "bind-restore-chain": "restore-journal-hash-chain",
    "bind-restore-continuity": "restore-continuity-does-not-activate",
    "bind-restore-export": "portable-evidence-is-not-activation",
    "bind-restore-export-verify": "portable-evidence-verification-does-not-activate",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _literal_assignment(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise SpineBindRecoveryControlError(f"{path}: missing literal {name}")


def verify_mirror_parity(root: Path) -> dict[str, str]:
    canonical = root / "skeleton" / "persistence"
    mirror = root / "skeleton" / "ai" / "runtime" / "persistence"
    digests: dict[str, str] = {}
    for name in MIRRORED:
        left = canonical / name
        right = mirror / name
        if not left.is_file() or not right.is_file():
            raise SpineBindRecoveryControlError(f"missing mirrored file: {name}")
        left_bytes = left.read_bytes()
        right_bytes = right.read_bytes()
        if left_bytes != right_bytes:
            raise SpineBindRecoveryControlError(f"AI-tree mirror drift: {name}")
        digests[name] = _sha256(left_bytes)
    return digests


def verify_manifest(root: Path) -> dict[str, Any]:
    path = root / "skeleton" / "persistence" / "spine_manifest.py"
    seams = _literal_assignment(path, "SEAMS")
    if not isinstance(seams, tuple):
        raise SpineBindRecoveryControlError("SEAMS must remain a tuple")
    if len(seams) != 91:
        raise SpineBindRecoveryControlError(
            f"expected 91 spine seams, found {len(seams)}"
        )
    names = [row[0] for row in seams]
    if len(names) != len(set(names)):
        raise SpineBindRecoveryControlError("spine seam names must be unique")
    laws = dict(seams)
    for name, law in EXPECTED_SEAMS.items():
        if laws.get(name) != law:
            raise SpineBindRecoveryControlError(
                f"missing or changed recovery seam: {name}"
            )
    return {
        "count": len(seams),
        "recovery_seams": sorted(EXPECTED_SEAMS),
    }


def verify_masterplan(root: Path) -> dict[str, Any]:
    path = root / "docs" / "plan" / "P2_SPINE_MASTERPLAN.md"
    text = path.read_text(encoding="utf-8")
    required = [
        "- Bind card sealed: 100%",
        "Expect `count` 91",
        "Bind snapshot",
        "Bind recovery",
        "Bind checkpoint",
        "Bind checkpoint replay",
        "Bind checkpoint tenant",
        "Bind checkpoint chain",
        "Bind bundle",
        "Bind bundle verify",
        "`ready`, `activated`, `apply_landed`, `live_motor`, "
        "`dispatcher_running`, `ci_green`, and `merged` remain false",
    ]
    missing = [fragment for fragment in required if fragment not in text]
    if missing:
        raise SpineBindRecoveryControlError(
            "masterplan recovery control drift: " + " | ".join(missing)
        )
    return {
        "bind_card_percent": 100,
        "manifest_count": 91,
        "activation_claimed": False,
    }


def build_report(root: Path) -> dict[str, Any]:
    root = root.resolve()
    mirrors = verify_mirror_parity(root)
    manifest = verify_manifest(root)
    masterplan = verify_masterplan(root)
    return {
        "schema_version": 1,
        "control": "p2-bind-recovery-v1",
        "valid": True,
        "mirror_count": len(mirrors),
        "mirror_digests": mirrors,
        "manifest": manifest,
        "masterplan": masterplan,
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        report = build_report(root)
    except (OSError, SyntaxError, ValueError, SpineBindRecoveryControlError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "control": "p2-bind-recovery-v1",
                    "valid": False,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
