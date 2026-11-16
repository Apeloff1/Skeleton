# Dragon delivery orchestration and custody

This combined draft adds five separate operating surfaces. Every remote
acquisition must still use the existing canonical crawler run/automation
authorization, robots rules, host restrictions, metering and shared leases.
No connector changes user agent identity, bypasses a restriction, uses a
fallback target, or accepts a credential or arbitrary requested URL.

## Registry connectors

Use the owner/editor GET `/api/dragon-academy/crawler/registry-connectors/{target_id}?revision={registry_sha}`
to obtain the exact plan digest from the installed dataset library. POST to
`/api/dragon-academy/crawler/registry-connectors` with target, revision, plan
digest, idempotency key, explicit consent, independent publisher permission
and metadata/capture rights acknowledgements. The existing session run or
finite automation route executes the canonical request. The finite connector
list is a source-controlled allowlist, not a claim that the entries were
verified live or that their declared terms permit every use. Some entries
are release indexes rather than downloadable data. Credential-required
sources need separate service-specific authorized API integration.

## Automatic local import and raw export custody

Prepare an independently obtained export and manifest using the existing
exact inspection and optional publisher signature procedures. Use a private
canonical owner-scope JSON file (no credentials) and separate private
pre-initialized ledger paths. The job command `python -m core.dragon_export_jobs`
accepts `enqueue`, `pulse`, and `resume`. Complete options are available with
`--help`. The enqueue operation requires the expected manifest SHA, finite
execution grant, explicit metadata rights, and optional signed proof. Jobs
are capped at 128 MiB and one million projected records; larger imports
retain the explicit manual path. Resume requires a stopped/drained worker
acknowledgement and cannot extend the original deadline. Sealed canonical
pages may persist after a partial settlement. No unattended retry of a held
or crashed job occurs.

The raw export command `python -m core.dragon_raw_export_custody` accepts
`retain`, `metadata`, and `purge-expired`. It requires an explicit independent
retention acknowledgement, expected SHA-256 and finite expiry. Raw BLOBs are
stored in 1 MiB chunks with bounded per-object and owner quotas, outside
context and training paths. Private storage/volume encryption is an operator
requirement. This retains independently provided raw files, not original
HTTP bodies that were never retained. Chunk reads require the current local
owner and active retention interval. Logical purge is not physical erasure
and does not revoke historic copies. Sensitive or private data requires a
separate lawful retention basis.

Opt into the existing recovery scheduler using the server-controlled
`SKL_DRAGON_DELIVERY_SCHEDULER=1`,
`SKL_DRAGON_DELIVERY_SCOPE_JSON`,
`SKL_DRAGON_EXPORT_JOB_DB_PATH` and/or `SKL_DRAGON_RAW_EXPORT_DB_PATH`.
No request can modify those settings. The scheduler advances at most one
job and four expired raw objects per pulse. It stops waiting after 45
seconds, keeps the thread resource credit until actual exit, and denies
further page authorization after cancellation. An already executing atomic
page may finish. The local operator must keep the configured scope and
permissions current; this is not an authenticated unattended remote-user
job service.

## Application backup

Register all local Dragon stores, including the new ledger and raw export
DB, using the configured storage paths. Stop all writers. Independently
produce protected application artifacts for the exact source revision,
Mongo databases (including account and original coordination authority),
configuration, user files, model/assets and external service state. A
private canonical plan with schema
`skeleton.dragon.application-backup.v1` declares the application commit
and per-artifact plane, absolute private path, size, SHA and protection
acknowledgement. The coordinator `python -m core.dragon_application_backup`
exports and verifies that declared set along with the Dragon local backup.
It refuses incomplete declared planes or differing bytes. It does not
produce external database dumps, verify encryption, discover every store,
perform a unified restore, or certify application launch. Those remain
separate provisioning and acceptance obligations.

## Capacity

Run `python -m core.dragon_capacity_qualification --growth-factor 10` on a
configured installation for a read-only, device-aggregated headroom report.
With explicit scratch permission, the --probe path writes non-sparse
random data, fsyncs, verifies exact readback and cleans up on the physical
devices. It reports measured MiB/s and configured bytes; it does not claim
sustained maximum production TPS, power-loss safety, or a verified 10x
expansion. Run the independent graph transaction probe, real Mongo
coordination and restore drills before operational qualification.
