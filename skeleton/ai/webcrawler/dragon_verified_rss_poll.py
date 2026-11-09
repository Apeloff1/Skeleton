"""Transactional RSS update handoff: signed snapshot + idle scheduling together.

The Updates hatchling already has (1) an independently signed feed-snapshot
queue and (2) a durable due-time scheduler. These controls previously
committed separately. This strict entry point binds both to exactly the same
owner/source, URL, policy receipt, scheduled generation and SQLite transaction,
preventing a partial feed commit if recording its poll later fails.

This module never fetches a URL, grants robots/terms rights, issues worker
tickets, or promotes training/model weights. Trusted operators must provision
the external fetch issuer and a fresh rights decision before calling it.
"""
from __future__ import annotations

import sqlite3
from threading import RLock
from hashlib import sha256

from .dragon_rss_update_queue import DragonRssUpdateQueue, SignedRssSnapshot
from .dragon_rss_freshness_scheduler import DragonRssFreshnessScheduler
from .dragon_nest_worker_admission import (
    DragonNestWorkerAdmission, HatchlingWorkerTicket,
)
from skeleton.ai.game_builder.contracts import canonical_digest


class DragonVerifiedRssPoll:
    """Operator-owned coordinator; no independent crawling capability."""

    def __init__(self, queue: DragonRssUpdateQueue,
                 scheduler: DragonRssFreshnessScheduler):
        if (not isinstance(queue, DragonRssUpdateQueue)
            or not isinstance(scheduler, DragonRssFreshnessScheduler)
            or queue.db is not scheduler.db
            or not isinstance(queue.db, sqlite3.Connection)):
            raise TypeError("RSS schedule and evidence queue must share one canonical SQLite connection")
        self.queue=queue
        self.scheduler=scheduler
        self.db=queue.db
        self._lock=RLock()

    def accept(self, ticket: HatchlingWorkerTicket,
               admission: DragonNestWorkerAdmission, *,
               xml: bytes, receipt: SignedRssSnapshot,
               reviewer_public_key: bytes, trusted_issuer: str, key_id: str,
               admission_kwargs: dict, expected_revision: int,
               now: int, authorized: bool) -> dict:
        if (authorized is not True or
            not isinstance(ticket,HatchlingWorkerTicket)
            or ticket.lane!="updates" or
            not isinstance(receipt,SignedRssSnapshot) or
            not isinstance(admission,DragonNestWorkerAdmission)
            or type(expected_revision) is not int or expected_revision<1
            or type(now) is not int or now<0
            or type(admission_kwargs) is not dict or
            type(xml) is not bytes):
            raise PermissionError("separately authorized idle RSS worker required")
        if receipt.body_sha256!=sha256(xml).hexdigest():
            raise PermissionError("RSS snapshot bytes not signed by issuer")
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                # Source and policy registration are HMAC-verified by the
                # scheduler BEFORE creating any new durable queue rows.
                current=self.scheduler._current(ticket.owner,ticket.source_id)
                if (current is None
                    or current["revision"]!=expected_revision
                    or current["feed_url"]!=ticket.source_url
                    or receipt.owner!=ticket.owner
                    or receipt.source_id!=ticket.source_id
                    or receipt.feed_url!=ticket.source_url
                    or receipt.rights_receipt_digest!=current["external_policy_digest"]
                    or now<current["next_due"]):
                    raise PermissionError("scheduled RSS identity, rights or generation mismatch")
                queued=self.queue.ingest(
                    ticket,admission,xml,receipt,
                    reviewer_public_key=reviewer_public_key,
                    trusted_issuer=trusted_issuer,key_id=key_id,
                    now=now,admission_kwargs=admission_kwargs,
                    authorized=True,transaction_managed=True)
                if queued["feed_snapshot_digest"]!=receipt.body_sha256:
                    raise ValueError("RSS source custody digest changed")
                # In the SAME SQLite transaction, advance the source's
                # durable schedule only after independent receipt checks.
                scheduled=self.scheduler.record_poll(
                    ticket,admission,admission_kwargs=admission_kwargs,
                    expected_revision=expected_revision,now=now,
                    succeeded=True,snapshot_digest=receipt.body_sha256,
                    authorized=True,transaction_managed=True)
                if (scheduled["revision"]!=expected_revision+1
                    or queued["owner"]!=ticket.owner
                    or queued["source_id"]!=ticket.source_id):
                    raise ValueError("RSS queue/schedule transaction mismatch")
                # Final pre-commit check: new foreground user actions or
                # worker revocations must suppress further idle effects.
                if not admission.authorize_chunk(ticket,**admission_kwargs):
                    raise PermissionError("idle ticket preempted before durable RSS commit")
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
        core={
            "schema":"skeleton.dragon.atomic_verified_rss_poll.v1",
            "owner":ticket.owner,"source_id":ticket.source_id,
            "feed_snapshot_digest":receipt.body_sha256,
            "signed_snapshot_receipt_digest":canonical_digest(receipt.body()),
            "policy_receipt_digest":receipt.rights_receipt_digest,
            "new_unverified_research_leads":queued["new_unverified_leads"],
            "candidate_research_items":queued["items_seen"],
            "poll_revision":scheduled["revision"],
            "next_due":scheduled["next_due"],
            "atomic_commit":True,
            "idle_ticket_rechecked":True,
            "network_requests":0,"crawl_rights_granted":False,
            "independent_fact_review_required":True,
            "training_authorized":False,"weights_promoted":False,
        }
        return {**core,"handoff_digest":canonical_digest(core)}
