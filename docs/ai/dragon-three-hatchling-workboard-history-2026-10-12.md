# Dragon companion — three-hatchling mission board and audited family history
Authored: 2026-10-12 UTC | PR #3605 | Branch feat/dragon-wisdom-review-20261010

## Milestone A: Actual three-child research mission board

The mother/companion interface now includes DragonResearchWorkboard, a deterministic, tenant-bound, non-executing projection of canonical article, video and updates custody. It uses the registered source picker, therefore never accepts arbitrary URLs or a user-provided database path, never advertises blocked source jobs, and never fetches a site. Each selected article contributes one article mission and one update mission; a registered video source contributes one transcript mission. Exactly three roles are recognized.

Article actions distinguish missing approved capture from exact-source text awaiting independent review. Video actions distinguish a missing authorized transcript from a staged transcript awaiting independent review. Update actions distinguish too few revisions, an identical reobservation, a genuine changed revision awaiting idle analysis, a staged delta awaiting Wiki review, and an independently detected superseded revision. The latter is an explicitly recognized stale-revision exception; any other history integrity failure still aborts the request.

Each mission includes its actual source ID, source kind, host, concise next-step description, relevant custody digest, recorded UTC observation epoch when available, whether independent authorization is required, whether five-minute idle worker admission is necessary and whether a reviewer must inspect it. The response expressly has workers_started=0, network_requests=0, permissions_granted=0, xp_awarded=0 and training_authorized=false. A recommendation is never a worker ticket.

GET /api/dragon-research/workboard provides authenticated, bounded, owner-scoped pagination and Cache-Control: private, no-store. The React Native Dragon cockpit renders all three lanes and next steps under a dedicated Review all hatchling research work action. It does not request raw article/video quotes. It will not silently execute any suggested action.

## Milestone B: Unified timestamped three-hatchling family change history

DragonFamilyResearchHistory merges three already-authenticated append-only research journals into one bounded timeline. Each event preserves lane, source identity, event digest, source revision sequence, UTC observation epoch, action classification and a parenthesized improvement/change note. The interface includes cryptographic content hashes when applicable, but no raw article or transcript excerpts.

Events come from DragonSourceCaptures._history (real fetched article versions), DragonVideoTranscriptLedger._history (independently attested timecoded transcripts), and DragonSourceDeltaLedger._history (changed source evidence staged by the idle update specialist). Histories are verified by each existing custodian before presentation; the timeline has no additional mutable truth store. Ordering is latest epoch first with deterministic role/sequence/digest tie-breaks, with max 100 visible and an explicit truncated flag and full event counts. Updates and articles can share one source identity; that is not independent corroboration.

GET /api/dragon-research/history is authenticated and read-only; it accepts three validated source IDs and a bounded display limit. The cockpit provides View timestamped hatchling changes and displays observations using ISO UTC timestamps, short custody receipts and no secret text. Unlike the editor-only exact-quote endpoint, this returns metadata only.

## Milestone C: CI execution request on Dragon feature branches

The Dragon AI Verification workflow formerly ran on push only for main; PR #3605's visible runs consisted solely of CodeQL Analyze(actions), not complete pytest or TypeScript checks. The workflow now also matches feat/dragon-* branch pushes, restricted by its existing relevant-file path filters. The Dragon Source Safety compile list now includes both the research workboard and family history modules. The existing specialist tests and authenticated backend suite were extended rather than replaced.

This requests real feature-branch Python, backend and frontend execution when GitHub Actions honors the workflow and runner permissions. It does NOT prove tests passed: exact-head job results must be inspected after the push.

## Adversarial acceptance points

- Three actual roles and no missing hatchling: article, video, updates; each mission derives from owner-scoped canonical evidence.
- No fabrication: same-content revisits cannot become update insight, superseded deltas cannot pass as current, and video missing licenses must stay missing.
- Each history event has verifiable recorded UTC time, role, source ID and integrity digest; no raw copyrighted text leaves via the status/history endpoints.
- Tampered capture history or mismatched tenant causes failure instead of dropping evidence and returning false completion.
- Every API remains read-only on SQLite mode=ro/query_only with per-request snapshot transactions; no crawl, grant, XP or model weights are mutated.
- All new Python and TypeScript changes remain subject to exact-head CI and app integration checks.

2026-10-12 UTC improvement record:
(Added a three-hatchling, task-specific and review-only operations workboard.)
(Surfaced missing authorizations, unchanged revisits and superseded revisions separately.)
(Merged article/video/update evidence events into one timestamped, custody-verified family history.)
(Added feature-branch push validation to request real Dragon Python/frontend gates.)