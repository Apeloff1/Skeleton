# Human-reviewed original quest content advisories

A typed Jeeves proposal can seed an editable advisory sheet for every authored
quest stage, but it **cannot infer that content is safe**. The proposal starts
unreviewed with no tags. An operator must explicitly review all stages, record
any warnings, and preserve the exact source and initial-session digest leases.

## Authoring and playback

1. Compile a catalog quest and keep its source and initial-session digests.
2. Route \`studio_original_quest_advisories\` through the Jeeves allowlist with
   explicit out-of-band authoring permission. The exact prompt is
   \`prepare editable original quest content advisories for human review\`.
3. Save the typed plan in private JSON. Review each stage, set a summary,
   severity, spoiler level and sorted, unique topics. Supported topics are
   \`violence\`, \`fear\`, \`grief\`, \`flashing\`, \`loud_audio\`,
   \`social_conflict\`, \`isolation\`, \`injury\`, and \`medical\`.
4. Run \`python -m scripts.studio_quest_advisories_cli --project PROJECT
   --expected-source DIGEST --expected-session DIGEST --plan-file PLAN.json\`.
   Use \`--editor-html\` for a CSP-constrained offline editor; \`--publish DIR\`
   and \`--restore DIR\` for no-clobber private custody; \`--handoff\` for
   all-stage reviewed, canonical-ending-eligible builder descriptors.
5. The player-facing \`--check-consent --accept-topic loud_audio\` reports
   currently played and available-stage warnings and whether the player has
   accepted every disclosed topic. It never advances the quest or records a
   global account consent. A later checkpoint requires a fresh evaluation.

## Fail-closed boundaries

Unreviewed stages block advisory handoff and player consent evaluation.
Unknown topics, repeated tags, forged stage IDs, reordered rows, unbounded
text, mismatched severity, stale source leases, unauthorized tools, malformed
private JSON, symlinks and replay drift fail closed. A digest proves internal
replay consistency, not rights, external authorship, clinical classification,
user identity, player safety or release certification. No advisory can
suppress canonical quests or grant a game ending.

Regression fixtures cover source-to-Jeeves proposal, human edits, replay,
consent, CLI, HTML CSP, private custody and adversarial input. They require
canonical test execution and exact-head CI before promotion.
