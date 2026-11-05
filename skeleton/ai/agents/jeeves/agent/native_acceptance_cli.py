"""Real installed GGUF Jeeves first turn and independent cold-reopen witness.

The installer, isolated child and SQLite execution spine remain independent
authorities. Source-only mocks cannot certify an installed model, its rights,
a device or consumer release. Never retry an uncertain native generation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Callable

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance import (
    run as run_first_turn,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.replay_probe import (
    inspect_replay,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.restart_probe import (
    inspect_restart,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.installed_witness import (
    require_activated_source,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.source_contract import (
    valid_source_snapshot,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.preflight import (
    validate_native_shape,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.publication import (
    emit_native_jsonl,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    identifier, utf8, identity_hash,
)
from .native_source_fence import NativeSourceFence


class NativeAcceptanceHold(ValueError):
    """A native acceptance fact is missing, stale or untrustworthy."""


class _RedactedAcceptanceParser(argparse.ArgumentParser):
    """Do not echo private paths or arguments on invalid CLI options."""

    def error(self, message: str) -> None:
        raise NativeAcceptanceHold("invalid native acceptance arguments")


def _private_root(value: object, label: str) -> None:
    if (not isinstance(value, Path) or not value.is_absolute()
            or ".." in value.parts or chr(0) in str(value)):
        raise NativeAcceptanceHold("absolute private " + label + " required")


def _installed_epoch(
    worker: object, installed: object, *, tenant: str, subject: str,
) -> tuple[ActiveModel, NativeSourceFence, dict[str, object]]:
    """Inspect one live, exact-principal GGUF worker and source inventory."""
    principal = ActiveModel.from_supervisor(worker)
    if (principal.tenant, principal.subject) != (tenant, subject):
        raise NativeAcceptanceHold("native worker belongs to another principal")
    # Receipt booleans are never upgraded from integers, truthy mocks or
    # a synthetic report. require_activated_source verifies the actual
    # isolated child, held capacity lease and installed model type.
    if (getattr(installed, "content_verified", None) is not True
            or getattr(installed, "rights_approved", None) is not True
            or getattr(installed, "model_sha256", None)
            != principal.model_sha256):
        raise NativeAcceptanceHold("installed source was not approved")
    fence = NativeSourceFence(
        worker, installed, expected_tenant=tenant,
        expected_subject=subject,
    )
    witness = require_activated_source(worker, installed)
    if not valid_source_snapshot(witness, principal):
        raise NativeAcceptanceHold("complete installed GGUF source required")
    fence.assert_live(worker)
    if ActiveModel.from_supervisor(worker) != principal:
        raise NativeAcceptanceHold("native source owner changed")
    return principal, fence, witness.copy()


def _proof(
    *, prompt: str, first: dict[str, object],
    principal: ActiveModel, restart_db: bool, cold_model: bool,
) -> dict[str, object]:
    return {
        "schema": "jeeves.real_native_acceptance.v1",
        "status": "native-first-turn-committed-and-replayed",
        "session_id": first["session_id"],
        "request_id": first["request_id"],
        "prompt_sha256": sha256(prompt.encode("utf-8", "strict")).hexdigest(),
        "model_sha256": principal.model_sha256,
        "tokenizer_sha256": principal.tokenizer_sha256,
        "output_sha256": first["output_sha256"],
        "real_native_inference_completed": True,
        "sqlite_committed_replay_verified": True,
        "restart_db_inspected": restart_db,
        "cold_model_reload_verified": cold_model,
        "second_generation_not_performed": True,
        "model_rights_independently_approved_here": False,
        "device_pressure_qualified": False,
        "inflight_native_cancellation_qualified": False,
        "clean_windows_install_qualified": False,
        "release_certified": False,
    }


def run_acceptance(
    *,
    model_root: Path,
    state_dir: Path,
    tenant: str,
    subject: str,
    prompt: str,
    approved: bool,
    cold_restart: bool,
    n_ctx: int = 2048,
    max_new_tokens: int = 256,
    n_threads: int = 4,
    gpu_layers: int = 0,
    capacity_root: Path | None = None,
    capacity_budget_bytes: int = 8000000000,
    publisher: Callable[[object, NativeSourceFence, dict[str, object]], None]
    | None = None,
) -> dict[str, object]:
    """Exactly one installed native generation, with optional cold replay.

    Any operator-visible publication callback runs *inside* the currently
    live source-fenced worker context, never after stack.close(). Normal
    function callers receive source-only return data; it is not a device
    or release certificate.
    """
    if approved is not True or type(cold_restart) is not bool:
        raise NativeAcceptanceHold("explicit real native approval required")
    if publisher is not None and not callable(publisher):
        raise NativeAcceptanceHold("invalid native output publisher")
    _private_root(model_root, "model root")
    _private_root(state_dir, "SQLite state root")
    if capacity_root is not None:
        _private_root(capacity_root, "capacity root")
    tenant = identifier(tenant, "tenant")
    subject = identifier(subject, "subject")
    prompt = utf8(prompt, maximum=32768)
    validate_native_shape(
        n_ctx=n_ctx, max_new_tokens=max_new_tokens, n_threads=n_threads,
        gpu_layers=gpu_layers, capacity_budget_bytes=capacity_budget_bytes,
    )
    options = {
        "model_root": model_root, "state_dir": state_dir,
        "tenant": tenant, "subject": subject, "n_ctx": n_ctx,
        "max_new_tokens": max_new_tokens, "n_threads": n_threads,
        "gpu_layers": gpu_layers, "capacity_root": capacity_root,
        "capacity_budget_bytes": capacity_budget_bytes, "isolated": True,
    }
    stack, worker, installed = activate_checked(**options)
    with stack:
        principal, fence, source = _installed_epoch(
            worker, installed, tenant=tenant, subject=subject,
        )
        fence.assert_live(worker)
        # Without the actual installed receipt and require_real=True, the
        # lower-level verifier truthfully reports synthetic/unverified evidence
        # and the real acceptance contract can never be satisfied.
        first = run_first_turn(
            worker, prompt=prompt, approved=True,
            installed_receipt=installed, require_real=True,
        )
        if (type(first) is not dict
                or first.get("native_model_observed") is not True
                or first.get("installed_source_bound") is not True
                or first.get("operator_approved_real_inference") is not True
                or first.get("replayed_without_generation") is not True
                or first.get("release_certified") is not False
                or first.get("installed_source") != source
                or first.get("model_sha256") != principal.model_sha256
                or first.get("tokenizer_sha256") != principal.tokenizer_sha256):
            raise NativeAcceptanceHold("source-bound SQLite first turn not verified")
        digest = identity_hash(first.get("output_sha256"))
        identifier(first.get("session_id"), "native session")
        identifier(first.get("request_id"), "native request")
        if (type(first.get("generated_tokens")) is not int
                or first["generated_tokens"] < 1):
            raise NativeAcceptanceHold("fresh native tokens were not witnessed")
        health = worker.spine.health()
        if type(health) is not dict:
            raise NativeAcceptanceHold("canonical SQLite spine health unavailable")
        fence.assert_live(worker)
        if ActiveModel.from_supervisor(worker) != principal:
            raise NativeAcceptanceHold("native principal changed after committed turn")
        if not cold_restart:
            proof = _proof(
                prompt=prompt, first=first, principal=principal,
                restart_db=False, cold_model=False,
            )
            if publisher is not None:
                publisher(worker, fence, proof)
            return proof

    # The first child and SQLite handles are closed before inspecting the
    # durable record on disk and activating a genuinely distinct model child.
    checked = inspect_restart(
        state_dir=state_dir, tenant=tenant, subject=subject,
        model_sha256=principal.model_sha256,
        tokenizer_sha256=principal.tokenizer_sha256,
    )
    if (type(checked) is not dict
            or checked.get("state") != "restart-storage-inspected-not-native-resumed"):
        raise NativeAcceptanceHold("read-only restart state not verified")
    reopened_stack, reopened_worker, reopened_installed = activate_checked(**options)
    if reopened_stack is stack or reopened_worker is worker:
        # If a faulty activation returns an already closed worker, never
        # reopen the prior inference epoch or classify it as a cold restart.
        if reopened_stack is not stack:
            reopened_stack.close()
        raise NativeAcceptanceHold("cold restart reused the earlier native worker")
    with reopened_stack:
        second_principal, second_fence, second_source = _installed_epoch(
            reopened_worker, reopened_installed,
            tenant=tenant, subject=subject,
        )
        if second_principal != principal or second_source != source:
            raise NativeAcceptanceHold("installed native epoch changed across cold restart")
        second_fence.assert_live(reopened_worker)
        replay = inspect_replay(
            reopened_worker, first["session_id"], first["request_id"],
            prompt, seed=17, temperature=0.8,
        )
        if (type(replay) is not dict
                or replay.get("committed") is not True
                or replay.get("no_second_generation") is not True
                or replay.get("output_sha256") != digest):
            raise NativeAcceptanceHold("cold SQLite replay disagrees with committed turn")
        second_fence.assert_live(reopened_worker)
        if ActiveModel.from_supervisor(reopened_worker) != principal:
            raise NativeAcceptanceHold("native principal changed during cold replay")
        proof = _proof(
            prompt=prompt, first=first, principal=principal,
            restart_db=True, cold_model=True,
        )
        if publisher is not None:
            publisher(reopened_worker, second_fence, proof)
        return proof


def main(argv: list[str] | None = None) -> int:
    parser = _RedactedAcceptanceParser(
        description="Approved installed GGUF and cold SQLite replay acceptance"
    )
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--approve-native", action="store_true")
    parser.add_argument("--cold-restart", action="store_true")
    parser.add_argument("--prompt-stdin", action="store_true")
    parser.add_argument("--context", type=int, default=2048)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--capacity-root", type=Path)
    parser.add_argument("--capacity-budget-bytes", type=int, default=8000000000)
    try:
        args = parser.parse_args(argv)
        if not args.approve_native or not args.prompt_stdin:
            raise NativeAcceptanceHold("explicit approval and stdin required")
        _private_root(args.model_root, "model root")
        _private_root(args.state_dir, "SQLite state root")
        if args.capacity_root is not None:
            _private_root(args.capacity_root, "capacity root")
        identifier(args.tenant, "tenant")
        identifier(args.subject, "subject")
        validate_native_shape(
            n_ctx=args.context, max_new_tokens=args.max_new_tokens,
            n_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_budget_bytes=args.capacity_budget_bytes,
        )
        # Pure admission must finish BEFORE private prompt bytes, installed
        # GGUF inspection, native process launch or SQLite side effects.
        raw = sys.stdin.buffer.read(32769)
        if type(raw) is not bytes or not 1 <= len(raw) <= 32768:
            raise NativeAcceptanceHold("bounded binary prompt stdin required")
        prompt = raw.decode("utf-8", "strict")
        proof = run_acceptance(
            model_root=args.model_root, state_dir=args.state_dir,
            tenant=args.tenant, subject=args.subject, prompt=prompt,
            approved=True, cold_restart=args.cold_restart,
            n_ctx=args.context, max_new_tokens=args.max_new_tokens,
            n_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
            publisher=lambda worker, fence, result: emit_native_jsonl(
                worker, fence, result, sys.stdout, maximum_result_bytes=65536,
            ),
        )
        # The approved native stack was alive when the result was written.
        # Do not repeat publication after the last source fence closes.
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        sys.stderr.write(json.dumps({
            "schema": "jeeves.real_native_acceptance.v1",
            "status": "held",
            "error_class": type(exc).__name__,
            "real_native_inference_qualified": False,
            "release_certified": False,
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
