"""Operator-approved real GGUF Jeeves acceptance with independent cold replay.

Unlike source-only Python fixtures, this CLI only runs through the existing
verified installer, actual native model activation, canonical supervised
generation, authoritative SQLite commit, and read-only replay. Its output
contains digests, never private prompt or response text.

An optional second source-bound model activation proves a cold *model reload*
and committed transcript replay without a second generation. It does not
prove native in-flight interruption, physical Windows qualification, model
accuracy, independent rights review, or release certification.
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
from skeleton.ai.runtime.operational_ai.laptop_runtime.replay_probe import (
    inspect_replay,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.restart_probe import (
    inspect_restart,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    identifier, utf8,
)


class NativeAcceptanceHold(ValueError):
    """Operator approval, native receipt or cold-restart proof is incomplete."""


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
    if approved is not True or type(cold_restart) is not bool:
        raise NativeAcceptanceHold("explicit real-model inference permission required")
    identifier(tenant, "tenant")
    identifier(subject, "subject")
    utf8(prompt, maximum=32768)
    args = {
        "model_root": model_root,
        "state_dir": state_dir,
        "tenant": tenant,
        "subject": subject,
        "n_ctx": n_ctx,
        "max_new_tokens": max_new_tokens,
        "n_threads": n_threads,
        "gpu_layers": gpu_layers,
        "capacity_root": capacity_root,
        "capacity_budget_bytes": capacity_budget_bytes,
        "isolated": True,
    }
    stack, worker, installed = activate_checked(**args)
    with stack:
        model_sha256 = worker.spine.identity.model_sha256
        tokenizer_sha256 = worker.spine.identity.tokenizer_sha256
        if (not installed.content_verified
            or not installed.rights_approved
            or installed.model_sha256 != model_sha256):
            raise NativeAcceptanceHold("installed model source identity not verified")
        # This pre-existing acceptance routine owns the one real model turn.
        first = run_first_turn(worker, prompt=prompt, approved=True)
        if first.get("native_model_observed") is not True:
            raise NativeAcceptanceHold("real model turn was not independently witnessed")
        first_digest = first.get("output_sha256")
        if type(first_digest) is not str or len(first_digest) != 64:
            raise NativeAcceptanceHold("real native output commitment digest missing")
        first_session = first["session_id"]
        first_request_id = first["request_id"]
        snapshot = worker.spine.health()
        if type(snapshot) is not dict:
            raise NativeAcceptanceHold("canonical SQLite spine health unavailable")

    restart_db_inspected = False
    cold_model_reload_verified = False
    if cold_restart:
        # Read-only verification on closed/native process: no new generation.
        checked = inspect_restart(
            state_dir=state_dir,
            tenant=tenant,
            subject=subject,
            model_sha256=model_sha256,
            tokenizer_sha256=tokenizer_sha256,
        )
        if checked.get("state") != "restart-storage-inspected-not-native-resumed":
            raise NativeAcceptanceHold("read-only restart state doctor failed")
        restart_db_inspected = True
        second_stack, second_worker, second_installed = activate_checked(**args)
        with second_stack:
            if (second_installed.model_sha256 != model_sha256
                or second_worker.spine.identity.tokenizer_sha256 != tokenizer_sha256):
                raise NativeAcceptanceHold("cold native model epoch mismatch")
            replay = inspect_replay(
                second_worker, first_session, first_request_id, prompt,
                seed=17, temperature=0.8,
            )
            if (replay.get("committed") is not True
                or replay.get("no_second_generation") is not True
                or replay.get("output_sha256") != first_digest):
                raise NativeAcceptanceHold("cold model reload lost committed native turn")
            cold_model_reload_verified = True

    return {
        "schema": "jeeves.real_native_acceptance.v1",
        "status": "native-first-turn-committed-and-replayed",
        "session_id": first_session,
        "request_id": first_request_id,
        "prompt_sha256": sha256(prompt.encode("utf-8", "strict")).hexdigest(),
        "model_sha256": model_sha256,
        "tokenizer_sha256": tokenizer_sha256,
        "output_sha256": first_digest,
        "real_native_inference_completed": True,
        "sqlite_committed_replay_verified": True,
        "restart_db_inspected": restart_db_inspected,
        "cold_model_reload_verified": cold_model_reload_verified,
        "second_generation_not_performed": True,
        "model_rights_independently_approved_here": False,
        "device_pressure_qualified": False,
        "inflight_native_cancellation_qualified": False,
        "clean_windows_install_qualified": False,
        "release_certified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Approved real GGUF Jeeves turn acceptance")
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
    args = parser.parse_args(argv)
    try:
        if not args.approve_native or not args.prompt_stdin:
            raise NativeAcceptanceHold("explicit approval and stdin prompt required")
        raw = sys.stdin.buffer.read(32769)
        if not 1 <= len(raw) <= 32768:
            raise NativeAcceptanceHold("bounded prompt stdin required")
        prompt = raw.decode("utf-8", "strict").strip()
        proof = run_acceptance(
            model_root=args.model_root,
            state_dir=args.state_dir,
            tenant=args.tenant,
            subject=args.subject,
            prompt=prompt,
            approved=True,
            cold_restart=args.cold_restart,
            n_ctx=args.context,
            max_new_tokens=args.max_new_tokens,
            n_threads=args.threads,
            gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
        )
        sys.stdout.write(json.dumps(proof, sort_keys=True, ensure_ascii=False) + "\n")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        # No private prompt, model response, key, source pathname or exception
        # text is published to CI/operator stderr on a failed native turn.
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
