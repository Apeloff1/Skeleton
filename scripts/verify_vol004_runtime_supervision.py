#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-004 runtime supervision."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("machine/runtime_supervision.json")
CONSTRUCTION = Path("machine/ai_app_construction.json")
MANIFEST = Path("skeleton/app/manifest.json")
MASTERPLAN = Path("machine/ai_master_plan.json")

EXPECTED_SCHEMA = "skeleton.architecture.runtime_supervision.v2"
EXPECTED_VERSION = "1.2.0"
QUALIFICATION_GAP = (
    "independent exact-head VOL-004 Runtime Supervision Closure "
    "qualification remains pending"
)
ALLOWED_MODES = {
    "async_task_cancellation",
    "bounded_blocking_token_fence",
    "cooperative_token",
    "delegated_durable_cancel",
}

REQUIRED_VOL004_PATHS = {
    "machine/runtime_supervision.json",
    "scripts/check_architecture_runtime_supervision.py",
    "skeleton/kernel/runtime_supervision.py",
    "skeleton/ai/runtime/kernel/runtime_supervision.py",
    "backend/server.py",
    "backend/core/engine_client.py",
    "skeleton/api/engine_runtime.py",
    "skeleton/api/engine_service.py",
    "skeleton/provider_runtime.py",
    "machine/ai_app_construction.json",
    "docs/architecture/RUNTIME_SUPERVISION.md",
    ".github/workflows/vol004-runtime-supervision.yml",
}
REQUIRED_VOL004_TESTS = {
    "tests/test_architecture_runtime_supervision.py",
    "skeleton/testing/test_vol004_runtime_supervision_v2.py",
    "skeleton/testing/test_kernel_supervisor_cancellation.py",
    "tests/test_vol004_runtime_supervision_independent.py",
}
REQUIRED_VOL004_EVALUATIONS = {
    "python scripts/check_architecture_runtime_supervision.py --json",
    ".github/workflows/vol004-runtime-supervision.yml",
    "scripts/verify_vol004_runtime_supervision.py",
}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read JSON authority {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("invalid repository path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("invalid repository path")
    if pure.as_posix() != value:
        raise ValueError("repository path is not canonical")
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _verify_lifecycle(contract: dict[str, Any], errors: list[str]) -> None:
    life = contract.get("lifecycle_semantics")
    if not isinstance(life, dict):
        errors.append("lifecycle_semantics must be an object")
        return
    if life.get("phases") != ["starting", "ready", "draining", "stopped", "failed"]:
        errors.append("lifecycle phases drifted")
    if life.get("work_admission_phase") != "ready":
        errors.append("only ready may admit ordinary work")
    if life.get("terminal_phases") != ["stopped", "failed"]:
        errors.append("terminal lifecycle phases drifted")
    for key in (
        "draining_revokes_admission",
        "restart_requires_terminal_generation",
        "restart_refreshes_cancellation_token",
        "monotonic_receipts",
    ):
        if life.get(key) is not True:
            errors.append(f"lifecycle_semantics.{key} must be true")

    leases = life.get("work_leases")
    if not isinstance(leases, dict):
        errors.append("work_leases must be an object")
    else:
        for key in ("required", "generation_bound", "stop_requires_quiescence"):
            if leases.get(key) is not True:
                errors.append(f"work_leases.{key} must be true")
        if leases.get("duplicate_work_id_policy") != "deny":
            errors.append("duplicate work IDs must fail closed")
        if leases.get("stale_generation_release_policy") != "deny":
            errors.append("stale generation release must fail closed")
        if leases.get("startup_recovery_exception") != "engine durable recovery only":
            errors.append("startup recovery exception drifted")
        if leases.get("shutdown_reconciliation") != "synchronous_before_shutdown_returns":
            errors.append("shutdown reconciliation must remain synchronous")
        if leases.get("task_identity_binding") is not True:
            errors.append("work leases must bind exact task identity")

    public = life.get("public_drain_response")
    if not isinstance(public, dict):
        errors.append("public_drain_response must be an object")
    else:
        if public.get("status_code") != 503:
            errors.append("public drain response must remain 503")
        if public.get("retry_after_seconds") != 1:
            errors.append("public drain Retry-After must remain one second")
        if "active_work_ids" not in (public.get("forbidden_lifecycle_fields") or []):
            errors.append("public drain must hide active_work_ids")
        if "cancellation" not in (public.get("forbidden_lifecycle_fields") or []):
            errors.append("public drain must hide cancellation detail")


def _collect_bindings(contract: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    services = contract.get("services")
    if not isinstance(services, list) or not services:
        errors.append("services must be a non-empty list")
        return bindings
    seen: set[str] = set()
    for service in services:
        if not isinstance(service, dict):
            errors.append("service row must be an object")
            continue
        service_id = service.get("service")
        if not isinstance(service_id, str) or not service_id:
            errors.append("service id must be non-empty")
            continue
        if service_id in seen:
            errors.append(f"duplicate service: {service_id}")
        seen.add(service_id)
        for group in ("lifecycle_bindings", "connector_bindings", "cancellation_bindings"):
            rows = service.get(group, [])
            if not isinstance(rows, list):
                errors.append(f"{service_id}.{group} must be a list")
                continue
            for binding in rows:
                if isinstance(binding, dict):
                    bindings.append(binding)
                else:
                    errors.append(f"{service_id}.{group} binding must be an object")
    return bindings


def _verify_binding_symbols(
    root: Path,
    bindings: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, str]:
    digests: dict[str, str] = {}
    for binding in bindings:
        try:
            relative = _repo_path(binding.get("path"))
        except ValueError:
            errors.append("binding contains invalid path")
            continue
        path = root / relative
        if not path.is_file():
            errors.append(f"binding source missing: {relative}")
            continue
        data = path.read_bytes()
        source = data.decode("utf-8")
        digests[relative] = hashlib.sha256(data).hexdigest()
        symbols = binding.get("required_symbols")
        if not isinstance(symbols, list) or not symbols:
            errors.append(f"{relative} required_symbols must be non-empty")
            continue
        if len(symbols) != len(set(symbols)):
            errors.append(f"{relative} required_symbols contains duplicates")
        for symbol in symbols:
            if not isinstance(symbol, str) or not symbol:
                errors.append(f"{relative} has invalid required symbol")
            elif symbol not in source:
                errors.append(f"{relative} missing required runtime symbol: {symbol}")
    return digests


def _verify_manifest_alignment(
    contract: dict[str, Any],
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    services = manifest.get("services")
    if not isinstance(services, list):
        errors.append("runtime manifest services must be a list")
        return
    by_name = {
        row.get("name"): row
        for row in services
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    for row in contract.get("services") or []:
        if not isinstance(row, dict):
            continue
        service_id = row.get("service")
        manifest_row = by_name.get(service_id)
        if manifest_row is None:
            errors.append(f"supervised service missing from runtime manifest: {service_id}")
            continue
        if manifest_row.get("depends_on") != row.get("expected_dependencies"):
            errors.append(f"runtime dependency drift for service {service_id}")


def _verify_connectors(
    contract: dict[str, Any],
    construction: dict[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, str]:
    provider_surfaces = construction.get("provider_surfaces")
    if not isinstance(provider_surfaces, list):
        errors.append("provider_surfaces must be a list")
        return {}
    selected = {
        row.get("id"): row
        for row in provider_surfaces
        if isinstance(row, dict) and row.get("network_transport_owner") is True
    }
    connectors = contract.get("connectors")
    if not isinstance(connectors, list) or not connectors:
        errors.append("connectors must be non-empty")
        return {}

    seen: set[str] = set()
    selected_refs: set[str] = set()
    digests: dict[str, str] = {}
    for connector in connectors:
        if not isinstance(connector, dict):
            errors.append("connector row must be object")
            continue
        cid = connector.get("id")
        if not isinstance(cid, str) or not cid or cid in seen:
            errors.append(f"invalid/duplicate connector id: {cid!r}")
            continue
        seen.add(cid)
        mode = connector.get("cancellation_mode")
        if mode not in ALLOWED_MODES:
            errors.append(f"connector {cid} has invalid cancellation mode")
        if connector.get("bounded_timeout") is not True:
            errors.append(f"connector {cid} must have bounded timeout")
        if connector.get("late_result_fencing") is not True:
            errors.append(f"connector {cid} must fence late results")
        if mode == "async_task_cancellation" and connector.get("deadline_propagation") is not True:
            errors.append(f"connector {cid} must propagate deadlines")
        if mode in {"bounded_blocking_token_fence", "delegated_durable_cancel"} and connector.get("retry_wait_cancellable") is not True:
            errors.append(f"connector {cid} retry wait must be cancellable")

        try:
            owner = _repo_path(connector.get("owner"))
        except ValueError:
            errors.append(f"connector {cid} owner path invalid")
            continue
        owner_path = root / owner
        if not owner_path.is_file():
            errors.append(f"connector {cid} owner missing: {owner}")
            continue
        digests[cid] = hashlib.sha256(owner_path.read_bytes()).hexdigest()
        required_symbols = connector.get("required_symbols")
        if not isinstance(required_symbols, list) or not required_symbols:
            errors.append(f"connector {cid} required_symbols must be non-empty")
        else:
            source = owner_path.read_text(encoding="utf-8")
            for symbol in required_symbols:
                if symbol not in source:
                    errors.append(f"connector {cid} missing required symbol: {symbol}")

        surface_id = connector.get("surface_id")
        if surface_id is not None:
            selected_refs.add(surface_id)
            surface = selected.get(surface_id)
            if surface is None:
                errors.append(f"connector {cid} references undeclared network surface")
            else:
                if connector.get("owner") != surface.get("owner"):
                    errors.append(f"connector {cid} owner drifted from construction surface")
                if connector.get("family") != surface.get("family"):
                    errors.append(f"connector {cid} family drifted from construction surface")

    if selected_refs != set(selected):
        errors.append(
            "network connector coverage mismatch: "
            f"expected={sorted(selected)} actual={sorted(selected_refs)}"
        )
    if seen != set(selected) | {"backend-engine"}:
        errors.append("connector inventory contains missing or undeclared connectors")
    return digests


def _verify_mirror(contract: dict[str, Any], root: Path, errors: list[str]) -> dict[str, str]:
    sources = contract.get("sources")
    if not isinstance(sources, dict):
        errors.append("sources must be an object")
        return {}
    try:
        canonical = _repo_path(sources.get("shared_lifecycle"))
        mirror = _repo_path(sources.get("governed_lifecycle_mirror"))
    except ValueError:
        errors.append("runtime lifecycle mirror paths are invalid")
        return {}
    canonical_path, mirror_path = root / canonical, root / mirror
    if not canonical_path.is_file() or not mirror_path.is_file():
        errors.append("runtime lifecycle canonical/mirror file missing")
        return {}
    canonical_bytes = canonical_path.read_bytes()
    mirror_bytes = mirror_path.read_bytes()
    if canonical_bytes != mirror_bytes:
        errors.append("runtime lifecycle governed mirror drifted")
    return {
        "canonical": hashlib.sha256(canonical_bytes).hexdigest(),
        "mirror": hashlib.sha256(mirror_bytes).hexdigest(),
    }


def _verify_masterplan(master: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        errors.append("masterplan volumes must be a list")
        return {}
    volume = next(
        (
            row for row in volumes
            if isinstance(row, dict) and row.get("key") == "VOL-004"
        ),
        None,
    )
    if volume is None:
        errors.append("masterplan missing VOL-004")
        return {}
    if volume.get("title") != "Kernel & Execution Foundation":
        errors.append("VOL-004 title drifted")
    if volume.get("implementation_status") not in {"implemented", "hardened", "verified"}:
        errors.append("VOL-004 implementation status below implemented")

    paths = set(volume.get("implementation_paths") or [])
    tests = set(volume.get("tests") or [])
    evaluations = set(volume.get("evaluations") or [])
    for label, required, actual in (
        ("implementation path", REQUIRED_VOL004_PATHS, paths),
        ("test", REQUIRED_VOL004_TESTS, tests),
        ("evaluation", REQUIRED_VOL004_EVALUATIONS, evaluations),
    ):
        missing = sorted(required - actual)
        if missing:
            errors.append(f"VOL-004 {label} binding incomplete: {', '.join(missing)}")

    gaps = list(volume.get("gaps") or [])
    if gaps not in ([QUALIFICATION_GAP], []):
        errors.append("VOL-004 gap state contains unexpected obligations")
    completion = volume.get("completion_checkbox")
    if gaps and completion is not False:
        errors.append("VOL-004 cannot remain signed with pending qualification")
    if not gaps and completion is not True:
        errors.append("VOL-004 cannot clear qualification gap before signoff")
    if not gaps and volume.get("implementation_status") != "verified":
        errors.append("signed VOL-004 must have verified implementation status")

    binding = {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "completion_checkbox_mark": volume.get("completion_checkbox_mark"),
        "enterprise_grade_state": volume.get("enterprise_grade_state"),
        "enterprise_grade_target": volume.get("enterprise_grade_target"),
        "gaps": gaps,
        "implementation_paths": sorted(paths),
        "tests": sorted(tests),
        "evaluations": sorted(evaluations),
    }
    binding["binding_digest"] = _digest(binding)
    return binding


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    contract = _load(root / CONTRACT)
    construction = _load(root / CONSTRUCTION)
    manifest = _load(root / MANIFEST)
    master = _load(root / MASTERPLAN)

    if contract.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("runtime supervision schema drifted")
    if contract.get("contract_version") != EXPECTED_VERSION:
        errors.append("runtime supervision contract version drifted")
    if contract.get("status") != "active":
        errors.append("runtime supervision contract must be active")

    binding = contract.get("masterplan_binding")
    if not isinstance(binding, dict):
        errors.append("runtime supervision masterplan_binding missing")
    else:
        if binding.get("volume_ref") != "VOL-004":
            errors.append("runtime supervision bound to wrong volume")
        if binding.get("qualification_gap") != QUALIFICATION_GAP:
            errors.append("runtime supervision qualification gap drifted")

    _verify_lifecycle(contract, errors)
    bindings = _collect_bindings(contract, errors)
    binding_digests = _verify_binding_symbols(root, bindings, errors)
    _verify_manifest_alignment(contract, manifest, errors)
    connector_digests = _verify_connectors(contract, construction, root, errors)
    mirror = _verify_mirror(contract, root, errors)
    volume = _verify_masterplan(master, errors)
    if isinstance(binding, dict) and volume:
        pending = list(volume.get("gaps") or []) == [QUALIFICATION_GAP]
        expected_state = "implemented_verification_pending" if pending else "verified"
        if binding.get("implementation_state") != expected_state:
            errors.append(
                "runtime supervision implementation_state/masterplan drift: "
                f"expected {expected_state}"
            )

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol004-runtime-supervision-v1",
        "volume": "VOL-004",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "contract_digest": hashlib.sha256((root / CONTRACT).read_bytes()).hexdigest(),
        "binding_digests": binding_digests,
        "connector_digests": connector_digests,
        "lifecycle_mirror": mirror,
        "volume_binding": volume,
        "errors": errors,
        "valid": not errors,
    }
    receipt["receipt_digest"] = _digest(receipt)
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
            "verifier": "independent-vol004-runtime-supervision-v1",
            "volume": "VOL-004",
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _digest(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-004 independent runtime supervision: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-004 independent runtime supervision: FAIL")
        for error in receipt["errors"]:
            print(f" - {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
