# Bounded Guard Patrol Route Solver

Run \`python -m skeleton scene-patrol-solve demo\` to find a legal
three-action route through the Lantern Hollow watch. The solver uses
the actual source-bound scene patrol transition engine and tests
collect, travel and wait actions in deterministic order. It never
creates keys, overrides guard blocks, changes authored exits or
skips canonical checkpoint validation.

\`solve --source-json\` accepts a patrol source and optional
\`--session-json\` to continue from a verified save. \`--max-nodes\`
and \`--max-depth\` bound work to at most 512 expansions and 32
actions. If a witness is found, the output includes canonical actions,
save, state digest and a replay receipt. If the budget is exhausted,
\`status: unproven\` explicitly does not assert that no route exists.

\`verify --source-json --result-json\` independently recomputes the
bounded search to reject forged shortest-path claims and altered
witnesses. The receipt is not a cryptographic signature.
