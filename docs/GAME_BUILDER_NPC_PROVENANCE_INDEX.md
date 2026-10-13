# Advanced Game Studio — Original NPC Provenance History Index

Date: 2026-10-12, Europe/Oslo. Status: draft pending exact-head CI.
Parent: fast original NPC branch snapshots PR #3692; source game timeline
#3690, chunked streaming #3689 and unified NPC authority #3686.

## Implemented actual-world capability

The Studio can query and compare authentic, original gameplay histories.
It does not invent stories by summarizing unverified NPC statements.

Using a verified original source checkpoint and chosen game turn cursor,
it executes up to twelve different authored player-action futures in the
actual chunked-world runtime, including physical NPC movement, witness
events, dialogue, finite material resources and optionally earned quests.

Each original branch is measured relative to the REAL source world
at the selected cursor: time, player location, physically embodied actor
count, detailed NPC updates, deferred ticks, real NPC steps, firsthand
physical facts and eyewitness counts, source-bound dialogues, paid social
choices, earned quests, supplies, stamina and voluntary endings.

An indexed search can filter five source record categories:
actions, rule-generated causal events, individual real one-tile NPC moves,
physical witnessed facts and all categories. Each record has actual original
turn, branch, previous source authority action-chain head, actor identity
when applicable, and inherited or divergent source distinction.
Direct witness facts also contain original physical event IDs and actual
unobstructed witness source IDs; the engine does not conflate an ordinary
conversation with firsthand event observation.

Search results accept bounded time ranges and exact original actor IDs,
and return stable paginated output. Query limits and offsets are explicit,
so the response cannot silently discard source facts. Full source counts
are included even when a page returns only the first 24 entries.

## Verification and legal source identity

Queries, branch comparisons and page offsets cannot confer world
authority. Every untrusted report is independently reconstructed from
content-addressed reviewed scene/settings source, seed, clock, real actions
and the original source game's full state transitions. Every branch also
passes the existing full from-genesis replay verification.

Changed witnesses, state hashes, resources, result heads, action steps,
page bounds, actor identities or quest outcomes cause exact verification
failure. No internet text, external software, game asset, training corpus
or model-weight promotion is involved.

Source hashes detect data changes; they are not cryptographic identities.
The module does not rank relative stories as objectively better or claim
third-party game skill improvements. It exposes actual choices and measurable
consequences for player and developer interpretation.

## Operator interfaces

Original source:
skeleton/ai/game_builder/advanced_npc_provenance_index.py

Tests:
tests/test_game_builder_npc_provenance_index.py

Offline CLI:
indexed-npc-histories
verify-indexed-npc-histories

Authenticated read-only Studio:
POST /api/indexed-npc-histories
POST /api/indexed-npc-histories-verify

Visual Studio: NPC History Index beside Fast Branch Lab.
Choose record class, optional exact citizen source ID and already selected
original timeline cursor; inspect both measured branch consequences and
the source-provenance records page by page. No source project file mutation.

Exact-head cross-platform CI:
.github/workflows/game-builder-npc-provenance-index.yml
Ubuntu and Windows run actual material source stories, actor and event
search, forged report denial, query pagination and seeded 35x35 histories.

## Dated improvements

2026-10-12 — Indexed actual per-turn NPC movements and source witness facts
(advances from opaque saved-game digests to inspectable physical evidence).

2026-10-12 — Added source-cursor-relative branch metrics with real material
and quest outcomes (not a heuristic that can award fictional achievements).

2026-10-12 — Added bounded kind/time/actor searches and stable pagination
(supports historical scrutiny without unlimited result exposure).

2026-10-12 — Added independent regeneration plus full from-genesis branch
verification (prevents forgery of indexed histories or claimed victories).

2026-10-12 — Added CLI, authenticated Studio index inspector and exact-head
cross-platform CI (actual, replayable end-user tooling).

## Scope boundaries

This is a correctness-first CPU reference index. It rebuilds original
source facts per query and does not claim persistent on-disk database
index acceleration, Godot hardware certification or all game genres.
Future work: durable indexes, browser visualization of large physical
maps, real multi-chunk event subscriptions and native incremental
gameplay. All dependent PRs remain draft and unmerged.
