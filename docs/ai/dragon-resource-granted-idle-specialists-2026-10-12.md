# Dragon research hatchlings: globally admitted worker tickets
**Date: 2026-10-12.** Implemented in the Dragon feature branch, pending exact-head CI qualification.

## New working capability
The signed-nest source feed can now request a **real shared-global-resource reservation** for a single idle research assignment. The ticket is not an execution of a crawler, a network grant, a media license, a training approval or an XP entitlement. The host application must supply separately authenticated, rights-reviewed execution workers and verified idle telemetry.

The DragonNestWorkerAdmission controller calls the canonical DragonNestSourceFeed to select task-relevant article/video/source-update work. It then submits a bounded checkpointable SessionTask to the canonical DragonResourceSession and the global scheduler. Local-only resource admission is advisory and **never** issues a worker ticket.

## Guarantees
- Each ticket is owner-bound, media-lane bound, URL/source-identity bound and uniquely identified by an opaque task ID.
- A ticket is valid for **60 seconds** at most. It carries a digest of the exact selected research assignment.
- A worker must call authorize_chunk before every network or compute chunk; it rechecks signed nest state, at least five minutes idle, current consent, fresh hardware telemetry, global preemption status, source policy, source revision and selected-assignment identity.
- When the foreground requests resources, global preemption and the local yield flag deny new background chunks. A yield request never falsely claims that the worker released its memory.
- The trusted worker calls stopped only after a real stop acknowledgment, which releases the shared global grant exactly once.
- Failure during ticket creation releases already-reserved capacity because no worker has yet started.
- A ticket does not change source review status, download copyrighted media, update model weights, grant new knowledge or grow any hatchling.

## Three differentiated lanes
Articles originate from the task-aware technical atlas. Videos require matching registered video candidate identities, and updates require reviewed evidence of genuinely changed source text plus a separately supplied publication hint. The queue prioritizes on-task topics, permits useful adjacent topics, and avoids redundant source allocations. The global reservation applies to each lane the same way; actual retrieval and media-specific extraction are still separately owned by the authorized crawler and video adapters.

## Representative trusted integration
```python
feed = DragonNestSourceFeed(almanacs, technical_atlas, signed_nest_store)
global_session = DragonResourceSession(
    global_resources=global_resource_scheduler, tenant=owner
)
admission = DragonNestWorkerAdmission(feed, global_session)
decision = admission.begin(
    owner, sample=sample, at=utc_now, idle_since=real_idle_since,
    now_seconds=sample_clock, authorized=True, trusted_worker=True,
    consented=consent, article_consent=True, video_consent=video_consent,
    updates_consent=updates_consent, video_hints=video_hints,
    update_hints=update_hints
)
if decision.ticket is not None:
    # Authorized worker: recheck chunk admission, then enforce existing
    # DNS/redirect/robots/terms/source-rights and independent review gates.
    # After actual stop: admission.stopped(ticket, ..., worker_stopped=True)
    pass
```

## Acceptance checks
The dedicated test module contains seven tests verifying global vs local admission, active resource accounting, per-chunk revalidation, consent and idle revocation, foreground preemption, ticket expiry, forgery rejection, blocked source revision and exact stopped-worker accounting. It is run by the Dragon AI Verification workflow.

Run: python -m pytest -q --noconftest tests/test_dragon_nest_worker_admission.py

Remaining: supply live application idle/foreground sensors, production-backed global-resource scheduler, crash-safe worker leases, actual media-specific safe acquisition, source publication custody, independent Wiki/HOAG reviewed promotion, and on-device performance measurements. This increment is not a claim of automatically running three background gatherers, completed live crawling or training improvements.
