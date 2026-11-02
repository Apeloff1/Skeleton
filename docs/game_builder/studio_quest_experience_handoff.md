# Source-bound original quest experience assembly

This builder-facing compiler composes **four independent authored receipts**:
reviewed localization, canonical sandbox achievements, operator-reviewed
pacing estimates, and human-reviewed content advisories. Each receipt has its
own typed Jeeves prompt, offline editor, bounded private persistence, replay,
and regression fixtures. This integration never treats display data as
canonical gameplay or safety evidence.

## End-user flow

1. Use the four typed Jeeves authoring tools to propose original quest labels,
   achievements, pacing estimates and content advisories. Keep exact source
   and initial-session leases and one canonical action list/target ending.
2. Edit and review the plans using their offline CSP-restricted editors, then
   compile and privately publish their replay-verified receipts.
3. Run \`python -m scripts.studio_quest_experience_cli --project PROJECT
   --localization-file LOCALE.json --achievements-file AWARDS.json
   --pacing-file PACING.json --advisories-file WARNINGS.json
   --accept-topic loud_audio\` for a single canonical readiness bundle.
4. Use \`--review-html\` for read-only, escaped, offline review; \`--publish DIR\`
   for exclusive private receipt publication; \`--restore DIR\` for exact
   replay verification; \`--handoff\` only when all review, ending, budget,
   consent and source/session checks pass.
5. The handoff contains canonical choice IDs, localized display rows, earned
   sandbox achievements, authored pacing estimates, reviewed advisories and
   current-checkpoint consent. The target game runtime must independently
   enforce consent at subsequent checkpoints and measure real timing.

## Invariants

All four receipts must replay from the same canonical quest source, initial
session, action history and target ending. Mismatches and tampered digests
fail closed. Unknown or repeated consent topics fail closed. Unreviewed
advisories cannot be used to infer safety. Missing player acceptance blocks
handoff without modifying quest state. A completed handoff proves only
deterministic source-level integration, **not** runtime/device acceptance,
external account awards, player safety, translation rights or release status.

Focused fixtures cover the complete four-receipt path, consent holds, stale
and mixed receipts, forged claims, HTML escaping, private no-clobber custody,
symlink refusal and CLI handoff. Required exact-head CI remains mandatory.
