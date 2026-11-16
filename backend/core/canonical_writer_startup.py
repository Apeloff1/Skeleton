"""Actual backend lifespan integration for an independently approved cutover.

No environment flag, public request, default setup command, AI response or
untrusted configuration can opt into this binding. The trusted launcher
supplies the verified short-lived approval before the existing app lifespan.
"""
from __future__ import annotations

from skeleton.app.canonical_writer_cutover import (
    VerifiedWriterCutover, WriterCutoverDenied, inspect_writer_inventory, qualify_writer_cutover,
    reserve_writer_deployment, verify_writer_deployment,
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


def configure_cutover(app, approval, *, local_checkpoint=None):
    if type(approval) is not VerifiedWriterCutover:
        raise WriterCutoverDenied("explicit signed canonical cutover required")
    approval.verify()
    if (getattr(app.state, "_trusted_writer_cutover", None) is not None
            or getattr(app.state, "_writer_cutover_installed", False)):
        raise WriterCutoverDenied("canonical cutover startup already configured")
    app.state._trusted_writer_cutover = approval
    app.state._trusted_writer_checkpoint = local_checkpoint


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
        # Reserve shared startup custody only after the first read-only
        # signed inventory passes. Re-scan under that non-expiring reservation.
        checkpoint = getattr(app.state,"_trusted_writer_checkpoint",None)
        if not callable(checkpoint):
            raise WriterCutoverDenied("trusted persistent deployment witness required")
        reservation = await reserve_writer_deployment(approval, epoch=epoch)
        local_evidence = checkpoint(reservation)
        if (type(local_evidence) is not dict or set(local_evidence) != {"generation","witness_sha256"}
                or local_evidence["generation"] != reservation["generation"]
                or type(local_evidence["witness_sha256"]) is not str
                or len(local_evidence["witness_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in local_evidence["witness_sha256"])):
            raise WriterCutoverDenied("persistent deployment witness unavailable")
        confirmed = await qualify_writer_cutover(
            approval, epoch=epoch, collections=_collections(conversation, memory),
            repository_namespace=memory.repository_namespace,
        )
        if confirmed != inventory:
            raise WriterCutoverDenied("canonical inventory changed during shared reservation")
        await verify_writer_deployment(epoch=epoch, reservation=reservation)
        await epoch.bind_deployment_latch(reservation)
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
            "shared_startup_reservation": reservation,
            "local_deployment_witness": local_evidence,
            "known_writer_reservation_revalidation_installed": True,
            "distributed_writer_fencing_verified": False,
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
