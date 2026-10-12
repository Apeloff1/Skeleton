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
