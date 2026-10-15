"""Exercise the real Stage-5 container context identity contract offline."""
from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from skeleton.contracts.context import ContextEnvelope
from scripts.check_engine_container_boundary import _command, _context, _now


def test_engine_container_context_id_binds_exact_digest():
    context = _context()
    assert isinstance(context, ContextEnvelope)
    assert UUID(context.context_id).version == 5
    assert context.context_id == str(
        uuid5(NAMESPACE_URL, "skeleton-context:" + context.context_digest)
    )
    assert context.source_snapshot[0][0] == context.instruction_segments[0].segment_id


def test_engine_command_uses_exact_bound_context_identity():
    context = _context()
    command = _command(context, started=_now())
    assert command.context_id == context.context_id
    assert command.context_digest == context.context_digest
