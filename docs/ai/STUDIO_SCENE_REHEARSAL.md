# Studio A: original scene what-if rehearsal

This vertical compares two operator-authored timing estimates against the same
canonical original quest and NPC scene source. It does not invent scenes,
dialogue, physical travel, elapsed wall time or native engine outcomes.

Run the scene rehearsal CLI with --project, --expected-source, --baseline and
--candidate, supplying strict JSON schedules of scene_ticks,
npc_turnaround_ticks and min_start_ticks. Optionally use --actions and
--expected-session to bind the exact canonical quest replay. The result
contains critical path changes, source-bound dependency edges, and stable
canonical digests. Use --publish-directory for exclusive private persistence,
and --verify-directory for descriptor-relative nofollow restoration and replay.

For a playable handoff, supply --playable-assignments and --visual-digest.
The candidate schedule is compiled by the existing HTML5 director compiler,
and --publish-playable-directory publishes its actual verified ZIP without
overwriting an existing artifact. This does not qualify native timing or assets.

The typed Jeeves tool studio_original_scene_rehearsal is registered in the
static allowlist and remains read-only. Regression fixtures cover determinism,
source/session authority, invalid authoring, private no-overwrite restore,
forgery, symlink denial, CLI/router parity, and real playable ZIP hashes.

Validation is required on the exact remote head. Canonical pytest, security
gates, device testing and consumer release are not asserted by source creation.

The offline CSP-hashed timing editor is published by --editor-directory. It
exports a source/session/baseline-bound JSON candidate. The CLI accepts
--import-candidate only with the exact baseline and replays the imported
candidate against canonical scene/quest source before any playable compilation.
The HTML publisher independently recompiles the editor before accepting bytes;
caller-supplied self-consistent hashes alone are never publication authority.

A bounded deterministic prompt-to-typed-generation route supports the exact
editorial intents: tighten pacing, preserve pacing, slow down for accessibility,
and reduce npc turnaround. Use --prompt instead of --candidate, or pass prompt
to the typed Jeeves tool. Unknown instructions fail closed. This is an explicit
rule-based authoring proposal, not a claim that a language model ran.
