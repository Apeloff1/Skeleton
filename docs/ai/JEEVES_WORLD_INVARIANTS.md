# Exhaustive Jeeves world-state invariants

This feature proves authored continuity and state constraints over every
reachable canonical scene/earned-flag state, not just selected example routes.
A breadth-first exploration constructs shortest witnesses; every violation
witness is replayed with the canonical player. Inconclusive budget exhaustion
never becomes a pass.

Rules are a JSON array with \`id\`, \`kind\`, \`scene\`, and sorted \`flags\`.
Kinds are:

- \`forbid_all_flags\`: globally forbid two or more flags being held together;
  \`scene\` must be null.
- \`require_all_at_scene\`: require every listed flag whenever a scene is visited.
- \`forbid_any_at_scene\`: reject any listed flag at the selected scene.
- \`require_any_at_ending\`: require at least one listed flag at an ending.

All flags must be obtainable from actual authored choices. Invalid references,
duplicate rule IDs and malformed rules are rejected. Each rule must be exercised
by at least one reachable state; an unexercised rule is not a successful proof.

\`\`\`sh
python -m skeleton world-invariants --store ./private-worlds propose --world-id myworld --rules-file rules.json
python -m skeleton world-invariants --store ./private-worlds save --world-id myworld --rules-file rules.json --expected-world-digest WORLD_SHA
python -m skeleton world-invariants --store ./private-worlds inspect --world-id myworld
python -m skeleton world-invariants --store ./private-worlds approve --world-id myworld --expected-suite-digest SUITE_SHA --review-note "Reviewed"
python -m skeleton world-invariants --store ./private-worlds compile --world-id myworld --expected-suite-digest APPROVED_SHA
python -m skeleton world-invariants --store ./private-worlds verify --world-id myworld
\`\`\`

Operator approval is explicit and impossible when any rule fails. Source-leased
compilation produces an exhaustive JSON proof, actual offline CSP-protected
HTML5 player and last-published SHA-256 receipt. Verification recomputes both
artifacts under a world lock. The typed read-only Jeeves tool
\`world.invariants_preview\` never approves or mutates anything. Budgets:
2,048 states, 65,536 transitions, 64 rules. No release/device claim.
