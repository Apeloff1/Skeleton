"""Actual backend lifespan integration for an independently approved cutover.

No environment flag, public request, default setup command, AI response or
untrusted configuration can opt into this binding. The trusted launcher
supplies the verified short-lived approval before the existing app lifespan.
"""
from __future__ import annotations

from skeleton.app.canonical_writer_cutover import (
    VerifiedWriterCutover, WriterCutoverDenied, inspect_writer_inventory, qualify_writer_cutover,
)
from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, bind_required_canonical_writers,
)


def _owners():
    from core.conversations import conversation_authority
    from core.canonical_memory import canonical_memory_repository, canonical_memory_writer
    from core.databases import core_db
    return core_db, conversation_authority, canonical_memory_repository, canonical_memory_writer


def _collections(conversation, memory):
    return {"threads": conversation.threads, "messages": conversation.messages,
            "records": memory.records, "revisions": memory.revisions,
            "projection_outbox": memory.projection_outbox,
            "idempotency": memory.idempotency}


def configure_cutover(app, approval):
    if type(approval) is not VerifiedWriterCutover:
        raise WriterCutoverDenied("explicit signed canonical cutover required")
    approval.verify()
    if (getattr(app.state, "_trusted_writer_cutover", None) is not None
            or getattr(app.state, "_writer_cutover_installed", False)):
        raise WriterCutoverDenied("canonical cutover startup already configured")
    app.state._trusted_writer_cutover = approval


async def install_before_lifespan(app):
    """Called before runtime scheduler, index creation or accepting requests."""
    approval = getattr(app.state, "_trusted_writer_cutover", None)
    if approval is None:
        # Preserve the ordinary unprotected installation, but never permit
        # this process to restart in legacy mode after protected binding.
        if getattr(app.state, "_writer_cutover_installed", False):
            raise WriterCutoverDenied("protected backend cannot downgrade")
        return
    if (type(approval) is not VerifiedWriterCutover
            or getattr(app.state, "_writer_cutover_installed", False)):
        raise WriterCutoverDenied("protected backend requires a fresh process")
    try:
        db, conversation, memory, writer = _owners()
        if (writer is None or writer.repository is not memory
                or getattr(conversation, "_required_canonical_source_epoch", None) is not None
                or getattr(memory, "_required_canonical_source_epoch", None) is not None
                or getattr(conversation, "canonical_source_epoch", None) is not None
                or getattr(memory, "canonical_source_epoch", None) is not None):
            raise WriterCutoverDenied("actual canonical writer ownership unavailable")
        epoch = MongoCanonicalSourceEpoch(db)
        inventory = await qualify_writer_cutover(
            approval, epoch=epoch, collections=_collections(conversation, memory),
            repository_namespace=memory.repository_namespace,
        )
        # No await between final signed/live admission and sticky binding.
        # A failed binding does not roll back to unprotected owners.
        approval.verify()
        bind_required_canonical_writers(conversation=conversation, memory=memory, epoch=epoch)
        app.state._writer_cutover_installed = True
        app.state.canonical_writer_cutover_evidence = {
            "inventory_sha256": inventory.digest,
            "epoch_count": len(inventory.epochs),
            "source_scope_count": len(inventory.source_scopes),
            "local_owner_graph_sha256": inventory.graph_sha256,
            "local_collection_counts": dict(inventory.collection_counts),
            "known_local_writer_binding_installed": True,
            "external_writer_coverage_verified": False,
            "guarded_local_ai_ready": False,
        }
    except WriterCutoverDenied:
        raise
    except Exception:
        raise WriterCutoverDenied("protected backend writer startup denied") from None


async def inspect_configured_inventory():
    db, conversation, memory, _ = _owners()
    return await inspect_writer_inventory(epoch=MongoCanonicalSourceEpoch(db),
                  collections=_collections(conversation, memory),
                  repository_namespace=memory.repository_namespace)
