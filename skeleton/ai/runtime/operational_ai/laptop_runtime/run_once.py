"""Single source-bound native turn; reject invalid requests before SQLite writes.

One-off local inference uses the canonical dispatcher and existing supervised
ExecutionSpine. Invalid prompt, sampler, request identity or tenant state
must never allocate an orphan session as a side effect of failed preflight.
"""
from __future__ import annotations

import secrets

from .contracts import identifier, utf8, nonnegative, number, refuse
from .dispatcher import LaptopDispatcher
from .source_guard import SourceFencedLaptopDispatcher


def generate_once(
    worker, question, *, session=None, request_id=None,
    seed=0, temperature=0.8, dispatcher=None,
):
    """Admit all caller-supplied fields before creating a durable session.

    On approved fresh work, the single dispatcher owns SQLite session
    allocation and independent committed-replay verification. A supplied
    existing session is *never* implicitly created or repaired. The laptop
    CLI injects its installed-source guard for both create and native turn.
    """
    if dispatcher is None:
        dispatcher = LaptopDispatcher(worker)
    elif (type(dispatcher) is not SourceFencedLaptopDispatcher
          or dispatcher.worker is not worker):
        refuse("one-shot dispatcher must be the same live source-fenced worker")
    # Structural checks are pure. A user error at this point cannot leave a
    # newly created SQLite session or reserve a native GPU/CPU model call.
    request = (identifier(request_id, "request ID") if request_id is not None
               else "r_" + secrets.token_hex(16))
    existing = (identifier(session, "session ID") if session is not None
                else None)
    prompt = utf8(question, maximum=dispatcher.limits.input_bytes)
    checked_seed = nonnegative(seed, maximum=2**32 - 1)
    checked_temperature = number(
        temperature, minimum=0.000000001, maximum=2,
    )

    session_id = (
        existing if existing is not None
        else dispatcher.dispatch("create", {})["session_id"]
    )
    output = dispatcher.dispatch("turn", {
        "session_id": session_id,
        "request_id": request,
        "prompt": prompt,
        "seed": checked_seed,
        "temperature": checked_temperature,
    })
    return {
        "session_id": session_id,
        "request_id": request,
        "receipt": output["receipt"],
        "model_source": "actual-offline-GGUF",
    }


__all__ = ["generate_once"]
