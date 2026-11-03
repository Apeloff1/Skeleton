# Jeeves authored scenario acceptance and replay

This vertical provides an operator-authored acceptance suite for a **real**
canonical world. Unlike automatically enumerated choice coverage, it verifies
the exact scene, earned flags, and ending state expected from specified player
choice traces. It never asks a model to assert that gameplay passed.

Author a JSON array of cases, each with an ID, ordered \`choices\` list, and
\`expect\` object containing \`scene\`, sorted \`flags\`, and boolean \`ending\`.
All IDs must exist in the source world. An invalid transition is a failing
scenario with the canonical player error code, not a successful test.

\`\`\`sh
python -m skeleton world-scenario --store ./private-worlds propose --world-id myworld --cases-file cases.json
python -m skeleton world-scenario --store ./private-worlds save --world-id myworld --cases-file cases.json --expected-world-digest WORLD_SHA
python -m skeleton world-scenario --store ./private-worlds inspect --world-id myworld
python -m skeleton world-scenario --store ./private-worlds approve --world-id myworld --expected-suite-digest SUITE_SHA --review-note "Reviewed scenarios"
python -m skeleton world-scenario --store ./private-worlds compile --world-id myworld --expected-suite-digest APPROVED_SHA
python -m skeleton world-scenario --store ./private-worlds verify --world-id myworld
\`\`\`

Saving is create-only, digest-leased, private and unapproved. Approval requires
all authored assertions to pass canonical replay. Compilation requires that
approval and rechecks the world and suite while holding the exclusive world
lease. It produces a deterministic JSON report, the actual CSP-protected
offline playable HTML5 handoff, and a receipt published last with SHA-256
artifact digests. Verification recomputes the report and player bytes and
fails closed on stale source, mismatched receipts, symlinks, or corruption.

The typed \`world.scenario_preview\` Jeeves tool can inspect the current
suite without mutating files or authorizing it. This is a deterministic
source acceptance tool, not an AI evaluation, release test, or device pass.
