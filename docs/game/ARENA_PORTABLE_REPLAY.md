# Tactical arena inspection and offline portable expedition bundles

\`python -m skeleton combat-arena inspect --session-json JSON\` returns
a replay-derived turn timeline with actual changed actor positions, HP,
guard state, action receipt, state hashes and terminal outcome.
\`combat-arena compare --left-json JSON --right-json JSON\` identifies
identical, prefix and divergent histories from the **same authored source**.
Neither tool trusts a client-supplied timeline without full replay.

\`python -m skeleton combat-expedition export --session-json JSON\`
exports a portable offline bundle containing the full verified session,
source/state identity, schema and deterministic checksum.
\`combat-expedition import --bundle-json JSON\` checks size, schema,
checksum, source/state binding and every nested combat event before
returning a resumable session. Bundle inputs are capped to the existing
128 KiB JSON CLI budget; oversized sessions require a separately reviewed
streaming package format. This checksum is **not a signature** and does
not confer source authorship or authorization.

Focused tests:
\`python -m pytest skeleton/testing/test_arena_inspector.py
skeleton/testing/test_arena_bundle.py -q\`. Exact-head CI and device
qualification are still mandatory before claiming release readiness.
