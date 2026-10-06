#!/usr/bin/env python3
"""Validate the executable VOL-004 cross-service supervision contract.

This verifier intentionally cross-checks independent authorities:
- the masterplan for maturity/gap state;
- the runtime manifest for service topology;
- the construction manifest for network/provider ownership and capabilities;
- the runtime-supervision contract for required semantics;
- concrete source files for implementation bindings.

A contract cannot make itself pass by deleting a hard requirement that is still
implied by the independent construction/runtime manifests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("machine/runtime_supervision.json")
MASTER = Path("machine/ai_master_plan.json")
EXPECTED_SCHEMA = "skeleton.architecture.runtime_supervision.v2"
EXPECTED_CONTRACT_VERSION = "1.2.0"

_OPERATION_CANCELLATION_MODES = frozenset(
    {
        "async_task_cancellation",
        "bounded_blocking_token_fence",
        "cooperative_token",
        "delegated_durable_cancel",
    }
)
_CONNECTOR_CANCELLATION_MODES = (
    _OPERATION_CANCELLATION_MODES | {"composite"}
)
_TRANSPORT_FLAGS = (
    "deadline_propagation",
    "bounded_timeout",
    "retry_wait_cancellable",
    "late_result_fencing",
)
_ENGINE_CAPABILITY_OPERATIONS = {
    "text-generation": "async-text-generation",
    "image-generation": "image-generation",
    "image-variation": "image-variation",
    "image-editing": "image-editing",
    "speech-synthesis": "speech-synthesis",
}


class RuntimeSupervisionError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeSupervisionError(
            f"missing required file: {relative}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeSupervisionError(
            f"invalid JSON in {relative}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeSupervisionError(
            f"{relative} must contain an object"
        )
    return data


def _repo_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or "\\" in value
    ):
        raise RuntimeSupervisionError(
            f"invalid repository path: {value!r}"
        )
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise RuntimeSupervisionError(
            f"invalid repository path: {value!r}"
        )
    if pure.as_posix() != value:
        raise RuntimeSupervisionError(
            f"repository path is not canonical: {value!r}"
        )
    return value


def _require_symbols(
    root: Path,
    binding: dict[str, Any],
    label: str,
) -> int:
    path = _repo_path(binding.get("path"))
    target = root / path
    if not target.is_file():
        raise RuntimeSupervisionError(
            f"{label} source missing: {path}"
        )
    text = target.read_text(encoding="utf-8")
    symbols = binding.get("required_symbols")
    if not isinstance(symbols, list) or not symbols:
        raise RuntimeSupervisionError(
            f"{label} required_symbols must be non-empty"
        )
    if len(symbols) != len(set(symbols)):
        raise RuntimeSupervisionError(
            f"{label} required_symbols contains duplicates"
        )
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol:
            raise RuntimeSupervisionError(
                f"{label} contains invalid required symbol"
            )
        if symbol not in text:
            raise RuntimeSupervisionError(
                f"{label} required runtime symbol missing "
                f"from {path}: {symbol!r}"
            )
    return len(symbols)


def _validate_masterplan_binding(
    contract: dict[str, Any],
    master: dict[str, Any],
) -> dict[str, Any]:
    binding = contract.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise RuntimeSupervisionError(
            "masterplan_binding must be an object"
        )
    if binding.get("volume_ref") != "VOL-004":
        raise RuntimeSupervisionError(
            "runtime supervision volume_ref must be VOL-004"
        )

    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise RuntimeSupervisionError(
            "masterplan volumes must be a list"
        )
    volume = next(
        (
            item
            for item in volumes
            if isinstance(item, dict)
            and item.get("key") == "VOL-004"
        ),
        None,
    )
    if not isinstance(volume, dict):
        raise RuntimeSupervisionError(
            "VOL-004 is missing from the masterplan"
        )
    if binding.get("title") != volume.get("title"):
        raise RuntimeSupervisionError(
            "runtime supervision title drifted from VOL-004"
        )
    if volume.get("implementation_status") != "implemented":
        raise RuntimeSupervisionError(
            "VOL-004 implementation status must remain implemented"
        )

    closed = binding.get("closed_implementation_gap_texts")
    if not isinstance(closed, list) or len(closed) != 2:
        raise RuntimeSupervisionError(
            "VOL-004 must bind the two closed implementation gaps"
        )
    if any(
        not isinstance(item, str) or not item.strip()
        for item in closed
    ):
        raise RuntimeSupervisionError(
            "closed implementation gap text is invalid"
        )
    if len(closed) != len(set(closed)):
        raise RuntimeSupervisionError(
            "closed implementation gaps contain duplicates"
        )

    current_gaps = volume.get("gaps")
    if not isinstance(current_gaps, list):
        raise RuntimeSupervisionError(
            "VOL-004 gaps must be a list"
        )
    resurrected = sorted(set(closed) & set(current_gaps))
    if resurrected:
        raise RuntimeSupervisionError(
            "closed VOL-004 implementation gap reappeared: "
            + ", ".join(resurrected)
        )

    remaining = binding.get("remaining_verification_gap_text")
    if not isinstance(remaining, str) or not remaining.strip():
        raise RuntimeSupervisionError(
            "remaining verification gap must be non-empty"
        )
    if (
        binding.get("completion_requires_independent_exact_head")
        is not True
    ):
        raise RuntimeSupervisionError(
            "VOL-004 completion must require independent exact-head evidence"
        )

    complete = volume.get("completion_checkbox")
    mark = volume.get("completion_checkbox_mark")
    if type(complete) is not bool:
        raise RuntimeSupervisionError(
            "VOL-004 completion checkbox must be boolean"
        )
    if complete:
        if mark != "[x]":
            raise RuntimeSupervisionError(
                "completed VOL-004 must have [x] completion mark"
            )
        if current_gaps:
            raise RuntimeSupervisionError(
                "completed VOL-004 cannot retain gaps"
            )
    else:
        if mark != "[ ]":
            raise RuntimeSupervisionError(
                "incomplete VOL-004 must have [ ] completion mark"
            )
        if current_gaps != [remaining]:
            raise RuntimeSupervisionError(
                "unsigned VOL-004 must retain exactly the independent "
                "exact-head verification gap"
            )

    return volume


def _validate_lifecycle_semantics(
    root: Path,
    contract: dict[str, Any],
) -> tuple[int, int]:
    lifecycle = contract.get("lifecycle_semantics")
    if not isinstance(lifecycle, dict):
        raise RuntimeSupervisionError(
            "lifecycle_semantics must be an object"
        )
    if lifecycle.get("phases") != [
        "starting",
        "ready",
        "draining",
        "stopped",
        "failed",
    ]:
        raise RuntimeSupervisionError(
            "lifecycle phases drifted"
        )
    if lifecycle.get("work_admission_phase") != "ready":
        raise RuntimeSupervisionError(
            "only ready may admit normal work"
        )
    for key in (
        "draining_revokes_admission",
        "restart_requires_terminal_generation",
        "restart_refreshes_cancellation_token",
        "monotonic_receipts",
    ):
        if lifecycle.get(key) is not True:
            raise RuntimeSupervisionError(
                f"lifecycle_semantics.{key} must be true"
            )
    if lifecycle.get("terminal_phases") != [
        "stopped",
        "failed",
    ]:
        raise RuntimeSupervisionError(
            "terminal lifecycle phases drifted"
        )

    expected_receipt_fields = [
        "service_id",
        "sequence",
        "generation",
        "from_phase",
        "to_phase",
        "reason",
        "at_monotonic",
        "cancellation",
        "inflight_work",
    ]
    if lifecycle.get("receipt_fields") != expected_receipt_fields:
        raise RuntimeSupervisionError(
            "lifecycle receipt shape drifted"
        )

    work_leases = lifecycle.get("work_leases")
    if not isinstance(work_leases, dict):
        raise RuntimeSupervisionError(
            "lifecycle work_leases must be an object"
        )
    for key in (
        "required",
        "generation_bound",
        "stop_requires_quiescence",
    ):
        if work_leases.get(key) is not True:
            raise RuntimeSupervisionError(
                f"lifecycle work_leases.{key} must be true"
            )
    if work_leases.get("duplicate_work_id_policy") != "deny":
        raise RuntimeSupervisionError(
            "duplicate work IDs must fail closed"
        )
    if (
        work_leases.get("stale_generation_release_policy")
        != "deny"
    ):
        raise RuntimeSupervisionError(
            "stale work leases must fail closed"
        )
    if (
        work_leases.get("startup_recovery_exception")
        != "engine durable recovery only"
    ):
        raise RuntimeSupervisionError(
            "startup recovery exception drifted"
        )
    if work_leases.get("snapshot_fields") != [
        "inflight_work",
        "active_work_ids",
        "last_lease_sequence",
    ]:
        raise RuntimeSupervisionError(
            "work lease snapshot contract drifted"
        )

    generated = work_leases.get("generated_identity")
    if not isinstance(generated, dict):
        raise RuntimeSupervisionError(
            "generated work identity contract is missing"
        )
    if (
        generated.get("authority")
        != "RuntimeServiceLifecycle.acquire_generated_work"
    ):
        raise RuntimeSupervisionError(
            "generated work identity authority drifted"
        )
    if (
        generated.get("format")
        != "<prefix>:<generation>:<monotonic_lease_sequence>"
    ):
        raise RuntimeSupervisionError(
            "generated work identity format drifted"
        )
    if generated.get("object_identity_forbidden") is not True:
        raise RuntimeSupervisionError(
            "object identity must be forbidden for generated work IDs"
        )

    background = lifecycle.get("background_work")
    if not isinstance(background, dict):
        raise RuntimeSupervisionError(
            "background work semantics are missing"
        )
    for key in (
        "async_tasks_leased",
        "threads_leased",
        "thread_join_required_before_dependency_close",
    ):
        if background.get(key) is not True:
            raise RuntimeSupervisionError(
                f"background_work.{key} must be true"
            )
    if (
        background.get("unquiesced_shutdown_policy")
        != "fail-closed-and-remain-draining"
    ):
        raise RuntimeSupervisionError(
            "unquiesced shutdown policy drifted"
        )

    sources = contract.get("sources")
    if not isinstance(sources, dict):
        raise RuntimeSupervisionError(
            "sources must be an object"
        )
    shared = _repo_path(sources.get("shared_lifecycle"))
    mirror = _repo_path(
        sources.get("governed_lifecycle_mirror")
    )
    shared_path = root / shared
    mirror_path = root / mirror
    if not shared_path.is_file() or not mirror_path.is_file():
        raise RuntimeSupervisionError(
            "shared lifecycle canonical/mirror file is missing"
        )
    if shared_path.read_bytes() != mirror_path.read_bytes():
        raise RuntimeSupervisionError(
            "shared lifecycle governed mirror drifted"
        )

    source = shared_path.read_text(encoding="utf-8")
    required = (
        "class RuntimeAdmissionMiddleware:",
        "class RuntimeServiceLifecycle:",
        "class WorkLease:",
        "ServicePhase.DRAINING",
        "self._token.cancel(",
        "def require_work_admission(",
        "def acquire_work(",
        "def acquire_generated_work(",
        "def release_work(",
        'self.lifecycle.acquire_generated_work("http")',
        "self.lifecycle.release_work(lease)",
        "runtime_not_accepting_work",
        "retry-after",
        "in-flight work leases",
        "def restart(",
        "LifecycleReceipt(",
    )
    for symbol in required:
        if symbol not in source:
            raise RuntimeSupervisionError(
                "shared lifecycle implementation missing semantic "
                f"symbol {symbol!r}"
            )
    if "id(scope)" in source:
        raise RuntimeSupervisionError(
            "HTTP work identity must not depend on Python object identity"
        )
    return len(lifecycle["phases"]), len(required)


def _network_transport_surfaces(
    construction: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    surfaces = construction.get("provider_surfaces")
    if not isinstance(surfaces, list):
        raise RuntimeSupervisionError(
            "construction provider_surfaces must be a list"
        )
    selected: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(surfaces):
        if not isinstance(raw, dict):
            raise RuntimeSupervisionError(
                f"provider_surfaces[{index}] must be an object"
            )
        surface_id = raw.get("id")
        if (
            not isinstance(surface_id, str)
            or not surface_id
        ):
            raise RuntimeSupervisionError(
                f"provider_surfaces[{index}].id must be non-empty"
            )
        if raw.get("network_transport_owner") is True:
            if surface_id in selected:
                raise RuntimeSupervisionError(
                    "duplicate network transport surface "
                    + surface_id
                )
            selected[surface_id] = raw
    if not selected:
        raise RuntimeSupervisionError(
            "no network transport provider surfaces declared"
        )
    return selected


def _validate_transport_semantics(
    payload: dict[str, Any],
    *,
    label: str,
    allow_composite: bool,
) -> str:
    mode = payload.get("cancellation_mode")
    allowed = (
        _CONNECTOR_CANCELLATION_MODES
        if allow_composite
        else _OPERATION_CANCELLATION_MODES
    )
    if mode not in allowed:
        raise RuntimeSupervisionError(
            f"{label} has invalid cancellation mode"
        )
    for key in _TRANSPORT_FLAGS:
        if type(payload.get(key)) is not bool:
            raise RuntimeSupervisionError(
                f"{label}.{key} must be boolean"
            )
    if payload.get("bounded_timeout") is not True:
        raise RuntimeSupervisionError(
            f"{label} must have a bounded timeout"
        )
    if payload.get("late_result_fencing") is not True:
        raise RuntimeSupervisionError(
            f"{label} must fence late results"
        )

    if mode == "bounded_blocking_token_fence":
        if payload.get("retry_wait_cancellable") is not True:
            raise RuntimeSupervisionError(
                f"{label} blocking retry waits must be cancellable"
            )
    elif mode == "async_task_cancellation":
        if payload.get("deadline_propagation") is not True:
            raise RuntimeSupervisionError(
                f"{label} async work must propagate deadlines"
            )
    elif mode == "delegated_durable_cancel":
        if not (
            payload.get("deadline_propagation") is True
            and payload.get("retry_wait_cancellable") is True
        ):
            raise RuntimeSupervisionError(
                f"{label} delegated cancellation is not bounded"
            )
    elif mode == "cooperative_token":
        if payload.get("retry_wait_cancellable") is not True:
            raise RuntimeSupervisionError(
                f"{label} cooperative retries must be cancellable"
            )
    return str(mode)


def _expected_engine_runtime_operations(
    construction: dict[str, Any],
) -> set[str]:
    providers = construction.get("runtime_model_providers")
    if not isinstance(providers, list):
        raise RuntimeSupervisionError(
            "runtime_model_providers must be a list"
        )
    openai = next(
        (
            item
            for item in providers
            if isinstance(item, dict)
            and item.get("id") == "openai"
            and item.get("state") == "active"
        ),
        None,
    )
    if not isinstance(openai, dict):
        raise RuntimeSupervisionError(
            "active openai runtime provider declaration is missing"
        )
    if openai.get("execution_owner") != "skeleton/provider_runtime.py":
        raise RuntimeSupervisionError(
            "active openai execution owner drifted"
        )

    capabilities = openai.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise RuntimeSupervisionError(
            "active openai capabilities must be non-empty"
        )
    if len(capabilities) != len(set(capabilities)):
        raise RuntimeSupervisionError(
            "active openai capabilities contain duplicates"
        )
    unknown = sorted(
        set(capabilities) - set(_ENGINE_CAPABILITY_OPERATIONS)
    )
    if unknown:
        raise RuntimeSupervisionError(
            "VOL-004 lacks operation mapping for active provider "
            "capabilities: " + ", ".join(unknown)
        )
    expected = {
        _ENGINE_CAPABILITY_OPERATIONS[item]
        for item in capabilities
    }

    sync_adapter = openai.get("sync_adapter")
    if sync_adapter is not None:
        if (
            not isinstance(sync_adapter, str)
            or not sync_adapter.startswith(
                "skeleton/provider_runtime.py:"
            )
        ):
            raise RuntimeSupervisionError(
                "openai sync adapter declaration is invalid"
            )
        expected.add("sync-text-generation")
    return expected


def _validate_connector_operations(
    root: Path,
    *,
    connector: dict[str, Any],
    owner: str,
    connector_id: str,
) -> tuple[int, int]:
    operations = connector.get("operations")
    if not isinstance(operations, list) or not operations:
        raise RuntimeSupervisionError(
            f"connector {connector_id} operations must be non-empty"
        )

    mode = connector.get("cancellation_mode")
    if mode == "composite" and len(operations) < 2:
        raise RuntimeSupervisionError(
            f"composite connector {connector_id} needs multiple operations"
        )
    if mode != "composite" and len(operations) != 1:
        raise RuntimeSupervisionError(
            f"non-composite connector {connector_id} must have one operation"
        )

    operation_ids: set[str] = set()
    operation_modes: set[str] = set()
    symbol_count = 0
    for index, operation in enumerate(operations):
        label = (
            f"connector {connector_id} operation[{index}]"
        )
        if not isinstance(operation, dict):
            raise RuntimeSupervisionError(
                f"{label} must be an object"
            )
        operation_id = operation.get("id")
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or operation_id in operation_ids
        ):
            raise RuntimeSupervisionError(
                f"{label} has invalid/duplicate id"
            )
        operation_ids.add(operation_id)
        operation_mode = _validate_transport_semantics(
            operation,
            label=f"connector {connector_id} operation {operation_id}",
            allow_composite=False,
        )
        operation_modes.add(operation_mode)
        symbol_count += _require_symbols(
            root,
            {
                "path": owner,
                "required_symbols": operation.get(
                    "required_symbols"
                ),
            },
            f"connector {connector_id} operation {operation_id}",
        )

    if mode == "composite":
        if len(operation_modes) < 2:
            raise RuntimeSupervisionError(
                f"composite connector {connector_id} must use "
                "multiple cancellation modes"
            )
    elif operation_modes != {mode}:
        raise RuntimeSupervisionError(
            f"connector {connector_id} operation mode drifted "
            "from connector mode"
        )

    for key in _TRANSPORT_FLAGS:
        if connector.get(key) is True and any(
            operation.get(key) is not True
            for operation in operations
        ):
            raise RuntimeSupervisionError(
                f"connector {connector_id} overstates aggregate {key}"
            )

    return len(operations), symbol_count


def _validate_connectors(
    root: Path,
    contract: dict[str, Any],
    construction: dict[str, Any],
) -> tuple[int, int, int, int]:
    inventory = contract.get("connector_inventory")
    if not isinstance(inventory, dict):
        raise RuntimeSupervisionError(
            "connector_inventory must be an object"
        )
    if (
        inventory.get("construction_source")
        != "machine/ai_app_construction.json:provider_surfaces"
    ):
        raise RuntimeSupervisionError(
            "connector construction source drifted"
        )
    if (
        inventory.get("selection_rule")
        != "network_transport_owner == true"
    ):
        raise RuntimeSupervisionError(
            "connector inventory selection rule drifted"
        )
    if (
        inventory.get("coverage_rule")
        != "every selected provider surface must appear exactly once in connectors"
    ):
        raise RuntimeSupervisionError(
            "connector coverage rule drifted"
        )
    if (
        inventory.get("undeclared_connector_policy")
        != "fail-closed"
    ):
        raise RuntimeSupervisionError(
            "undeclared connector policy must fail closed"
        )

    network_surfaces = _network_transport_surfaces(
        construction
    )
    extras = inventory.get("extra_internal_connectors")
    if extras != ["backend-engine"]:
        raise RuntimeSupervisionError(
            "extra internal connector inventory must contain "
            "backend-engine exactly"
        )

    connectors = contract.get("connectors")
    if not isinstance(connectors, list) or not connectors:
        raise RuntimeSupervisionError(
            "connectors must be a non-empty list"
        )

    by_id: dict[str, dict[str, Any]] = {}
    surface_refs: list[str] = []
    symbol_count = 0
    operation_count = 0

    for index, connector in enumerate(connectors):
        label = f"connectors[{index}]"
        if not isinstance(connector, dict):
            raise RuntimeSupervisionError(
                f"{label} must be an object"
            )
        connector_id = connector.get("id")
        if (
            not isinstance(connector_id, str)
            or not connector_id
            or connector_id in by_id
        ):
            raise RuntimeSupervisionError(
                f"invalid/duplicate connector id {connector_id!r}"
            )
        by_id[connector_id] = connector

        owner = _repo_path(connector.get("owner"))
        if not (root / owner).is_file():
            raise RuntimeSupervisionError(
                f"connector {connector_id} owner is missing: {owner}"
            )

        _validate_transport_semantics(
            connector,
            label=f"connector {connector_id}",
            allow_composite=True,
        )
        symbol_count += _require_symbols(
            root,
            {
                "path": owner,
                "required_symbols": connector.get(
                    "required_symbols"
                ),
            },
            f"connector {connector_id}",
        )
        op_count, op_symbols = _validate_connector_operations(
            root,
            connector=connector,
            owner=owner,
            connector_id=connector_id,
        )
        operation_count += op_count
        symbol_count += op_symbols

        surface_id = connector.get("surface_id")
        if surface_id is not None:
            if (
                not isinstance(surface_id, str)
                or not surface_id
            ):
                raise RuntimeSupervisionError(
                    f"connector {connector_id}.surface_id is invalid"
                )
            surface_refs.append(surface_id)
            surface = network_surfaces.get(surface_id)
            if surface is None:
                raise RuntimeSupervisionError(
                    f"connector {connector_id} references "
                    f"non-network surface {surface_id}"
                )
            if connector_id != surface_id:
                raise RuntimeSupervisionError(
                    "connector id must equal provider surface id: "
                    + connector_id
                )
            if connector.get("owner") != surface.get("owner"):
                raise RuntimeSupervisionError(
                    f"connector {connector_id} owner drifted "
                    "from provider surface"
                )
            if connector.get("family") != surface.get("family"):
                raise RuntimeSupervisionError(
                    f"connector {connector_id} family drifted "
                    "from provider surface"
                )

    if set(surface_refs) != set(network_surfaces):
        missing = sorted(
            set(network_surfaces) - set(surface_refs)
        )
        extra = sorted(
            set(surface_refs) - set(network_surfaces)
        )
        raise RuntimeSupervisionError(
            "network connector coverage mismatch "
            f"(missing={missing}, extra={extra})"
        )
    if len(surface_refs) != len(set(surface_refs)):
        raise RuntimeSupervisionError(
            "network provider surfaces must be covered exactly once"
        )
    if set(by_id) != set(network_surfaces) | {"backend-engine"}:
        raise RuntimeSupervisionError(
            "connector inventory contains undeclared or missing connectors"
        )

    engine = by_id.get("engine-runtime")
    if not isinstance(engine, dict):
        raise RuntimeSupervisionError(
            "engine-runtime connector is missing"
        )
    engine_operations = engine.get("operations")
    assert isinstance(engine_operations, list)
    actual_engine_ops = {
        item.get("id")
        for item in engine_operations
        if isinstance(item, dict)
    }
    expected_engine_ops = _expected_engine_runtime_operations(
        construction
    )
    if actual_engine_ops != expected_engine_ops:
        raise RuntimeSupervisionError(
            "engine-runtime operation coverage drift "
            f"(expected={sorted(expected_engine_ops)}, "
            f"actual={sorted(str(item) for item in actual_engine_ops)})"
        )

    return (
        len(connectors),
        len(network_surfaces),
        operation_count,
        symbol_count,
    )


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    contract = _load(root, CONTRACT)
    master = _load(root, MASTER)

    if contract.get("schema_version") != EXPECTED_SCHEMA:
        raise RuntimeSupervisionError(
            "runtime supervision schema must equal "
            + EXPECTED_SCHEMA
        )
    if (
        contract.get("contract_version")
        != EXPECTED_CONTRACT_VERSION
    ):
        raise RuntimeSupervisionError(
            "runtime supervision contract version must equal "
            + EXPECTED_CONTRACT_VERSION
        )
    if contract.get("status") != "active":
        raise RuntimeSupervisionError(
            "runtime supervision contract must be active"
        )

    _validate_masterplan_binding(contract, master)

    sources = contract.get("sources")
    if not isinstance(sources, dict):
        raise RuntimeSupervisionError(
            "sources must be an object"
        )
    manifest_path = _repo_path(
        sources.get("runtime_manifest")
    )
    manifest = _load(root, Path(manifest_path))
    construction_path = _repo_path(
        sources.get("construction_contract")
    )
    construction = _load(root, Path(construction_path))

    manifest_services = {
        item.get("name"): item
        for item in manifest.get("services", [])
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
    }

    (
        phase_count,
        lifecycle_symbol_count,
    ) = _validate_lifecycle_semantics(root, contract)

    services = contract.get("services")
    if not isinstance(services, list) or not services:
        raise RuntimeSupervisionError(
            "services must be non-empty"
        )
    service_ids: set[str] = set()
    symbol_count = lifecycle_symbol_count

    for service in services:
        if not isinstance(service, dict):
            raise RuntimeSupervisionError(
                "service supervision entry must be an object"
            )
        service_id = service.get("service")
        if (
            not isinstance(service_id, str)
            or not service_id
            or service_id in service_ids
        ):
            raise RuntimeSupervisionError(
                f"invalid/duplicate supervised service {service_id!r}"
            )
        service_ids.add(service_id)

        live = manifest_services.get(service_id)
        if not isinstance(live, dict):
            raise RuntimeSupervisionError(
                "runtime manifest lacks supervised service "
                + service_id
            )
        if service.get("role") != live.get("role"):
            raise RuntimeSupervisionError(
                f"{service_id} role drift"
            )
        if sorted(
            service.get("expected_dependencies", [])
        ) != sorted(live.get("depends_on", [])):
            raise RuntimeSupervisionError(
                f"{service_id} dependency drift"
            )
        if (
            service.get("expected_health_path")
            != live.get("health_path")
        ):
            raise RuntimeSupervisionError(
                f"{service_id} health-path drift"
            )
        if (
            service.get("expected_entrypoint")
            != live.get("entrypoint")
        ):
            raise RuntimeSupervisionError(
                f"{service_id} entrypoint drift"
            )

        groups = (
            "lifecycle_bindings",
            "connector_bindings",
            "cancellation_bindings",
        )
        if not any(
            isinstance(service.get(group), list)
            and service.get(group)
            for group in groups
        ):
            raise RuntimeSupervisionError(
                f"{service_id} has no concrete supervision bindings"
            )
        for group in groups:
            raw = service.get(group, [])
            if not isinstance(raw, list):
                raise RuntimeSupervisionError(
                    f"{service_id}.{group} must be a list"
                )
            for index, item in enumerate(raw):
                if not isinstance(item, dict):
                    raise RuntimeSupervisionError(
                        f"{service_id}.{group}[{index}] "
                        "must be an object"
                    )
                symbol_count += _require_symbols(
                    root,
                    item,
                    f"{service_id}.{group}[{index}]",
                )

    if service_ids != {"backend", "skeleton"}:
        raise RuntimeSupervisionError(
            "supervision contract must cover backend "
            "and skeleton exactly"
        )
    backend = next(
        item for item in services
        if item["service"] == "backend"
    )
    engine = next(
        item for item in services
        if item["service"] == "skeleton"
    )
    if "skeleton" not in backend["expected_dependencies"]:
        raise RuntimeSupervisionError(
            "backend must depend on skeleton"
        )
    if (
        "mongo" not in backend["expected_dependencies"]
        or "mongo" not in engine["expected_dependencies"]
    ):
        raise RuntimeSupervisionError(
            "backend and skeleton must retain mongo dependency"
        )

    (
        connector_count,
        network_surface_count,
        operation_count,
        connector_symbols,
    ) = _validate_connectors(
        root,
        contract,
        construction,
    )
    symbol_count += connector_symbols

    invariants = contract.get("invariants")
    if (
        not isinstance(invariants, list)
        or len(invariants) < 16
    ):
        raise RuntimeSupervisionError(
            "runtime supervision invariants are incomplete"
        )
    if len(invariants) != len(set(invariants)):
        raise RuntimeSupervisionError(
            "runtime supervision invariants contain duplicates"
        )

    return {
        "status": "valid",
        "schema_version": EXPECTED_SCHEMA,
        "contract_version": EXPECTED_CONTRACT_VERSION,
        "service_count": len(services),
        "lifecycle_phase_count": phase_count,
        "connector_count": connector_count,
        "connector_operation_count": operation_count,
        "network_surface_count": network_surface_count,
        "required_symbol_count": symbol_count,
        "masterplan_binding": "VOL-004",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except RuntimeSupervisionError as exc:
        print(
            f"runtime supervision: FAIL: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "runtime supervision: OK "
            f"({result['service_count']} services, "
            f"{result['connector_count']} connectors, "
            f"{result['connector_operation_count']} operations, "
            f"{result['network_surface_count']} network surfaces, "
            f"{result['required_symbol_count']} symbols)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
