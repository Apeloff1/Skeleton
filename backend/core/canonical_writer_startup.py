"""Actual backend lifespan integration for an independently approved cutover.

No environment flag, public request, default setup command, AI response or
untrusted configuration can opt into this binding. The trusted launcher
supplies the verified short-lived approval before the existing app lifespan.
"""
from __future__ import annotations

import asyncio

from skeleton.app.canonical_writer_cutover import (
    VerifiedWriterCutover, WriterCutoverDenied, inspect_writer_inventory, qualify_writer_cutover,
    reserve_writer_deployment, verify_writer_deployment,
)
from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, bind_required_canonical_writers,
    configured_canonical_epoch, verify_canonical_source_writer_inventory,
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


def configure_cutover(app, approval, *, local_checkpoint=None, after_binding=None, before_database_close=None):
    if type(approval) is not VerifiedWriterCutover:
        raise WriterCutoverDenied("explicit signed canonical cutover required")
    approval.verify()
    if (getattr(app.state, "_writer_cutover_requested", False)
            or getattr(app.state, "_trusted_writer_cutover", None) is not None
            or getattr(app.state, "_writer_cutover_installed", False)):
        raise WriterCutoverDenied("canonical cutover startup already configured")
    if (after_binding is None) != (before_database_close is None) or (
            after_binding is not None and (not callable(after_binding) or not callable(before_database_close))):
        raise WriterCutoverDenied("protected stack lifecycle hooks must be paired")
    app.state._writer_cutover_after_binding = after_binding
    app.state._writer_cutover_before_database_close = before_database_close
    app.state._writer_cutover_requested = True
    app.state._trusted_writer_cutover = approval
    app.state._trusted_writer_checkpoint = local_checkpoint


async def install_before_lifespan(app):
    """Called before runtime scheduler, index creation or accepting requests."""
    approval = getattr(app.state, "_trusted_writer_cutover", None)
    if approval is None:
        # Preserve the ordinary unprotected installation, but never permit
        # this process to restart in legacy mode after protected binding.
        if (getattr(app.state, "_writer_cutover_requested", False)
                or getattr(app.state, "_writer_cutover_installed", False)):
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
        app.state._writer_cutover_runtime = (conversation,memory,writer,epoch)
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
        after_binding = getattr(app.state,"_writer_cutover_after_binding",None)
        if after_binding is not None:
            evidence = await after_binding(app.state._writer_cutover_runtime)
            if (type(evidence) is not dict or evidence.get("shared_canonical_owners_observed") is not True
                    or evidence.get("scoped_reviewer_challenge_observed") is not True
                    or evidence.get("guarded_registry_available_observed") is not True
                    or evidence.get("inference_qualified") is not False):
                raise WriterCutoverDenied("protected co-hosted engine not qualified")
            app.state.protected_stack_observation = evidence
    except WriterCutoverDenied:
        app.state._writer_cutover_quarantined = True
        raise
    except Exception:
        app.state._writer_cutover_quarantined = True
        raise WriterCutoverDenied("protected backend writer startup denied") from None


async def inspect_configured_inventory():
    db, conversation, memory, _ = _owners()
    return await inspect_writer_inventory(epoch=MongoCanonicalSourceEpoch(db),
                  collections=_collections(conversation, memory),
                  repository_namespace=memory.repository_namespace)


def _readiness(code, *, required, ok=False):
    # Only positive evidence about known writer binding; never inference.
    return {"ok":ok,"required":required,"code":code,
            "known_local_writer_binding_observed":required and ok,
            "external_writer_coverage_verified":False,
            "guarded_local_ai_ready":False}


async def _observe_protected_runtime(app):
    try:
        runtime=getattr(app.state,"_writer_cutover_runtime",None)
        if (getattr(app.state,"_writer_cutover_requested",False) is not True
                or getattr(app.state,"_writer_cutover_installed",False) is not True
                or type(runtime) is not tuple or len(runtime)!=4
                or getattr(app.state,"_writer_cutover_quarantined",False)):
            raise WriterCutoverDenied("protected writer runtime missing")
        conversation,memory,writer,epoch=runtime
        _,actual_conversation,actual_memory,actual_writer=_owners()
        if (type(epoch) is not MongoCanonicalSourceEpoch
                or actual_conversation is not conversation or actual_memory is not memory
                or actual_writer is not writer or writer.repository is not memory
                or configured_canonical_epoch(conversation) is not epoch
                or configured_canonical_epoch(memory) is not epoch):
            raise WriterCutoverDenied("protected writer runtime ownership changed")
        verify_canonical_source_writer_inventory(conversation=conversation,memory=memory,epoch=epoch)
        await epoch._assert_deployment_latch()
        if (getattr(app.state,"_writer_cutover_runtime",None) is not runtime
                or getattr(app.state,"_writer_cutover_installed",False) is not True
                or configured_canonical_epoch(conversation) is not epoch
                or configured_canonical_epoch(memory) is not epoch
                or getattr(app.state,"_writer_cutover_quarantined",False)):
            raise WriterCutoverDenied("protected writer runtime changed during observation")
        return _readiness("protected_writer_binding_observed",required=True,ok=True)
    except asyncio.CancelledError:
        app.state._writer_cutover_quarantined=True
        raise
    except Exception:
        app.state._writer_cutover_quarantined=True
        return _readiness("protected_writer_authority_unavailable",required=True)


async def protected_writer_readiness(app, *, timeout=1.8):
    """Bounded, coalesced observation for the public backend health probe.

    Concurrent requests share one outstanding task; caller timeout or
    cancellation does not cancel the authoritative check. Never serve a
    cached successful observation. Ordinary install does not acquire a new
    database dependency, and unprotected health is explicitly not custody.
    """
    state=app.state
    required=bool(getattr(state,"_writer_cutover_requested",False)
                  or getattr(state,"_writer_cutover_installed",False)
                  or getattr(state,"_trusted_writer_cutover",None) is not None
                  or getattr(state,"_writer_cutover_runtime",None) is not None
                  or getattr(state,"_writer_cutover_quarantined",False))
    if not required:
        return _readiness("legacy_writer_mode_unqualified",required=False,ok=True)
    if getattr(state,"_writer_cutover_quarantined",False):
        return _readiness("protected_writer_authority_unavailable",required=True)
    task=getattr(state,"_writer_readiness_task",None)
    if task is None or task.done():
        task=asyncio.create_task(_observe_protected_runtime(app),name="protected-writer-readiness")
        state._writer_readiness_task=task
    try:
        return await asyncio.wait_for(asyncio.shield(task),timeout=timeout)
    except TimeoutError:
        return _readiness("protected_writer_observation_pending",required=True)


async def drain_protected_writer_readiness(app):
    """Cancel outstanding health work before the shared Mongo client closes."""
    task=getattr(app.state,"_writer_readiness_task",None)
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)


async def drain_protected_stack_before_database_close(app):
    """The engine may use the exact same backend Mongo client until drained."""
    hook=getattr(app.state,"_writer_cutover_before_database_close",None)
    if hook is not None:
        if getattr(app.state,"_writer_cutover_installed",False) is not True:
            raise WriterCutoverDenied("protected stack shutdown custody unavailable")
        await hook()
