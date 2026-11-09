# Dragon Family: egg-to-adult companion and three idle-only hatchlings

**Engineering workpass:** 2026-10-12 (UTC). **Wire:** `skeleton.ai.dragon.family.v1`.
**Change log:** UTC event timestamp, source ID, reason, previous SHA-256 event hash,
new SHA-256 event hash. Every changed-source improvement displays in parentheses.

## Canonical placement and implementation status

The existing crawler/game-knowledge owner is `skeleton/ai/webcrawler/`.
The companion is rendered by `frontend/features/Jeeves/companion/`.
The authenticated academy router reuses `SKL_DRAGON_PRACTICE_DB_PATH` and exposes
a read-only `family` field in `GET /api/dragon-academy/status`.

This does **not** launch another crawler, service, internet fetcher, ML trainer,
credential boundary, scheduler or knowledge authority. The user-facing game
derives its stages from source/evidence facts in the canonical SQLite store.
The existing full approval chain (crawled custody -> repeated evidence ->
knowledge promotion -> human review -> practice registration) remains in force.
A hash-chain provides accidental tampering detection, not a cryptographic
proof of publication or protection from administrators who can rewrite the DB.

| Family member | Stage mechanism | What counts as new information |
|---|---|---|
| Mother dragon | Egg, hatchling, juvenile, adolescent, winged, adult | Unique reviewed sources in a **sealed original inventory** |
| Ember | Egg, hatchling, juvenile, dragon | Approved article revisions relevant directly or adjacently to current task |
| Flicker | Egg, hatchling, juvenile, dragon | Approved transcript/audio/visual video chunks, from an authorized media adapter |
| Scout | Egg, hatchling, juvenile, dragon | A verified, non-replayed **change** to a previously acquired source |

Source coverage is not synonymous with web completeness. An approved,
fixed inventory must be fully consumed before the mother lays **exactly three
eggs once**. New eligible discoveries may be enrolled *after* that event for
the children, without moving the mother's completion goalposts.
All three children remain eggs until they acquire distinct reviewed content
while genuinely idle, and they never grow from unchanged URLs, revisions,
metadata, rereads, UI animation or conversation length.

## Trusted producer sequence

The product API is *not* an ingestion API. Its principal is derived from the
authenticated tenant and email; it never accepts a browser's owner ID. Only a
trusted crawler producer may construct a `DragonFamilyCustodyBridge` over the
same durable SQLite DB after the canonical promotion + independent human review
have actually been recorded. A `SourceReceipt` is not authority by itself.

```python
from skeleton.ai.webcrawler.dragon_family_custody_bridge import (
    DragonFamilyCustodyBridge, ApprovedSourceSnapshot,
)

bridge = DragonFamilyCustodyBridge(canonical_crawler_db, owner)
family = bridge.family()

# `document` must be a real policy-admitted CrawlDocument from the
# authorized crawler, with exact text digest and acquisition provenance.
# claim_id must already have reviewed evidence in the existing knowledge and
# DragonPracticeLab ledgers. A denied/obsolete review raises PermissionError.
source, receipt = bridge.article(
    ApprovedSourceSnapshot(source_id="game-engine-source-v1",
                           media="article",
                           url=document.canonical_url,
                           topics=("game_engine", "physics"),
                           claim_id=reviewed_claim_id,
                           observed_at=trusted_event_time),
    document,
)
family.enroll(owner, (source,), authorized=True, now=trusted_registration_time)

# Explicitly finalize the complete source manifest BEFORE first consumption;
# this is required to prevent laying eggs after only the first batch.
family.seal_inventory(owner, authorized=True, now=trusted_seal_time)
family.consume(owner, receipt, authorized=True)
```

For video, call the existing `ingest_authorized_video` with a real
`VideoSourceGrant`, then `bridge.video(snapshot, chunks)`. The bridge
hashes a bounded canonical representation of time-coded chunks; the exact
revision MUST be admitted by the canonical evidence ledger and independently
reviewed before growth. A claim about text alone is not evidence of decoded
frames, successful video playback or video permissions.

**Critical requirement:** Do not trust browser-provided `approved`, source
digests, URLs, `observed_at`, relevance tags, last-user-activity or system
idle state. A review receipt alone is not enough; the bridge rechecks the
exact source revision in `dragon_evidence_passes`, the reviewed lesson,
and the current claim's entire evidence fingerprint. Retraction or a changed
evidence aggregate blocks future admissions. Approval is checked again
*inside* the SQLite write transaction.

## Bounded idle-only research

Use the existing authorized host scheduler to call `IdleBroodRunner.tick`
while a time-bounded, explicit user research grant is active. No UI polling
creates research, and no background loop is created by this package.

```python
from skeleton.ai.webcrawler.dragon_family import IdleBroodRunner

def verified_idle_window():
    # MUST be implemented by the host from authenticated activity,
    # running jobs, power/network policy, resource quotas and live opt-in.
    return current_authoritative_idle_signals()

runner = IdleBroodRunner(family, max_per_tick=3)
report = runner.tick(
    owner,
    (
        ("article", fetch_and_verify_next_article_receipt),
        ("video", fetch_and_verify_next_video_receipt),
        ("monitor", fetch_and_verify_next_changed_source_receipt),
    ),
    authorized=True,
    idle_state=verified_idle_window,
    task_topics=("game_engine",),
    adjacent_topics=("physics", "collision_detection"),
)
```

The host passes **callbacks returning already policy-verified SourceReceipt**.
The network adapter owns DNS rebinding checks, robots rules, terms, rate limits,
HTTP redirect checks, byte/time limits, video consent, and media licensing.
A callback cannot run unless idle admission passes; the runner rechecks live
idle state after every callback and before accepting a result. One task per
child per tick, at most three by default. The service never catches up missed
ticks and must stop on user activity, foreground use, memory pressure, another
running job, lost consent or exhausted allowance. Supplied callbacks must have
their own cancellable deadlines; synchronous network calls already in progress
cannot be forcibly cancelled by a pure state machine.

Idle means at least five minutes since last real user activity, no foreground
work, zero busy jobs, current consent and available resources. A source
observation may not be in the future or older than five minutes relative to the
trusted idle-window timestamp. Under changed tasks, adjacent topics must
explicitly overlap the trusted source tags; no keyword guessing can count as
evidence. New versions are checked for chronological and content novelty
across **all three** hatchlings to avoid XP farming.

### Visual and accessibility behavior

The Academy status returns source count, maternal stage, exact brood roles,
per-child stage and level, number of **novel** acquisitions, last-grew-at UTC,
most recent verified evolution history and `inventory_sealed`.
`dragonFamilyProjection.ts` validates the wire before showing progression;
`DragonFamilyNest.tsx` presents a selectable egg/dragon trio and a
timestamped, source-attributed journal in the existing companion UI.
No tap, animation, screen refresh, inferred topic, or petting action grants XP.
Reduced-motion settings still govern companion animation; the nest is static.

Example:
- `2026-10-12T14:22:31.000Z` — Ember — hatched — article-017
  **(new: independently approved information acquired)**
- `2026-10-12T14:29:04.000Z` — Scout — grew — api-doc-021
  **(improved: documentation erratum independently confirmed)**

These timestamps are **format examples**, not claims that those sources
were fetched or improved in this workpass.

## Verification and recovery

Focused Python commands:

```bash
pytest -q tests/test_ai_webcrawler_dragon_family.py
pytest -q tests/test_ai_webcrawler_dragon_family_custody_bridge.py
pytest -q tests/test_ai_webcrawler_dragon_practice_lab.py
```

Frontend:

```bash
cd frontend
yarn test:dragon-companion
yarn typecheck
```

Required architecture and release checks remain those in `AGENTS.md`.
This project uses one canonical SQLite store, so operator migrations,
backup/recovery, WAL/SHM permission checks, and tenant isolation must be
part of host readiness. Read-only status replays and checks every historical
hash link; integrity failure blocks the entire affected owner's projection.
The source hash journal is *not* a substitute for the crawler's source
custody evidence or a strong signed transparency receipt.

### Change history for this PR (2026-10-12 UTC)

1. Maternal Tamagotchi lifecycle and exactly three eggs
   **(improved: stable, replay-proof source completion)**.
2. Explicit source inventory sealing
   **(improved: partial or paginated inventory cannot trigger early brood)**.
3. Role-specialized hatchling growth and idle resource gate
   **(improved: distinct article/video/update work, no progress during active use)**.
4. Cross-sibling deduplication and chronological revision fencing
   **(improved: retries and metadata-only scans cannot multiply growth)**.
5. Digest-chained change history and parenthesized improvement notes
   **(improved: attributable, chronological, owner-scoped progress)**.
6. Canonical evidence/human-review adapter with revocation revalidation
   **(improved: gameplay cannot replace real crawler approval authority)**.
7. Authenticated read-only Academy projection and selectable family nest
   **(improved: visible child roles, timestamps and explanation of limits)**.
8. Python and frontend regression additions
   **(improved: tamper, owner, duplicate, idle, consent, source-seal coverage)**.

**Not release-complete:** the host's genuine crawler session, production idle
scheduler, media adapter, explicit opt-in and metering, exact-head CI,
device/browser acceptance, DB backup/restore and production release signing
still need independent integration proof. A queued/skipped check is not a pass.


## Almanakk, Wiki, HOAG: confirmed terminology and review ladder

**Terminology decision (2026-10-12 UTC):** No explicit repository or
Dragon-product rename was authorized in prior user instructions.
Keep `Skeleton`, `Dragon` and the companion family; present
`Almanakk` (graded knowledge), `Wiki` (adversarial fact verifier),
and `HOAG/Jeeves` (user-facing knowledge/LLM layer) as system names.
The three child dragon display names Ember, Flicker, and Scout are
currently UI labels, **not** hardcoded storage identities. The durable
role IDs remain `article`, `video`, and `monitor`.

**Implemented in this PR:**

- `DragonAlmanakkLane.projection` reads actual revisions from the Dragon
  research ledger without persisting a fake separate acquisition source
  (improved: same source identity across parent and all three children).
- `DragonFamilyCustodyBridge.almanakk(...)` builds the owner-locked review
  lane on the shared crawler/practice DB
  (improved: no cross-tenant shadow permission confusion).
- `wiki_review` requires an independent Wiki validator receipt, at least
  two independent corroborating groups, and source-rights clearance;
  every revision is checked against current canonical human review
  (improved: disputed and legally restricted source material stays pending).
- `sandbox_review` requires a holdout-evaluator receipt, 30+ independent
  cases, positive measured quality delta and **zero critical regressions**
  (improved: no promotion for restatements, duplicates or regressions).
- `authorize_weight_handoff` requires a separately signed authority.
  It returns a deterministic handoff *intent*, not changes to underlying
  model weights. The exact signed receipt is replay-fenced
  (improved: no phantom weight-approval receipts).
- Source revisions invalidate prior stage eligibility; the earlier
  evaluation remains audit history but is not current evidence
  (improved: update-aware, reversible review decisions).
- The authenticated companion exposes the measured, read-only counts in
  `DragonFamilyNest` alongside their UTC source history
  (improved: players can see what the dragons actually learned).

### Acceptance and incomplete integrations

1. Wire trusted canonical crawl and video producer calls directly into the
   host's recorded source-acquisition events, including cancellation,
   publisher rules, source permissions, deadlines and actual hardware
   capacity. The sidecar cannot autonomously download, transcribe, or
   approve sources.
2. Wire a real authorized idle scheduler with current user/activity
   signals, prioritizing foreground UX; per-child batch caps and
   role-separated callbacks exist, but service deployment is not yet proof.
3. Use the actual Wiki, shadow sandbox and signed-model promoter
   verification services as the three evaluator callbacks; never
   substitute UI claims, simple digests, or permissive test lambdas.
4. Prove database migrations, backup/restore and UTC audit replay,
   exact-head Dragon Python + frontend, full Webcrawler, App Assembly,
   and all inherited build gates. No signed release while these fail.
5. The product game builder must only act on verified knowledge through
   existing rights checks. A shadow handoff cannot bypass copyright,
   licensing, human review, or anti-plagiarism controls.

**Engineering report, 2026-10-12 UTC:** Family + Almanakk + Wiki/shadow
source-projection and tests are committed to a draft PR. Release
qualification is pending; no production deployment or model-weight
change should be inferred from this status.


## Durable idle workers and real-capture integration (2026-10-12 UTC)

Production-focused next milestone implementation:
`dragon_family_idle_coordinator.py` owns a persisted, bounded owner-specific
work lease and `dragon_family_idle_integration.py` connects all three roles
to the **existing** custody and verified-evidence bridge. Neither module
downloads anything, starts a daemon, invents review decisions, or alters
AI weights; the authenticated host must supply trusted, cancelable adapters.

```python
from skeleton.ai.webcrawler.dragon_family_idle_integration import (
    DragonIdleAcquisitionService, AcquiredArticle, AcquiredVideo
)
from skeleton.ai.webcrawler.dragon_family_custody_bridge import (
    DragonFamilyCustodyBridge
)

bridge = DragonFamilyCustodyBridge(canonical_crawler_db, current_authenticated_owner)
service = DragonIdleAcquisitionService(bridge)

# Each capture callback is a separately authorized *existing crawler/media
# adapter*, returning canonical reviewed bytes + source metadata, or None for
# no new data. Network policy, video rights, timeouts and host budgets are the
# adapter's responsibility; the source can never come from raw UI parameters.
result = service.run_once(
    authorized=True,
    idle_state=host_authenticated_device_and_job_idle_state,
    article_capture=host_capture_reviewed_article,
    video_capture=host_capture_authorized_video,
    monitor_capture=host_capture_reviewed_source_revision,
    task_topics=("game_engine",),
    adjacent_topics=("physics", "game_ai"),
)
```

The host must:
- Use a confirmed five-minute idle threshold (or stricter), opt-in research,
  zero busy jobs and available resources, and **recheck after every fetch**.
- Authenticate the owner at the host boundary; `DragonFamilyCustodyBridge`
  binds family, Almanakk and idle coordinator to the same owner.
- Return `AcquiredArticle` for articles and `AcquiredVideo` for videos;
  Scout may use either, but not an unverified URL or arbitrary approval hash.
- Observe host/bandwidth/robots/redirect/SSRF/license/copyright restrictions,
  per-source timeouts shorter than the coordinator lease, and the existing
  reviewed-source evidence chain. This module intentionally cannot enforce
  live DNS/HTTP policies because it does **not** fetch.
- Stop launching new ticks as soon as device activity, foreground work,
  memory/network capacity, or consent state changes.

### Scheduler behavior and measurable evidence

| Condition | Coordinator action |
|---|---|
| Parent not yet adult | No hatchling tasks |
| User active / consent expired | No dispatch; if activity resumes mid-capture, discard result |
| Fresh eligible article | Ember attempts a registered article with exact source identity |
| New licensed video material | Flicker attempts a time-coded, approved media capture |
| Previously acquired source due for revision | Scout checks old source for changed content |
| Same source selected by two hatchlings | Only one role may dispatch that source in a tick |
| Same content digest revisited | No XP, no new accepted knowledge; schedule cooldown |
| Network/custody/adapter failure | No XP; persist bounded retry information |
| Worker lease expired or lost | Refuse admission; next trusted idle tick may reclaim source |
| Large source inventory | Persist a rotating keyset scan cursor; no permanent first-page starvation |

The source catalog keyset scan has bounded per-tick work, per-worker leases
and fair specialist dispatch. The scheduler does not infer whether the user's
machine is idle: the host must supply authoritative signals. No source grants,
activity permissions, or outside-provider credentials are stored in the UI.

A separate SQLite append-only idle-attempt journal stores UTC time, role,
source ID, action, parenthesized explanation, previous SHA-256 event hash and
current hash. The authenticated `read_idle_family_health` projection checks
the complete journal chain and shows bounded recent entries. Examples:

- `2026-10-12T15:32:01.000Z` — article — changed
  `(improved: independently reviewed new source content acquired)`
- `2026-10-12T15:38:09.000Z` — monitor — unchanged
  `(checked: no novel verified source information)`
- `2026-10-12T15:45:00.000Z` — video — paused
  `(paused: user activity, consent, capacity, or lease fence)`

**These are format examples, not actual crawl events.** A source reviewer
may additionally record a specific improvement note, but the idle coordinator
cannot claim a model-quality gain without an approved holdout evaluation.

### Added targeted validation

```bash
pytest -q tests/test_ai_webcrawler_dragon_family_idle_coordinator.py
pytest -q tests/test_ai_webcrawler_dragon_family_custody_bridge.py
pytest -q tests/test_ai_webcrawler_dragon_family_almanakk.py
cd frontend && yarn test:dragon-companion && yarn typecheck
```

New tests exercise all three specialist roles, true idle/foreground gates,
rejected source rewrites, typed real-capture integration, repeated content,
fair role isolation, callback interruption, retry/cooldown, rotating scans
into later source pages, owner isolation, audit timestamps and corruption
detection.

**Release remains gated** on actual installed host adapters, real device
state signals, independent Wiki/holdout evaluators, tenant-isolated storage,
deployment-specific resource budgets and passing exact-head gates.


## Host-consented idle research (2026-10-12 UTC)

The next milestone adds a **durable opt-in control** in
`skeleton/ai/webcrawler/dragon_family_idle_host.py`, built on the existing
`DragonConsentLedger` and canonical `DragonFamilyCustodyBridge`. It does
not make the remote web backend an authoritative observer of a user's device.

1. The host authenticates the user's tenant and issues the existing Dragon
   consent receipt for BOTH capture and analysis, with `scope_digest` from
   `idle_consent_scope(owner,task_topics,adjacent_topics)` and a finite
   expiry no longer than 30 days. Only the existing ConsentLedger can mint
   that receipt; this module cannot invent user approval.
2. The host creates `DragonIdleHostControl(bridge)`, then calls
   `activate(consent_id=...,task_topics=...,adjacent_topics=...,at=...,authorized=True)`.
   Consent, source scope and session generation are persisted in the canonical
   SQLite database. Opt-in is denied if the receipt is absent, expired,
   revoked or for a different task scope.
3. From its **existing OS/native app idle event loop**, the host invokes
   `tick(authorized=True,host_idle_state=...,article_capture=...,
   video_capture=...,monitor_capture=...)`. The idle callback must report
   accurate wall time, last local interaction, foreground work, app jobs,
   consent, and resource availability. An HTTP client is **not** a trusted
   local idle detector, and the backend does not silently schedule ticks.
4. The source/role budget is reserved atomically **within the same SQLite
   transaction as the worker lease**, not on optimistic dispatch count.
   Defaults: no more than 48 attempts/day and 20 per role/day. The host may
   configure stricter limits. Separate cooldowns and failed-attempt backoff
   apply in the specialist coordinator.
5. On every host observation, session generation, consent scope, revocation
   and expiry are revalidated. A mid-capture opt-out or consent revocation
   discards the result; no game growth or Almanakk promotion is allowed.
   `stop(at=...,authorized=True)` fences the active session generation
   without revoking consent used by unrelated application workflows.
6. `read_idle_host_projection` is a **read-only** authenticated status
   projection with no schema creation, no worker start and no client-mintable
   consent. The companion displays opt-in, daily attempts and next eligible
   tick, but its `host_idle_now` is deliberately `null`. A server status
   screen cannot know whether a local computer is currently idle.

A minimal host-facing example after a separately consented, policy-approved
source catalog and reviewer have already been configured:

```python
from skeleton.ai.webcrawler.dragon_family_idle_host import (
    DragonIdleHostControl, idle_consent_scope,
)
# Only run inside the authenticated native/desktop host boundary:
scope = idle_consent_scope(owner, ("game_engine",), ("physics",))
# The existing DragonConsentLedger issues an explicit, revocable capture+
# analysis receipt with scope and deadline after user authorization.
host = DragonIdleHostControl(owner_locked_custody_bridge)
host.activate(
    consent_id=existing_consent_receipt.consent_id,
    task_topics=("game_engine",), adjacent_topics=("physics",),
    at=host_utc_now, authorized=True,
)
# Each callback must provide truly reviewed source evidence, or None.
summary = host.tick(
    authorized=True,
    host_idle_state=read_trusted_os_activity,
    article_capture=capture_consented_reviewed_article,
    video_capture=capture_licensed_timecoded_video,
    monitor_capture=check_and_review_changed_source,
)
# Foreground resumption, sign-out or consent withdrawal:
host.stop(at=host_utc_now, authorized=True)
```

Test coverage in `tests/test_ai_webcrawler_dragon_family_idle_host.py`
includes scoped opt-in, deny-before-activation, consent expiry/revocation,
mid-capture opt-out, foreground interruption, one-time growth, atomic daily
role quotas, rate throttling, read-only status and SQLite restart recovery.

### Production release boundary

This milestone completes the host **control interface**, not OS detection or
an installed scheduler. Deployment must still connect independently trusted
Windows/macOS/Linux local activity probes, cancellable source adapters with
robots/SSRF/terms/rights checks, independent Wiki/holdout evaluators,
operator stop controls, and a complete passing exact-head release suite.
No code introduced here trains or mutates AI model weights; sandbox
`shadow_validated` and signed `weight_handoff` remain distinct stages.


## Crash recovery, source-global leases and disputed-source research (2026-10-12 UTC)

**Shipped as branch code, not as a production OS service.** This milestone
turns the previous on-demand idle coordinator into an auditable crash/restart
worker and connects the independent Mother Dragon Glean Matrix to the sibling
research queue. The trust boundary remains host-owned.

### Expired-work reconciliation

`DragonIdleCoordinator.reconcile_expired_leases(owner,authorized=True,
at=trusted_now,max_recover=100)` examines **only** expired, still-running
owner-scoped leases. Within a single SQLite write transaction it:
- invalidates the old token so an orphaned process cannot commit its capture;
- records a new `recovered` outcome (no XP), with source ID, UTC time,
  parenthesized note, and append-only hash-chain evidence;
- imposes bounded retry backoff before any fresh attempt and does not
  refund already-debited daily quota;
- limits work to at most 100 leases by default (up to 1,000 by policy).

The host-invoked `run_once` automatically performs a bounded reconciliation
after confirming an authenticated idle/consent window. It does not reconcile
or resume during foreground activity. A valid resumed tick is still required
to fetch *new*, independently approved source bytes.

### Multi-process source fence and consent commit fence

A source cannot hold overlapping active leases for Ember, Flicker and Scout
even on separate worker processes using the same durable SQLite database.
The per-role queue, source-global lease check and reservation budget operate
under one SQLite writer lock; a competing role is deferred rather than
simultaneously re-crawling a source in another worker.

Immediately before inserting an improved source reading, the trusted host's
`commit_gate` is executed **inside the same write transaction** as the
canonical `DragonFamily.digest_idle` source-lease check. The gate rechecks
the session generation, current scope and revocable `DragonConsentLedger`
approval. Consent revoked between the last post-fetch idle poll and the
final write cannot be accepted as hatchling growth.

A lost observer cannot be queried again simply to write a cancellation
receipt. Interrupted work is recorded at the last successfully authenticated
host time, not silently converted into successful evidence.

### Research-priority synergy

`DragonGleanMatrix.research_briefs` composes read-only, owner-locked,
source-reviewed contradiction findings. Only `revisit_conflicting_sources`
briefs can elevate Scout's priority for an already registered source ID.
The normal research topic and adjacent-topic filters, original source
catalog, rights/transport gates, source-global lease and task quota remain
in force. A Wiki review request is never taken as permission to autonomously
crawl or promote weights.

Missing Almanakk tables now explicitly fail the Glean Matrix's Wiki gate:
a missing review stage means **unverified**, never permission or an
uncaught SQLite missing-table exception. Source review and independent claim
verification stay distinct from sandbox/holdout and signed weight handoff.

### Regression and integration checklist

```bash
python -m pytest -q --noconftest \
  tests/test_ai_webcrawler_dragon_family_idle_coordinator.py \
  tests/test_ai_webcrawler_dragon_family_idle_host.py \
  tests/test_ai_webcrawler_dragon_family_glean_matrix.py \
  tests/test_ai_webcrawler_dragon_family_custody_bridge.py
cd frontend && yarn test:dragon-companion && yarn typecheck
```

New cases reject multi-role lease races, stale tokens, unapproved or
non-inventory review priorities, revocation in the commit window, false
foreground recovery, audit tampering and missing-Almanakk promotion.
Passing a focused local or GitHub subset **does not** clear existing
whole-repository Webcrawler/Dragon/App Assembly failures or install a
native host. Actual operating system idle probes, cancellable network
adapters and independently graded shadow evaluators remain prerequisites
to declaring a functioning production crawler companion.


### Explicit operator opt-out fencing

`DragonIdleHostControl.stop` now revokes the active session generation
**and** immediately fences the owner's currently running source tokens with
`DragonIdleCoordinator.fence_owner_leases`. It records a single authenticated
UTC `(paused: …)` event per fenced source and imposes the transient backoff.
No active worker can credit its result afterward; the policy-bound native
network adapter must also cancel its own in-flight requests. Repeating stop
does not invent new events.

A source-level cooldown now applies to **all** three hatchlings: a source
just inspected by Ember cannot be immediately re-fetched by Scout merely
because Scout has a separate role queue. This conserves bandwidth, reduces
repetitive acquisition, and preserves the game's novelty requirement.


## Real local-input observer capability (2026-10-12 UTC)

The optional host adapter `dragon_family_native_idle.py` can now sample
**local OS input inactivity** rather than requiring a fabricated browser
idle number. It does not independently start a worker or observe the user's
screen content.

| Platform | Source of recent input | Safety rule |
|---|---|---|
| Windows desktop | Native `GetLastInputInfo` and `GetTickCount64` | Reject API failures and stale/out-of-range results |
| macOS desktop | Quartz `CGEventSourceSecondsSinceLastEventType` | Reject unavailable permission/library/invalid readings |
| Linux X11 | `XScreenSaverQueryInfo` on an accessible `DISPLAY` | Reject missing/unavailable X11 library/display |
| Linux Wayland | No trusted universal compositor signal available here | **Deny** rather than accept XWayland-only activity |
| Unknown/headless/remote | No trustworthy native input source | **Deny** by default |

The authenticated native host must additionally provide
`NativeHostSignals(session_unlocked=...,user_foreground_active=...,
running_foreground_jobs=...,resources_available=...,
research_consent_active=...)`. It must derive all fields from trusted local
session/job/consent infrastructure, never browser-submitted booleans. Locked
or unconfirmed sessions refuse activity admission. A stale/slow native
measurement, clock regression, missing library, untrusted signal or more
than one day of unconfirmed input time refuses activity admission.

A native host's existing event loop can now run:

```python
from skeleton.ai.webcrawler.dragon_family_native_idle import (
    NativeDragonIdleProbe, NativeHostSignals,
)

probe = NativeDragonIdleProbe(
    host_signals=read_authoritative_local_jobs_consent_session_and_resources,
)
# Only on a trusted, authenticated OS host after explicit scope-bound opt-in:
host.tick(
    authorized=True,
    host_idle_state=probe.observe,
    article_capture=approved_article_fetch_and_review,
    video_capture=licensed_video_capture_and_review,
    monitor_capture=consented_revision_review,
)
```

The source capture callbacks remain necessary and are intentionally NOT
invented in this adapter. They must enforce SSRF protection, redirects and
public-host DNS checks, robots/terms/license/DRM rights, bandwidth and
deadline restrictions, independent human review, and revocable authorization.
`NativeDragonIdleProbe` samples only input duration and boolean host state;
it does not record key presses, typed text, screen content or user-window titles.

```bash
python -m pytest -q --noconftest tests/test_ai_webcrawler_dragon_family_native_idle.py
```

This still does **not** install a daemon, connect an OS idle-event scheduler
in production, or represent legal/rights approval for arbitrary sources.
The host is responsible for how and when it invokes the bounded tick.


## Three linked milestones: atomic growth, source quarantine and adaptive recrawls (2026-10-12 UTC)

The following implementations are code committed to the feature branch; they
must still pass exact-head CI and do NOT imply a native app or autonomous
crawler is installed on an end-user machine.

### 1. Transactionally complete the entire accepted acquisition

`DragonFamily.digest_idle` accepts a trusted `completion_hook`. Under its
existing owner-scoped SQLite `BEGIN IMMEDIATE` transaction, the new source
reading, growth event, source lease terminal state, due time, and SHA-256
idle-attempt audit are accepted **together**. Duplicate reviewed revisions
complete as unchanged without XP. An injected audit write failure reverses
the new source reading and event; the coordinator separately records the
failed attempt on its already-reserved lease.

Only a host-attested, authorized, unexpired source lease may call the
completion hook. The implementation preserves direct `digest_idle` callers
that do not supply one.

### 2. Typed crawler denials and independent source unblocking

`dragon_family_idle_failures.py` defines policy-safe outcomes, not arbitrary
untrusted exception text:

| Host outcome | What the hatchlings do |
| --- | --- |
| Approved genuinely changed capture | Atomically record verified reading and growth |
| Identical verified content | Record unchanged; no XP |
| Network/transient failure | Bounded exponential retry |
| HTTP 429 with valid 60-86400 second Retry-After | Respect the delay and give no XP |
| Robots/rights/SSRF/media grant denied | Persist `policy_blocked`, quarantine that source across ALL specialist roles, no XP |
| Later authorized re-review | `clear_source_policy_block` requires an independent host rights callback to return true before any new lease |

A quota-exhausted or denied source cannot exploit a second hatchling to
evade the owner/source-wide policy gate. Raw source headers, credentials,
host exception messages, or user-submitted permissions are never written
into the companion journal. The Academy's authenticated idle status
provides blocked/rate-limited counts, and the nest displays review
warnings without granting any UI write permission.

### 3. Evidence-derived adaptive recrawl priorities

`dragon_family_recrawl_planner.py` reuses the canonical mission scheduler's
`plan_adaptive_recrawls`. It considers only source revisions previously
admitted to the canonical family ledger, current human review validity,
true recorded attempts, source topics and adjacent research relevance.
An observed revision-to-attempt ratio is explicitly an **uncalibrated
priority heuristic**, not a learned or empirically validated probability.
The plan is read-only; it creates no new source grants, timers or network
requests.

During an authenticated native idle host tick, due reviewed sources and
the Mother's independently corroborated Glean Matrix dispute briefs can
elevate Scout's work ordering. Sources outside the approved catalog,
unrelated task topics, revoked reviews, or policy-blocked leases remain
unavailable. The normal resource, consent, license, host and retry gates
are still enforced by the native host and trusted adapters.

### New acceptance tests

```bash
PYTHONPATH=. python -m pytest -q --noconftest \
  tests/test_ai_webcrawler_dragon_family_idle_coordinator.py \
  tests/test_ai_webcrawler_dragon_family_idle_host.py \
  tests/test_ai_webcrawler_dragon_family_recrawl_planner.py \
  tests/test_ai_webcrawler_dragon_family_custody_bridge.py
cd frontend && yarn test:dragon-companion && yarn typecheck
```

The tests verify: all-or-nothing evidence + journal commit; rollback on
injected audit failure; no XP on duplicate or denied source; source-global
policy-blocked quarantine and independently authorized release; bounded
HTTP 429 Retry-After; no fabricated future recrawl recommendations;
rights revocation; and no network authorization from read-only recrawl
advice.

Unresolved prior system-level Dragon, Webcrawler, App Assembly and release
gates must still be repaired and verified before changing the PR from draft
or releasing any installed research automation.
