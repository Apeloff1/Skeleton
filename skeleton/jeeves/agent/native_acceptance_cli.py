"""Operator-approved GGUF first-turn and cold-reopen acceptance.

This CLI delegates real-source verification to the canonical installed
GGUF witness, isolated supervisor and SQLite acceptance contracts. No
synthetic model, cached answer, model-provided self-report or fallback
can satisfy the production real-native acceptance condition.

Output is digests and explicit nonqualification flags only: no private
prompt/answer text, source pathname, tokens, rights grant or device claim.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance import (
    run as run_first_turn,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.cold_reopen_acceptance import (
    run as run_cold_reopen,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.installed_witness import (
    require_activated_source,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.source_contract import (
    valid_source_snapshot,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.preflight import (
    validate_native_shape,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.restart_probe import (
    inspect_restart,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    identifier, identity_hash, utf8,
)


class NativeAcceptanceHold(ValueError):
    """A real installed GGUF acceptance receipt cannot be published."""


class _RedactedAcceptanceParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise NativeAcceptanceHold("invalid native acceptance arguments")


def _absolute_private_root(value: object, label: str) -> None:
    if (not isinstance(value, Path) or not value.is_absolute()
            or ".." in value.parts or "\x00" in str(value)):
        raise NativeAcceptanceHold("absolute private " + label + " required")


def _positive_source_flags(first: object, active: ActiveModel) -> tuple[str, str, str]:
    """Require the existing real-only first-turn and installed witness contract."""
    if type(first) is not dict:
        raise NativeAcceptanceHold("canonical native first-turn evidence missing")
    for field in (
        "native_model_observed", "installed_source_bound",
        "replayed_without_generation", "operator_approved_real_inference",
    ):
        if first.get(field) is not True:
            raise NativeAcceptanceHold("real source and SQLite turn proof incomplete")
    if first.get("release_certified") is not False:
        raise NativeAcceptanceHold("source-only evidence cannot certify release")
    if (first.get("model_sha256") != active.model_sha256
            or first.get("tokenizer_sha256") != active.tokenizer_sha256):
        raise NativeAcceptanceHold("native model epoch differs from installed source")
    if not valid_source_snapshot(first.get("installed_source"), active):
        raise NativeAcceptanceHold("complete installed source custody required")
    if (type(first.get("generated_tokens")) is not int
            or not 1 <= first["generated_tokens"] <= 8192):
        raise NativeAcceptanceHold("real generation token witness missing")
    return (
        identifier(first.get("session_id"), "session"),
        identifier(first.get("request_id"), "request"),
        identity_hash(first.get("output_sha256")),
    )


def _positive_cold_flags(proof: object) -> tuple[str, str, str, str, str]:
    """Check canonical cold-reopen proof without inferring a second model call."""
    if type(proof) is not dict:
        raise NativeAcceptanceHold("canonical cold source proof missing")
    if (proof.get("source_verified_twice") is not True
            or proof.get("sqlite_replay_after_cold_reopen") is not True
            or proof.get("second_generation_attempted") is not False
            or proof.get("release_certified") is not False):
        raise NativeAcceptanceHold("independent cold GGUF and SQLite replay not proved")
    if (type(proof.get("first_turn_generated_tokens")) is not int
            or not 1 <= proof["first_turn_generated_tokens"] <= 8192):
        raise NativeAcceptanceHold("fresh native first turn not witnessed")
    return (
        identifier(proof.get("session_id"), "session"),
        identifier(proof.get("request_id"), "request"),
        identity_hash(proof.get("model_sha256")),
        identity_hash(proof.get("tokenizer_sha256")),
        identity_hash(proof.get("output_sha256")),
    )


def _public_proof(
    *, prompt: str, model: str, tokenizer: str, digest: str,
    session: str, request: str, cold: bool,
) -> dict[str, object]:
    return {
        "schema": "jeeves.real_native_acceptance.v1",
        "status": "native-first-turn-committed-and-replayed",
        "session_id": session,
        "request_id": request,
        "prompt_sha256": sha256(prompt.encode("utf-8", "strict")).hexdigest(),
        "model_sha256": model,
        "tokenizer_sha256": tokenizer,
        "output_sha256": digest,
        "real_native_inference_completed": True,
        "sqlite_committed_replay_verified": True,
        "restart_db_inspected": cold,
        "cold_model_reload_verified": cold,
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
) -> dict[str, object]:
    """One independently source-checked real turn, optionally a cold replay."""
    if approved is not True or type(cold_restart) is not bool:
        raise NativeAcceptanceHold("explicit real-model inference permission required")
    tenant = identifier(tenant, "tenant")
    subject = identifier(subject, "subject")
    _absolute_private_root(model_root, "installed model root")
    _absolute_private_root(state_dir, "SQLite state root")
    if capacity_root is not None:
        _absolute_private_root(capacity_root, "capacity root")
    prompt = utf8(prompt, maximum=32768)
    validate_native_shape(
        n_ctx=n_ctx, max_new_tokens=max_new_tokens,
        n_threads=n_threads, gpu_layers=gpu_layers,
        capacity_budget_bytes=capacity_budget_bytes,
        inference_ms=90000,
    )
    args = {
        "model_root": model_root, "state_dir": state_dir,
        "tenant": tenant, "subject": subject,
        "n_ctx": n_ctx, "max_new_tokens": max_new_tokens,
        "n_threads": n_threads, "gpu_layers": gpu_layers,
        "capacity_root": capacity_root,
        "capacity_budget_bytes": capacity_budget_bytes,
    }
    if cold_restart:
        # Canonical cold acceptance separately installs, verifies and closes
        # both isolated workers, replaying only the *existing* SQLite receipt.
        cold = run_cold_reopen(**args, prompt=prompt, approved=True)
        session, request, model, tokenizer, digest = _positive_cold_flags(cold)
        doctor = inspect_restart(
            state_dir=state_dir, tenant=tenant, subject=subject,
            model_sha256=model, tokenizer_sha256=tokenizer,
        )
        if (type(doctor) is not dict
                or doctor.get("state")
                    != "restart-storage-inspected-not-native-resumed"):
            raise NativeAcceptanceHold("read-only cold SQLite state doctor failed")
        return _public_proof(
            prompt=prompt, model=model, tokenizer=tokenizer,
            digest=digest, session=session, request=request, cold=True,
        )

    stack, worker, installed = activate_checked(**args, isolated=True)
    with stack:
        current = ActiveModel.from_supervisor(worker)
        if (current.tenant, current.subject) != (tenant, subject):
            raise NativeAcceptanceHold("installed native worker belongs to another owner")
        # Existing first_turn only marks native_model_observed=True when the
        # real InstalledModelReport, isolated child and capacity lease are
        # independently inspected before and AFTER the native model effect.
        first = run_first_turn(
            worker, prompt=prompt, approved=True,
            installed_receipt=installed, require_real=True,
        )
        session, request, digest = _positive_source_flags(first, current)
        if type(worker.spine.health()) is not dict:
            raise NativeAcceptanceHold("canonical SQLite native health unavailable")
        observed = require_activated_source(worker, installed)
        if (not valid_source_snapshot(observed, current)
                or observed != first["installed_source"]
                or ActiveModel.from_supervisor(worker) != current):
            raise NativeAcceptanceHold("installed source drift after real first-turn proof")
    return _public_proof(
        prompt=prompt, model=current.model_sha256,
        tokenizer=current.tokenizer_sha256, digest=digest,
        session=session, request=request, cold=False,
    )


_PUBLIC_FIELDS = frozenset((
    "schema", "status", "session_id", "request_id", "prompt_sha256",
    "model_sha256", "tokenizer_sha256", "output_sha256",
    "real_native_inference_completed", "sqlite_committed_replay_verified",
    "restart_db_inspected", "cold_model_reload_verified",
    "second_generation_not_performed", "model_rights_independently_approved_here",
    "device_pressure_qualified", "inflight_native_cancellation_qualified",
    "clean_windows_install_qualified", "release_certified",
))


def _publish_summary(summary: object) -> None:
    """Write a bounded, digest-only historical proof, never native model text."""
    if type(summary) is not dict or set(summary) != _PUBLIC_FIELDS:
        raise NativeAcceptanceHold("invalid native acceptance public receipt")
    if (summary["schema"] != "jeeves.real_native_acceptance.v1"
            or summary["status"] != "native-first-turn-committed-and-replayed"
            or summary["real_native_inference_completed"] is not True
            or summary["sqlite_committed_replay_verified"] is not True
            or summary["second_generation_not_performed"] is not True):
        raise NativeAcceptanceHold("native source acceptance not certified")
    if any(summary[flag] is not False for flag in (
        "model_rights_independently_approved_here", "device_pressure_qualified",
        "inflight_native_cancellation_qualified",
        "clean_windows_install_qualified", "release_certified",
    )):
        raise NativeAcceptanceHold("device/release/rights flags must stay false")
    for field in (
        "prompt_sha256", "model_sha256", "tokenizer_sha256", "output_sha256",
    ):
        identity_hash(summary[field])
    for field in ("session_id", "request_id"):
        identifier(summary[field], field)
    try:
        result = json.dumps(
            summary, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ) + "\n"
        size = len(result.encode("utf-8", "strict"))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise NativeAcceptanceHold("native acceptance receipt not JSON") from exc
    if size > 8192:
        raise NativeAcceptanceHold("native acceptance disclosure exceeds bound")
    written = sys.stdout.write(result)
    if type(written) is not int or written != len(result):
        raise NativeAcceptanceHold("incomplete native acceptance disclosure")
    flush = getattr(sys.stdout, "flush", None)
    if callable(flush):
        flush()


def main(argv: list[str] | None = None) -> int:
    parser = _RedactedAcceptanceParser(
        description="Explicit source-approved native GGUF acceptance"
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
            raise NativeAcceptanceHold("explicit approval and stdin prompt required")
        identifier(args.tenant, "tenant")
        identifier(args.subject, "subject")
        _absolute_private_root(args.model_root, "installed model root")
        _absolute_private_root(args.state_dir, "SQLite state root")
        if args.capacity_root is not None:
            _absolute_private_root(args.capacity_root, "capacity root")
        validate_native_shape(
            n_ctx=args.context, max_new_tokens=args.max_new_tokens,
            n_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_budget_bytes=args.capacity_budget_bytes,
            inference_ms=90000,
        )
        # Preserve the operator's exact UTF-8 prompt; no .strip() of
        # meaningful whitespace, Python indentation, CRLF, or final EOF.
        raw = sys.stdin.buffer.read(32769)
        if not 1 <= len(raw) <= 32768:
            raise NativeAcceptanceHold("bounded prompt stdin required")
        prompt = utf8(raw.decode("utf-8", "strict"), maximum=32768)
        proof = run_acceptance(
            model_root=args.model_root, state_dir=args.state_dir,
            tenant=args.tenant, subject=args.subject, prompt=prompt,
            approved=True, cold_restart=args.cold_restart,
            n_ctx=args.context, max_new_tokens=args.max_new_tokens,
            n_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
        )
        _publish_summary(proof)
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


__all__ = ["NativeAcceptanceHold", "run_acceptance", "main"]
