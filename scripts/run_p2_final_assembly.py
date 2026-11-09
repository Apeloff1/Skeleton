#!/usr/bin/env python3
"""Execute the P2 final-assembly plan and emit digest-bound evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

from skeleton.quality.final_assembly import (
    FinalAssemblyEvidence,
    GateReceipt,
    RiskDisposition,
    evaluate_promotion,
)

ROOT = Path(__file__).resolve().parents[1]


class FinalAssemblyHarnessError(RuntimeError):
    pass


def _load(root: Path, rel: str) -> dict[str, Any]:
    try:
        data = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalAssemblyHarnessError(f"cannot load {rel}: {exc}") from exc
    if not isinstance(data, dict):
        raise FinalAssemblyHarnessError(f"{rel} must contain an object")
    return data


def _ubuntu_version() -> str:
    path = Path("/etc/os-release")
    if not path.is_file():
        return platform.system().lower()
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    if values.get("ID") == "ubuntu" and values.get("VERSION_ID"):
        return f"ubuntu-{values['VERSION_ID']}"
    return values.get("ID", platform.system().lower())


def environment_fingerprint() -> dict[str, str]:
    return {
        "os": _ubuntu_version(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
    }


def _digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def current_git_head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    head = proc.stdout.strip().lower()
    if proc.returncode != 0 or not head or any(ch not in "0123456789abcdef" for ch in head):
        raise FinalAssemblyHarnessError(
            "cannot resolve exact Git HEAD: " + (proc.stderr or proc.stdout)[-2000:]
        )
    if len(head) not in {40, 64}:
        raise FinalAssemblyHarnessError("exact Git HEAD has unexpected object ID length")
    return head


def dependency_snapshot(root: Path) -> tuple[str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        raise FinalAssemblyHarnessError(
            "cannot capture resolved dependency snapshot: "
            + (proc.stderr or proc.stdout)[-2000:]
        )
    normalized = "\n".join(
        sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())
    ) + "\n"
    return normalized, _digest(normalized)


def build_risk_dispositions(
    control: dict[str, Any],
    supplied: list[dict[str, Any]] | None = None,
) -> tuple[RiskDisposition, ...]:
    expected: dict[str, str] = {}
    for binding in control.get("masterplan_bindings", []):
        ref = binding.get("volume_ref")
        for index, _statement in enumerate(binding.get("risks", []), 1):
            risk_id = f"{ref}:risk:{index:03d}"
            expected[risk_id] = f"masterplan:{ref}:risk:{index:03d}"

    provided: dict[str, dict[str, Any]] = {}
    for item in supplied or []:
        if not isinstance(item, dict):
            raise FinalAssemblyHarnessError("risk disposition entries must be objects")
        risk_id = item.get("risk_id")
        if not isinstance(risk_id, str) or not risk_id or risk_id in provided:
            raise FinalAssemblyHarnessError(
                f"duplicate/invalid risk disposition id: {risk_id!r}"
            )
        provided[risk_id] = item
    extra = sorted(set(provided) - set(expected))
    if extra:
        raise FinalAssemblyHarnessError(
            "risk disposition contains unknown IDs: " + ", ".join(extra)
        )

    dispositions: list[RiskDisposition] = []
    for risk_id, default_ref in sorted(expected.items()):
        item = provided.get(risk_id)
        if item is None:
            dispositions.append(
                RiskDisposition(
                    risk_id=risk_id,
                    status="blocking",
                    evidence_refs=(default_ref,),
                )
            )
            continue
        refs = item.get("evidence_refs")
        if not isinstance(refs, list):
            raise FinalAssemblyHarnessError(
                f"{risk_id} evidence_refs must be a list"
            )
        try:
            dispositions.append(
                RiskDisposition(
                    risk_id=risk_id,
                    status=item.get("status"),
                    evidence_refs=tuple(refs),
                    authority_ref=item.get("authority_ref"),
                )
            )
        except (TypeError, ValueError) as exc:
            raise FinalAssemblyHarnessError(
                f"invalid risk disposition {risk_id}: {exc}"
            ) from exc
    return tuple(dispositions)


def execute(
    source_sha: str,
    *,
    root: Path = ROOT,
    builder_id: str = "github-actions-builder",
    verifier_id: str | None = None,
    risk_dispositions: list[dict[str, Any]] | None = None,
) -> tuple[FinalAssemblyEvidence, dict[str, Any]]:
    root = root.resolve()
    control = _load(root, "machine/p2_quality_control.json")
    plan = control.get("final_assembly", {})
    requested_source = str(source_sha).strip().lower()
    actual_head = current_git_head(root)
    if requested_source != actual_head:
        raise FinalAssemblyHarnessError(
            f"source SHA is not exact checked-out HEAD: requested={requested_source} head={actual_head}"
        )
    expected_env = plan.get("environment")
    actual_env = environment_fingerprint()
    if actual_env != expected_env:
        raise FinalAssemblyHarnessError(
            f"release-like environment drift: expected={expected_env} actual={actual_env}"
        )

    dependency_text, dependency_sha = dependency_snapshot(root)
    receipts: list[GateReceipt] = []
    details: list[dict[str, Any]] = []
    for gate in plan.get("gates", []):
        gate_id = gate.get("gate_id")
        argv = gate.get("argv")
        if (
            not isinstance(gate_id, str)
            or not gate_id
            or not isinstance(argv, list)
            or not argv
            or not all(isinstance(x, str) and x for x in argv)
        ):
            raise FinalAssemblyHarnessError("invalid final assembly gate")
        command = list(argv)
        if command[0] == "python":
            command[0] = sys.executable
        proc = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=1200,
            env={**os.environ, "PYTHONPATH": str(root)},
        )
        receipts.append(
            GateReceipt(
                gate_id=gate_id,
                passed=proc.returncode == 0,
                stdout_sha256=_digest(proc.stdout),
                stderr_sha256=_digest(proc.stderr),
            )
        )
        details.append(
            {
                "gate_id": gate_id,
                "returncode": proc.returncode,
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-2000:],
            }
        )

    risks = build_risk_dispositions(control, risk_dispositions)

    verified_at = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if verifier_id is not None
        else None
    )
    evidence = FinalAssemblyEvidence(
        source_sha=actual_head,
        environment=actual_env,
        gate_receipts=tuple(receipts),
        risk_dispositions=risks,
        dependency_snapshot_sha256=dependency_sha,
        builder_id=builder_id,
        verifier_id=verifier_id,
        verified_at_utc=verified_at,
    )
    decision = evaluate_promotion(
        evidence,
        presented_digest=evidence.evidence_digest,
        expected_source_sha=actual_head,
        expected_environment=expected_env,
        required_gate_ids=tuple(gate["gate_id"] for gate in plan.get("gates", [])),
    )
    return evidence, {
        "promotion_ready": decision.ready,
        "promotion_blockers": list(decision.blockers),
        "gate_details": details,
        "dependency_snapshot": dependency_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--builder-id", default="github-actions-builder")
    parser.add_argument("--verifier-id")
    parser.add_argument("--risk-dispositions")
    parser.add_argument("--output")
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    try:
        supplied_risks = None
        if args.risk_dispositions:
            try:
                raw = json.loads(
                    Path(args.risk_dispositions).read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise FinalAssemblyHarnessError(
                    f"cannot load risk disposition file: {exc}"
                ) from exc
            if not isinstance(raw, list):
                raise FinalAssemblyHarnessError(
                    "risk disposition file must contain a JSON list"
                )
            supplied_risks = raw
        evidence, detail = execute(
            args.source_sha,
            root=Path(args.repo_root),
            builder_id=args.builder_id,
            verifier_id=args.verifier_id,
            risk_dispositions=supplied_risks,
        )
    except FinalAssemblyHarnessError as exc:
        print(f"p2 final assembly: FAIL: {exc}", file=sys.stderr)
        return 1

    payload = {
        **evidence.payload(),
        "evidence_digest": evidence.evidence_digest,
        **detail,
    }
    encoded = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if any(not item.passed for item in evidence.gate_receipts):
        return 1
    if not detail["promotion_ready"] and not args.allow_blocked:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
