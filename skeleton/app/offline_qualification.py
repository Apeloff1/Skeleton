"""Two-turn on-device model qualification without hosted-model fallback.

This is a functional runtime and persistence acceptance check. A fresh local
model/session is reopened between turns, exercising real inference, validated
execution receipts and the same SQLite conversation context used by the app.
It does not certify model quality, a new OS process or network air-gapping.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
import tempfile
from typing import Any

from .local_ai import OfflineAISession, OfflineGGUFSession, load_native_checkpoint
from .offline_readiness import inspect_local_readiness
from .offline_workspace import DurableOfflineSession, OfflineWorkspace


SCHEMA = "skeleton.app.offline_functional_qualification.v1"


def qualify_offline_model(
    *,
    model: str | Path | None = None,
    deployment: str | Path | None = None,
    max_output_tokens: int = 2,
) -> dict[str, Any]:
    """Exercise two complete local turns across closed/reopened sessions.

    All state is written in a self-cleaning, locally created temporary
    directory. Only bound hashes and token counts are reported; generated
    text, restored conversation and user credentials are never printed.
    """
    if (model is None) == (deployment is None):
        raise ValueError("select exactly one local model or GGUF deployment")
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 256:
        raise ValueError("offline qualification token limit must be 1-256")
    initial = inspect_local_readiness(model=model, deployment=deployment)
    identity = (initial["model_digest"], initial["runtime_digest"])

    def open_model() -> OfflineAISession | OfflineGGUFSession:
        if model is not None:
            return OfflineAISession(load_native_checkpoint(model))
        return OfflineGGUFSession(deployment)

    receipts: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="skeleton-local-qualification-") as scratch:
        state = Path(scratch) / "qualification.sqlite"
        for turn, question in enumerate(("hello", "world"), start=1):
            # New model engine and SQLite connection each round. This is a
            # session re-open, NOT a verified new operating-system process.
            with OfflineWorkspace(state) as before:
                expected_revision, expected_history = before.open("qualify", identity[0])
            if expected_revision != turn - 1 or len(expected_history) != (turn - 1) * 2:
                raise RuntimeError("offline qualification context revision changed")
            durable = DurableOfflineSession(open_model(), state, session_id="qualify")
            try:
                if durable.history != expected_history:
                    raise RuntimeError("offline qualification failed context restoration")
                answer = asyncio.run(
                    durable.ask(question, max_output_tokens=max_output_tokens)
                )
                if (
                    not isinstance(answer.text, str) or not answer.text.strip()
                    or answer.model_digest != identity[0]
                    or not isinstance(answer.execution_receipt_digest, str)
                    or len(answer.execution_receipt_digest) != 64
                    or any(ch not in "0123456789abcdef"
                           for ch in answer.execution_receipt_digest)
                    or durable.revision != turn
                    or len(durable.history) != turn * 2
                ):
                    raise RuntimeError("offline qualification model result is not bound")
                receipts.append({
                    "turn": turn,
                    "output_sha256": hashlib.sha256(
                        answer.text.encode("utf-8")
                    ).hexdigest(),
                    "execution_receipt_digest": answer.execution_receipt_digest,
                    "input_tokens": answer.input_tokens,
                    "output_tokens": answer.output_tokens,
                })
            finally:
                durable.close()
        # Independently reopen the final SQLite state and confirm exactly
        # two complete user-assistant turns; no inferred success from stdout.
        with OfflineWorkspace(state) as after:
            final_revision, final_history = after.open("qualify", identity[0])
            if (
                final_revision != 2 or len(final_history) != 4
                or final_history[0][0] != "user"
                or final_history[2][0] != "user"
                or final_history[0][1] != "hello"
                or final_history[2][1] != "world"
            ):
                raise RuntimeError("offline qualification persistent state mismatch")

    final = inspect_local_readiness(model=model, deployment=deployment)
    if (final["model_digest"], final["runtime_digest"]) != identity:
        raise RuntimeError("local model/runtime identity changed during qualification")
    return {
        "schema_version": SCHEMA,
        "kind": initial["kind"],
        "model_digest": identity[0],
        "runtime_digest": identity[1],
        "artifacts_verified_before_and_after": True,
        "two_real_generation_calls_completed": True,
        "session_reopened_between_turns": True,
        "same_process_qualification": True,
        "sqlite_context_restored_and_verified": True,
        "turns_completed": 2,
        "receipts": receipts,
        "network_isolation_verified": False,
        "trained_model_quality_verified": False,
        "release_signed": False,
    }


__all__ = ["SCHEMA", "qualify_offline_model"]
