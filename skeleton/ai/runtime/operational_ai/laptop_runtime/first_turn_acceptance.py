"""Explicit, source-approved real first-turn inference with durable replay proof.

A caller must have independently installed and approved actual native GGUF
model bytes through activate_checked. This function does not install or fetch
weights, obtain source rights, bypass isolation, or certify hardware/release.
"""
from __future__ import annotations

import secrets

from .contracts import refuse, utf8
from .identity import ActiveModel
from .session_adapter import create
from .turn_bridge import TurnBridge
from .replay_probe import inspect_replay
from .installed_witness import require_activated_source
from .source_contract import valid_source_snapshot


def run(
    worker, *, prompt, approved=False, installed_receipt=None,
    require_real=False,
) -> dict[str, object]:
    """Make exactly one NEW native inference and independently inspect replay.

    The installed model and tokenizer must stay bound to the same principal
    throughout generation and both SQLite receipt verification boundaries.
    An already-cached request is not fresh inference acceptance evidence.
    """
    if approved is not True:
        refuse("real end-to-end inference approval required")
    if type(require_real) is not bool:
        refuse("real acceptance must be an explicit boolean")
    # Pure private-input validation MUST precede even read-only installed
    # source/probe activity. Invalid direct-caller prompts are held before
    # any source inspection, durable allocation or isolated model effect.
    verified_prompt = utf8(
        prompt, maximum=worker.spine.limits.input_bytes,
    )
    # No synthetic or arbitrary worker may claim native GGUF observation.
    # All source evidence comes from the existing verified installer and the
    # canonical supervisor, not from the model's generated text.
    source = (
        require_activated_source(worker, installed_receipt)
        if installed_receipt is not None else None
    )
    if source is not None:
        # A partial, bool-valued, upper-case or forged source inventory
        # must not become real installed GGUF acceptance evidence.
        if not valid_source_snapshot(source, ActiveModel.from_supervisor(worker)):
            refuse("complete installed native source witness required")
        source = source.copy()
    if require_real and source is None:
        refuse("independent installed source proof required")
    bridge = TurnBridge(worker)
    bound = bridge.identity
    session = create(worker)
    request = "r_" + secrets.token_hex(16)

    # Native call is non-retryable on uncertainty; bridge requires the
    # authoritative committed SQLite text and digest before returning.
    first = bridge.turn(
        session, request, verified_prompt, seed=17, temperature=0.8,
    )
    if first["replayed"] is not False:
        refuse("first-turn acceptance requires a fresh native generation")
    if first["generated_tokens"] < 1:
        refuse("first-turn acceptance requires actual output token evidence")

    # This is a second, explicitly read-only identity-bound retrieval,
    # not a second native forward pass or synthetic model response.
    replay = inspect_replay(
        worker, session, request, verified_prompt, seed=17, temperature=0.8,
    )
    if (replay["committed"] is not True
            or replay["no_second_generation"] is not True
            or replay["output_sha256"] != first["output_sha256"]):
        refuse("native first-turn durable replay disagrees")

    # Even a correct transaction is not publishable through a model- or
    # tenant-stale operator session after a principal epoch transition.
    if ActiveModel.from_supervisor(worker) != bound:
        refuse("native model identity changed during first-turn acceptance")
    if source is not None:
        # Commit and replay prove the output, not that an installed model
        # stayed alive with the same archive, tokenizer, rights evidence and
        # kernel-fenced capacity lease while inference was in flight.
        # This check is read-only. A failed check preserves SQLite custody
        # and MUST NOT trigger a second native forward pass.
        observed = require_activated_source(worker, installed_receipt)
        if (not valid_source_snapshot(observed, bound)
                or observed != source):
            refuse("verified native source changed after model generation")
        if ActiveModel.from_supervisor(worker) != bound:
            refuse("native principal changed after final source verification")

    return {
        "schema": "laptop-real-first-turn-e2e.v1",
        "session_id": session,
        "request_id": request,
        "model_sha256": bound.model_sha256,
        "tokenizer_sha256": bound.tokenizer_sha256,
        "output_sha256": first["output_sha256"],
        "prompt_tokens": first["prompt_tokens"],
        "generated_tokens": first["generated_tokens"],
        "replayed_without_generation": True,
        "native_model_observed": source is not None,
        "installed_source_bound": source is not None,
        "evidence_grade": (
            "native-installed-source-and-sqlite"
            if source is not None else "source-only-simulated-or-unverified"
        ),
        "installed_source": source,
        "operator_approved_turn_attempt": True,
        "operator_approved_real_inference": source is not None,
        "device_qualified": False,
        "release_certified": False,
    }


__all__ = ["run"]
