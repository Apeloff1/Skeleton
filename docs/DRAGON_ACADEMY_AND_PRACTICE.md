# Dragon Academy: crawler knowledge → practice games → verified progression

The baby-dragon companion has one appearance surface in `frontend/features/Jeeves/companion`
and one governed practice domain in `skeleton/ai/webcrawler`. The practice worker
does not create a separate AI model/runtime, internet crawler, credential
boundary, or source-of-truth. The existing approval and provenance checks
remain authoritative.

## User-facing progression

- Dragon Academy adds four skill meters: research, game design, prototyping,
  verification. These reflect accepted lessons and reviewed demonstrations,
  not character animation, chat messages, total URLs, speculative confidence,
  or requests to "work harder".
- Six evolution ranks and a quest map are unlocked by evidence-backed XP.
  Initial level 1 requires no proof, but no earned XP is shown until the host
  provides a valid `skeleton.ai.dragon.practice_progress.v1` snapshot.
- A scored success requires **a human-reviewed playtest evidence digest**.
  Rendering an HTML document only produces a **built attempt**. A demo can be
  built and then rejected; no mastery XP is awarded for rejected/failed
  attempts. A screenshot or digest alone is not a runtime execution guarantee.
- The visual companion may reveal decorative wings, a scarf and a star aura
  at evolution milestones, but those cosmetics grant no crawler permissions.

## Producer flow (concrete API)

`DragonPracticeLab` is injected with the canonical owner's SQLite connection.
Do not instantiate a new per-request in-memory database in production.
Host code running in the authorized crawler service calls:

```python
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_practice_lab import (
    DragonPracticeLab, ApprovedLesson,
)

# decision is the canonical result of assess_promotion(...), not a user-
# supplied JSON Boolean. human_receipt is the validated approval fingerprint.
lab = DragonPracticeLab(existing_crawler_db)
lesson_id = lab.offer(ApprovedLesson(
    owner=authenticated_owner,
    title=reviewed_lesson_title,
    promotion=decision,
    review_fingerprint=human_receipt,
    observed_mechanics=(Mechanic.MOVEMENT, Mechanic.PHYSICS),
    practice_consent=practice_user_opted_in,
), authorized=caller_can_write_practice, now=trusted_now)

attempts = lab.run_batch(authenticated_owner, authorized=True,
                         consent=live_consent, now=trusted_now, max_demos=2)
# artifact() returns the exact self-contained offline HTML by authenticated
# owner and attempt ID. Serve only with sandboxed CSP, never same-origin unsandboxed.
# After an actual human playtest has an attested digest:
lab.review(authenticated_owner, attempts[0].attempt_id, authorized=True,
           playtested=True, accepted=True, playtest_digest=verified_playtest_sha256)
progress = lab.progress(authenticated_owner, authorized=True)
```

The game design is built from explicit, whitelisted mechanics, reuses
`render_playable_prototype`, and chooses deterministic seed-indexed arena
layouts. Geometry is original; no scraped images, scripts, assets, or game
level maps enter the generated HTML. The micro-prototype currently supports
movement, jumping, physics, exploration and level-design scaffolding; other
mechanics are not silently counted as implemented. This is a **practice
generator**, not an autonomous AAA-game compiler.

## Finite self-practice cadence

`DragonPracticeCycles` composes the Lab, not a new daemon. To make regular
game experiments possible, the existing trusted scheduler may poll
`cycles.pulse(owner, authorized=True, now=trusted_now)`.

A user must explicitly enable a subscription via `cycles.enable` with
`human_approved=True`, a **maximum seven-day expiry**, a bounded number of
ticks, a minimum five-minute interval and no more than four demos per tick.
A day's total attempts are capped by `PracticePolicy.max_demos_per_day`.
A revoked lesson grant, disabled subscription, expired grant, or exhausted
budget produces no new game artifacts. No tick loops catch up missed work,
which avoids resource spikes after downtime.

A subscription is only a *permission state*. If a host does not schedule
calls to `pulse`, no background work occurs. A user can stop future
generation at once with `cycles.disable` or `lab.revoke`. A fresh,
independently validated approved lesson receipt may reactivate a revoked claim
under its original identity without duplicating XP.

## Authenticated host integration

The backend product router at `/api/dragon-academy` is registered by
`backend/core/routes_registry.py`. It uses the existing GameForge login
dependency directly, **without** the developer anonymous-admin fallback.
Every request uses the authenticated user's tenant+email hashed to a stable
owner identifier. No browser-supplied `owner`, `PromotionDecision`, XP,
or review verdict is accepted.

Durable storage must be explicitly configured by the operator:

```bash
export SKL_DRAGON_PRACTICE_DB_PATH=/var/lib/skeleton/dragon/dragon.sqlite3
```

The parent folder must exist and be writable; otherwise the endpoint returns
503 and no in-memory alternate authority is created. Keep the crawler journal
and practice product adapter pointed at **one canonical owner-scoped database**.
On startup, the producer must validate migrations/retention against the main
governance regime.

Current endpoints:

| Method | Path | Meaning |
|---|---|---|
| GET | `/api/dragon-academy/status` | Authenticated XP, queue and cycle snapshot |
| POST | `/api/dragon-academy/practice/run` | Generate 1–4 bounded original demos from approved lessons |
| POST | `/api/dragon-academy/practice/subscribe` | Enable finite recurring practice with explicit approval |
| POST | `/api/dragon-academy/practice/stop` | Stop scheduled cycles, retaining previously approved lessons |
| POST | `/api/dragon-academy/practice/revoke` | Stop cycles and revoke outstanding lesson-practice consent |
| GET | `/api/dragon-academy/practice/{attempt_id}/artifact` | Verified HTML as JSON data only |
| GET | `/api/dragon-academy/crawler/feed` | Owner-scoped crawler journal replay |

**Important:** `DragonSessionProjection.attach(owner,session_id,authorized=True,at=...)`
is an internal producer method only. A trusted crawler must attach its
already-authorized session to the same canonical owner before the feed
shows real progress. Browser clients cannot bind a crawl, approve lessons,
or create crawler events. The feed checks the journal digest chain before
emitting replay events. The linked session can be closed by its producer.

The frontend `useDragonAcademy` checks login, attaches bearer headers to
API calls, validates the authority-owned progress projection, polls real
crawler events on foreground, and verifies HTML SHA-256 before opening
`DragonDemoPlayer`. The WebView is incognito, cannot access files or
cookies, and blocks external navigation; the generated HTML also forbids
network access via CSP. On-screen touch controls supplement keyboard
movement and jumping.

**Scheduler caveat:** subscription enables an approved interval and
remaining-run budget, but **no background worker is created**.
Your trusted runtime scheduler must invoke `DragonPracticeCycles.pulse()`
while the authorization remains current. If it does not, the UI honestly
shows the subscription with no generated attempts. A browser never polls
a run endpoint in a loop to impersonate a background scheduler.

Playtest review remains producer-only and needs independently checked evidence.
A running microgame is not, by itself, proof of a passed real-device test.
The frontend does not have a public success-verdict endpoint and never
mints mastery points.

## Quality targets and constraints

1. Every XP increment is traceable to a unique reviewed claim or a specific
   accepted playtest attempt. Re-reviewing the same claim does not mint XP.
2. Demo history survives process restarts. Owner scoping, artifact digest
   verification, per-day quotas and consent revocation stay enforced.
3. A generated demo is not called "verified playable" until a separate
   actual-device/browser playtest has happened.
4. Reduced-motion OS settings override decorative animation preferences.
5. Test on exact PR head before promotion:
   `pytest -q tests/test_ai_webcrawler_dragon_practice_lab.py tests/test_ai_webcrawler_dragon_practice_cycles.py tests/test_ai_webcrawler_dragon_playable_prototype.py`,
   `cd frontend && yarn test:dragon-companion && yarn typecheck`,
   plus architecture, dependency and UI integration gates.
6. Only after those pass should the operator attach scheduler callbacks and
   authenticated demo delivery. Failure or a skipped gate is not completion.

## Next implementation slice

- Connect the canonical crawler producer's authenticated session startup to
  `DragonSessionProjection.attach` so the prepared feed receives actual events.
- Connect the existing bounded task scheduler to `DragonPracticeCycles.pulse`,
  with resource metering and authoritative job receipts.
- Run true browser/device smoke and gameplay acceptance receipts, not HTML-only
  validation; add a trusted playtest verifier.
- Broaden practice to combat, resource management, UI, camera and cooperative
  games through implemented mechanics rather than dishonest "supported" tags.
- Evidence-driven adaptive challenge selection from actual playtest outcomes,
  with rollback on regressions or uncertain learning.
