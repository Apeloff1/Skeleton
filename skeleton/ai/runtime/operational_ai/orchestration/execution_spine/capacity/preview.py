"""Read-only context planning surface for independent diagnostics."""
from __future__ import annotations
from ..contracts import SpineError
from .planner import prepare_context
from .proofs import describe_decision


def preview(spine, session: str, prompt: str, *, policy=None) -> dict:
    """No native generation, request reservation, state writes or tool calls."""
    from ..history import load
    from ..principal import require_session
    from ..contracts import identifier
    identifier(session, 'session')
    with spine.db.snapshot() as conn:
        require_session(conn, spine.identity, session)
        history = load(conn, spine.identity, session, spine.limits)
    evidence = tuple(spine.evidence_provider(spine.identity,prompt)) if spine.evidence_provider else ()
    prepared = prepare_context(identity=spine.identity, backend=spine.backend,
        history=history, prompt=prompt, evidence=evidence, limits=spine.limits,
        policy=policy)
    return describe_decision(prepared) | {'status':'context-preview-not-native-inference'}
