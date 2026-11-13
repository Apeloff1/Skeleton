# Jeeves world choice-impact proof

The \`world-choice-impact\` vertical evaluates *actual canonical player
transitions* rather than asking a model to guess which choices matter. It
enumerates bounded reachable scene/earned-flag states and computes terminal
ending+flag signatures using a reverse fixed point, including cyclic routes.
Each choice carries a shortest replay-verified witness, context counts,
terminal signatures, and an explicit classification.

Use the operator CLI after authoring a world with \`world-canon\`:

\`\`\`sh
python -m skeleton world-choice-impact --store ./private-worlds preview --world-id myworld
python -m skeleton world-choice-impact --store ./private-worlds compile --world-id myworld --expected-world-digest SHA256
python -m skeleton world-choice-impact --store ./private-worlds verify --world-id myworld
\`\`\`

The optional \`--require-distinct\` policy fails closed when a reachable
branching choice has terminal outcomes equivalent to all its alternatives.
Equivalence concerns only ending IDs and earned flags: it **does not** mean
narrative prose, pacing, locations, animation, or experience are equivalent.
Unreachable choices and sole-option choices are reported separately. In
particular, this proof does not infer creative quality, originality, player
preference, or device readiness.

The read-only typed Jeeves tool \`world.choice_impact_preview\` returns the
same source-bound analysis without changing approval state or private files.
Only the operator CLI can publish. Publication holds an exclusive world lease,
checks the exact world digest, writes a canonical JSON report and a real
offline CSP-protected HTML5 player, and publishes a SHA-256 receipt last.
Verification recomputes the source analysis and compiled player, and rejects
stale, modified, missing, or symlinked artifacts. No network calls or external
asset dependencies are required.

Budgets: at most 2,048 reachable states, 65,536 transitions and 131,072
outcome propagation pairs. Budget exhaustion is an explicit error, never a
claim that two decisions are equivalent. The output is a bounded deterministic
source proof, **not** release certification.
