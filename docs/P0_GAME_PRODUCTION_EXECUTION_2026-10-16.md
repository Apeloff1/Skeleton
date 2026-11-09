# Full Skeleton P0 game-production execution plan and live evidence boundary

Date: 2026-10-16. Scope: `Apeloff1/Skeleton`, the **one integrated app**, not
a small example game. Historical conversation requirements are reconciled
against current code and `GAME_PRODUCTION_GAP_ATLAS_2026-10-16.md`.

**Overall P0 status: NOT COMPLETE.** The 20 baseline P0 areas are
non-compensable and require independent, release-bound evidence.
Code presence, 43 typed editor interfaces, claimed expert ratings,
catalogued emulators, installed tools and test fixtures cannot qualify
consumer-level experience, rights clearance or native platform release.

## Recovered whole-product user requirements

- Jeeves is the in-app game-production conversation and governed proposer,
  attached to real project/editor/runtime state; the independent challenger
  reviews findings. The Dragon crawler/research companion must only promote
  verified, rights-cleared, attributable evidence through explicit approval
  and independent evaluation. A closed unmerged Dragon PR is **not** a live
  feature by virtue of having a prior test report.
- Real original games, not merely sample games: story and world, character
  and NPC identity, quests, causes and choices, interactive cutscenes,
  branching endings, executable stages, physics/controls, visuals, music,
  assets, accessibility and save/reopen/recovery.
- The long-form **100 chapters / 1,000 acts / 9,999 scenes** standard applies
  when the author selects that scale. Canon voice, cast, lore, palettes,
  costumes, causal anchors and original source must survive all expansion.
  Scale targets are authored content and acceptance obligations, not counts
  that a schema alone fulfils.
- Academy, Galaxy Studio, Snowball Flow and Jeeves cockpit/settings must
  expose the same underlying project capabilities, including real model
  control, undo and operator approvals, not parallel noninteroperable UIs.
- Real legal original creation, historical-console/era-correct assets,
  2D/2.5D/2.9D/3D camera and media support, actual engine and controller
  operation, comparison of up to 30 games/10 concurrent sessions under
  available resources, and reviewable captured training evidence.
- Project work and recording must not have an arbitrary lifetime/attempt
  deadline. Every *operation* must remain resource-admitted, cancellable,
  resumable and traceable; physical compute, model budgets, disk and context
  cannot be infinite. Learning does not silently alter production weights.
- Creative literary/film/gameplay parity must be evaluated against real
  works with rights-sensitive independent blind reviewers, not developer
  self-scores. At least two independently qualified disciplines are required.
- No release, training, P0 closure, or model improvement is claimed from
  an unexecuted plan, synthetic provider, source-only replay, or queued CI.

## Additional whole-application P0 lanes (not included in the game 20)

The original masterplan has **separate** binding requirements. The 20-area
game atlas is only one P0 register and does not retire these gates:

- **AI CHAT-01..07 and CHAT-10:** real in-app chat; actual local checkpoint
  load/generate/stop; persistent recoverable branched conversations;
  streaming, cancellation/retry and reconnection; Jeeves understands the
  active project and editor; reviewable approve/reject/undo source mutation;
  cited rights-governed retrieval; installed-app acceptance.
- **Assembly and end-to-end:** full TypeScript compile, real checkpoint
  inference, complete stub/truncation inventory, genuine first-install
  operating state and playable whole-game run. Queued/skipped GitHub
  actions are not passing evidence.
- **Unified UI:** Academy, Galaxy Studio, Snowball Flow, Jeeves cockpit
  and settings must surface the same authoritative project and model
  capabilities rather than another parallel UI stack.
- **Dragon governance/reproducibility:** the historical 22-gate program
  and P0 reproducibility requirements continue independently of the
  game atlas. Research acquisition flows via Dragon → reviewed almanac →
  independent Wiki/adversarial check → shadow candidates → heldout test →
  explicit approved promotion → rollback. Never promote unverified raw
  crawler assets, training data or scraped third-party intellectual property.
- **Native cross-era requirements:** the author-selected Game Boy,
  Nintendo/Sega, PlayStation/Xbox, DOS/PC and other era targets require
  actual legal original runtime binaries and appropriate controllers,
  not just platform names and reference raster previews.

The `p0-acceptance` report now exposes these extra mandatory lanes as
`additional_noncompensable_app_p0`, clearly separate from the twenty
game-specific release gates. No one can assert full application P0 from
a 20/20 game-domain score alone.

Current GitHub facts checked during this workpass: the advanced game
builder PR #3642 is merged, the Dragon PR #3605 is **closed without
merge**, and the continuing integrated Jeeves/game studio PR #4068 is
still open. Other Dragon modules may exist on `main`; this fact
alone does not prove the Dragon pipeline or its 22 gates functional.

## P0 baseline — authoritative 20 required release gates

Run `python -m skeleton dev game jeeves p0-acceptance --project ./game`
to return the 20 non-compensable gate IDs `P0-01..P0-20` defined by
`skeleton/developer/jeeves_game_p0_acceptance.py`. This report tries to
validate present GameForge source receipts and source-linked story/quest
dossiers, but **never marks a release gate qualified without independent
consumer/game/human/hardware evidence**.

The 20 gates group as:

| Gate IDs | Required product evidence |
| --- | --- |
| 01-03 | Conversation-to-install product, real Jeeves model, complete canonical story |
| 04-08 | Independent novel/film quality, causal arcs, character arcs and voiced dialogue |
| 09-12 | Material player agency, authored scene coverage, book-to-game execution, true world memory |
| 13-14 | Independent reviewer/challenger and actual protected creator/IP approvals |
| 15-17 | Complete quest arcs, editor-to-runtime integration and native full game playthrough |
| 18-20 | Target-native rendering, performed adaptive audio, signed/installable release |

Each gate has its own technical evidence and independent release criteria.
No aggregate average or high-scoring P1/P2 feature can substitute for a
single unresolved P0 gate.

## Implemented this pass — real but narrowly qualified P0 runtime work

1. `skeleton/ai/game_builder/quest_campaign_completion.py` executes
   every stage of each authored DirectorWorld quest through the real
   `available_director_actions` and `director_step` contract. It uses
   scene graph travel, actual objective affordances, optional objectives,
   quest prerequisites and recorded consequences. An unsolvable stage or
   dependency cycle fails rather than manufacturing an ending.
2. The original world can be run through multiple *entire* choices from
   genesis; branch qualification requires different observed
   `(approach, consequence)` pairs on actual common quest stages.
   The independently re-executed segmented trace preserves state, inventory,
   quest progress and source outcomes.
3. `skeleton/ai/game_builder/quest_campaign_save.py` offers real
   **Director logic-state** create-only campaign saves and reopen by
   re-executing the exact legal action history, including tamper,
   foreign-world, duplicate and unsafe-path rejection.
   No direct arbitrary DirectorState deserialization is trusted.
4. `jeeves direction-campaign --source design/director_campaign_source.json
   --passes 2` executes and compares two complete world routes against an
   explicitly reviewed source blueprint. The report offers actual segment
   records for subsequent human-authored, signed story binding.
   It never automatically invents matches between prose and player action.
5. `jeeves p0-acceptance` surfaces honest progress plus every currently
   unqualified original game-release requirement. CI has regression coverage
   for these functions alongside existing canon, playthrough and authoring
   checks.

The CLI campaign source is exact-schema local JSON:

```json
{
  "schema": "skeleton.jeeves.director_campaign_source.v1",
  "director_world": {"schema": "skeleton.game_builder.director_world.v1"},
  "author_review_acknowledged": true
}
```

The nested world above is an illustrative **placeholder**, not runnable:
supply the complete authored `DirectorWorld.payload()` and a matching
current GameForge project ID. `--passes` specifies 1..8 fully replayed
choices, rather than synthetic scoring or independent human reviews.

### Operator save and reopen, without native-release claims

```bash
python -m skeleton dev game jeeves direction-campaign --project ./original-game --source design/director_campaign_source.json --passes 2 --output original_campaign
python -m skeleton dev game jeeves direction-campaign-reopen --project ./original-game --source design/director_campaign_source.json --output original_campaign_0
python -m skeleton dev game jeeves p0-acceptance --project ./original-game
```

The first command executes both routes, then writes each route's **actual
replayed action history** as create-only JSON under
`design/campaign_saves/original_campaign_0.json` and
`original_campaign_1.json`. Existing save names cannot be overwritten.
The second command recompiles the exact approved world and re-executes
every legal action from genesis to reconstruct the selected DirectorState;
it rejects forged actions, stale/foreign world IDs and altered checkpoint
receipts. The third command displays the separately blocked release gates.
This proves Director **logic-state save/reopen**, not installed Godot save
migration or consumer native-state recovery.

The resulting `replays_for_signed_story_binding` can be incorporated
into an approved StoryCanon / `direction-gameplay` dossier with exact
author-controlled `source_anchor` / quest / stage / approach / consequence.
That second layer is mandatory for narrative closure, and full running game
art/audio/render/export and review evidence is still separate.

## P0 remaining implementation and acceptance program

**P0-A: Real game journey** — Connect user Jeeves chat to project creation,
authorized source mutation and editor controls. Generate a complete
original Godot project, execute all chosen narrative branches in its
actual exported runtime, perform real save/load/install/update/rollback
and record independent first-install user acceptance.

**P0-B: Complete exceptional original authored narrative** — Produce an
approved 100-chapter-scale corpus if selected by the creator. Maintain
signed full-history continuity and source/shot/action payoffs; schedule real
independent novel, film and gameplay reviewer evidence with disagreements
visible, original timed performances and protected author approval.

**P0-C: Same-project production integration** — Source-identified cast,
original visual/audio assets, camera/animation/cutscenes, scenes,
NPC states, editor controls, compiled presentation and exercised input
routes must share canonical project identity and reversible transactions.
Academy/Galaxy Studio/Snowball/Jeeves must display that same run.

**P0 independent acceptance** — Full real-game native playthroughs
at all claimed release hardware targets; measured controls, audio,
camera/render performance, accessibility, rights and export/first-install
qualification; security/provenance/CI green at exact merged head.
Only after all 20 gate receipts are truly independent, valid and current
could the project be marked `P0_complete`.

## Current blockers and PR integration

- GameForge is source/build/boot-oriented; source ZIP is not a native signed
  consumer game. The new Director campaign is executable **Python game
  logic**, not a full Godot game engine playthrough.
- The underlying GameForge world has limits on simultaneously allocated
  scenes/quests; source chapter count does not prove all scenes are compiled
  or alive at once. A streaming/partitioned game runtime is still needed
  for very large projects.
- Real model checkpoint evaluation/training, Dragon-to-Jeeves promotions,
  adjudicated legal rights and independent studio review are not installed
  release evidence from this workpass.
- The working code is currently in the dedicated game-development PR.
  Merge only after exact-head CI and reconciliation; no bypass or fabricated
  QA. `docs/GAME_PRODUCTION_GAP_ATLAS_2026-10-16.md` remains the 65-area
  source-qualified gap catalogue (P0, P1, P2).
