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
generation at once with `cycles.disable` or `lab.revoke`.

## Required production adapter

There is deliberately **no unauthenticated REST route** that accepts raw
`PromotionDecision` records or arbitrary `owner` parameters. The host
must bind owner identity to the authenticated principal, resolve canonical
promotion and human-approval records server-side, and never accept XP,
skill levels or playtest successes from front-end JSON.

A host providing the Jeeves companion screen may pass `CompanionAcademyInput`:
`progress` is the server-projected `PracticeProgress`, `attempts` comes
from `lab.attempts`, `subscription` from `cycles.status`, and callbacks
perform authenticated actions for `onRunPractice`, `onStopPractice`, and
`onOpenDemo`. Game HTML must be presented in a strongly sandboxed isolated
origin or isolated WebView. Browsers must not reuse application auth cookies
when loading a demo. No callback means the UI only shows an honest
read-only workshop state and does not claim to have run a game.

Connect the canonical crawl-event journal to the companion in a separate
authorized read-only feed; the current Jeeves chat mount supplies conversation
interests, not a live crawler session ID.

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

- Authoritative crawler-event feed into Jeeves, with owner/session identity.
- Authenticated artifact streaming into sandboxed playable demo view.
- True browser/engine smoke and gameplay acceptance receipts, not HTML checks.
- Broaden practice to combat, resource management, UI, camera and cooperative
  games through implemented mechanics rather than dishonest "supported" tags.
- Evidence-driven adaptive challenge selection from actual playtest outcomes,
  with rollback on regressions or uncertain learning.
