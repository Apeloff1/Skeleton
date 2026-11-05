# Unified source-exact Jeeves world assurance

The world assurance gate joins three **different** source-complete authoring
planes into one end-user playable handoff: authored scenario acceptance,
exhaustive state invariants, and terminal choice-consequence proof.

The operator first creates and explicitly approves scenario and invariant
suites, compiles each, then compiles the choice-impact report. The assurance
gate reads and independently rederives all three receipts and their actual
artifact bytes **under the same world lock**. Missing, stale, modified, or
symlinked upstream evidence blocks compilation.

\`\`\`sh
python -m skeleton world-assurance --store ./private-worlds preview --world-id myworld
python -m skeleton world-assurance --store ./private-worlds compile --world-id myworld --expected-world-digest WORLD_SHA
python -m skeleton world-assurance --store ./private-worlds verify --world-id myworld
\`\`\`

The read-only \`world.assurance_preview\` typed Jeeves tool reports readiness
without approving or writing. Compilation produces a canonical JSON handoff,
the real offline CSP-protected HTML5 playable, and a last-published SHA-256
receipt bound to all upstream receipts. Verification recomputes and checks all
upstream dependencies and the final artifacts, never treating a skipped or
missing proof as success.

This is **source-level assurance only**, not actual device, user acceptance,
external engine integration, CI, or release certification.
