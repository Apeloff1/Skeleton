# Source-bound original quest pacing

The pacing workbench connects an original quest prompt to a typed, editable
storyboard and deterministic canonical playthrough. It does **not** measure real
player speed or certify runtime, hardware, external evidence, or release.

## Operator flow

1. Compile the canonical quest program and start a canonical session. Keep the
   exact source digest and initial-session digest as optimistic leases.
2. Ask the allowlisted Jeeves tool \`studio_original_quest_pacing\` with the
   exact prompt \`draft an editable original quest pacing storyboard with explicit estimates\`,
   source/session leases, project, canonical action pairs and authored target ending.
   This returns an unreviewed, typed plan. No file is written.
3. Save the plan in a private \`0600\` JSON file and edit its stage-specific
   estimated seconds, intensity, label, note, and reviewed flags. Every stage
   must remain present in canonical order. The optional CSP-restricted HTML
   editor exports the same JSON plan without network access.
4. Run \`python -m scripts.studio_quest_pacing_cli --project PROJECT
   --expected-source DIGEST --expected-session DIGEST --plan-file PLAN.json\`
   for a deterministic replay receipt. Add \`--editor-html\` to export an
   offline editor, \`--publish DIRECTORY\` for an exclusive private receipt,
   \`--restore DIRECTORY\` to reopen it, or \`--handoff\` to require verified
   canonical session parity and an eligible, reviewed, within-budget route.
5. Pass the handoff to a game builder as a **presentation timing estimate**.
   Actual gameplay timing must be measured by the target runtime independently.

## Safety and correctness

All plan fields and limits are checked strictly; unknown fields, stale leases,
unreviewed played beats, budget violations, forged ending predicates, duplicate
stage rows, hostile JSON paths and tampered receipts fail closed. An unreviewed
proposal is not permission to publish. Private persistence uses descriptor-
anchored, exclusive no-clobber publication and bounded re-read. Digest checks
detect corruption and replay drift; they are not author signatures.

The CLI accepts only authored catalog projects and uses the same deterministic
quest compiler and replay as Jeeves. Regression fixtures cover source leases,
replay, edits, authorization, CSP, malformed plans, symlinks, no-clobber,
publication, and handoff. The feature remains unqualified until tests and
required exact-head CI have passed.
