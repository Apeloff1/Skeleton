# Jeeves Original Game Studio — Actual Outcome and Source Review Milestones

Date: 2026-10-13. Development branch: \`feat/jeeves-evidence-graph-scale-20261013\`.
This is **source implementation**, not independent app release qualification.

## 1. Verified reference-game outcomes, not hypothetical paths

\`JeevesCampaignOutcomes\` consumes an already human-committed original
campaign and two to twelve distinct player-action override profiles.
Every selected profile is recompiled using the **installed**
\`compile_campaign\` interpreter and the project's actual human-committed
editor-system configuration and authored game scenes.

The report records:

- The action-profile content hash, compiled-game receipt, actual chosen
  branch sequence, final observed ending node/category and reference
  gameplay session count.
- The exact observed branch edges by the canonical deterministic
  predicate/priority resolver, even when two priorities share a target.
- All authored ending nodes/categories and branch edges **not witnessed**
  by the supplied gameplay profiles.
- The current committed campaign source hash and compiler receipt
  fingerprint, so source changes invalidate historical outcome assertions.

A compiler may have several *structurally declared* ending categories
without any supplied action profile that actually reaches them. In that
case the missing outcomes remain explicitly unobserved.

\`GameWorkspace._validate_campaign_outcomes_source\` reruns this entire
operation at proposal and human-commit boundaries. The resulting source
path is \`game/campaigns/<campaign_id>_outcomes.json\`.

## 2. Original game choices joined to character and world canon

\`JeevesNarrativeConsequences\` requires three **committed and current**
source domains: the actual original-game campaign, its outcome portfolio,
and its full-story signed-canon linkage. It reloads the complete original
history through \`load_story_workspace\` and reconciles every scenario route
against real story scene paths and content hashes.

For each observed real game route it records the actually-authored cast
IDs, regions, causal event IDs, event references, and explicit character
status/location/affiliation/outfit transitions found in those scenes.
It computes pairwise differences between *witnessed* event sets for
distinct action profiles. It does not invent missing NPCs, factions,
karma changes, plots or world states.

Crucial distinction: these are **source-authored narrative consequences**
associated with actually run game paths; they are **not** game-engine
mechanics that automatically modify karma, reputation, faction control
or NPC runtime state. That remains a separate unfinished game system.

Commit-time source reconstruction prevents a change to an authored
story, game campaign, original-game outcome or source linkage from silently
preserving a formerly accepted consequence report.

## 3. Complete large-source human review

The original \`JeevesProductionReview.commit\` rejects any truncated
diff. This workpass preserves that policy and adds a usable alternative:

1. \`studio.production.review_manifest\`: reads one exact original source
   proposal, determines the full Unicode-safe unified diff, and creates a
   SHA-bound page inventory.
2. \`studio.production.review_page\`: returns one complete, bounded,
   UTF-8-preserving diff page with its exact content SHA and manifest ID.
3. \`studio.production.commit_pages\`: requires a signed acknowledgement
   for **every** current page, each exact SHA and full-review receipt,
   then invokes the **existing sole canonical GameWorkspace writer**.
   A failed mid-publication operation returns an explicit partial-source
   state and requires manual reconciliation.

Game Studio displays each exact page and demands a separate human
acknowledgement before the next. This does not certify what a person
actually read, but it prevents a silently clipped diff from being accepted
as a full-source review.

## 4. Live project source dependency graph

\`studio.source_graph\` builds a deterministic, source-version-bound graph
from actual current original-project editor settings, advanced authored
scenes, gameplay replays, campaign and ending source, signed story links,
consequence evidence, typed Forge source, and source-only game releases.

It distinguishes **current**, **drifted**, **missing** and **not inspected**
dependency edges; indexes at most 1,400 relevant source nodes and 9,000
edges; and explicitly reports how much of the source tree is omitted by
that budget. It does not represent a static match as evidence a game
actually executed or passed release gates.

## Workflow and assurance boundaries

All new source-writing paths require a real selected current game, explicit
designer authorization, exact optimistic source SHA and the original
\`GameWorkspace.propose\` / human \`GameWorkspace.commit\` acceptance
boundary. All new gameplay assertions are tied to real reference-engine
actions rather than manually supplied claims of victory.

**Still pending independent verification:** repository tests and
regressions, exact-head required CI, Godot native game/device execution,
performance/security review, rights/originality signoff, actual model
quality and enterprise volume promotion. This pass did not run tests.

**Measured separately against canonical source registries:**
- 414/421 masterplan volume implementation statuses marked verified
  = **98.34% metadata complete, 1.66% metadata remaining**.
- 0/421 enterprise-qualified volumes = **0%; 100% remaining**.
- 0/9 AI product capabilities marked complete = **0%; 100% remaining**.
- 17/17 declared app-construction gaps closed = **100% declared closure**.
No evidence-grounded total application completion percentage exists yet.
