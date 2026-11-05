"""Read-only exact-request SQLite replay, fenced to one active native owner.

A replay never calls native generation, but its committed output is still
private data: a model/tokenizer/tenant change during the SQLite read must
refuse disclosure even when the historical receipt remains valid on disk.
"""
from __future__ import annotations

from .contracts import identifier, utf8, nonnegative, number, refuse
from .result_protocol import verify_turn_receipt
from .identity import ActiveModel


def inspect_replay(
    worker, session_id, request_id, prompt, *, seed=0, temperature=0.8,
):
    """Inspect one committed request without allocating a session or worker."""
    bound = ActiveModel.from_supervisor(worker)
    result = worker.spine.replay(
        identifier(session_id),
        identifier(request_id),
        utf8(prompt, maximum=worker.spine.limits.input_bytes),
        seed=nonnegative(seed, maximum=2**32 - 1),
        temperature=number(temperature, minimum=0.000000001, maximum=2),
    )
    if result is None:
        if ActiveModel.from_supervisor(worker) != bound:
            refuse("native principal changed during empty durable replay")
        return {"committed": False, "no_second_generation": True}
    verified = verify_turn_receipt(
        result, model_sha256=bound.model_sha256,
        tokenizer_sha256=bound.tokenizer_sha256,
    )
    if verified["replayed"] is not True:
        refuse("durable replay was not marked replayed")
    if ActiveModel.from_supervisor(worker) != bound:
        refuse("native principal changed during committed SQLite replay")
    return {
        "committed": True, "no_second_generation": True,
        "output_sha256": verified["output_sha256"],
    }
