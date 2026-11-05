# Scene Market — original playable trade-and-delivery vertical

Run \`python -m skeleton scene-market demo\` to complete an original offline
market quest. The canonical tile engine supplies collision, pickup provenance,
locked exits and endings. The market layer only mints currency when the player
actually collects an authored pickup; it never invents canonical inventory.

## Source and gameplay

\`schema_version=skeleton.scene_market.v1\` binds a canonical tile source,
finite-value coin pickups, reachable market stalls with priced limited stock,
reachable crafting stations with ingredient requirements, one-time recipient
deliveries, and a list of mandatory deliveries before the canonical ending.
All IDs, tile positions, stock, amounts and bounded list sizes are validated
before play. A successful canonical ending without required deliveries is a
market loss, not a successful completion.

The \`tile\` action wraps the canonical \`move\`, \`collect\` and \`travel\`
actions. The \`buy\` action consumes earned credits at a market position and
respects stock. The \`craft\` action consumes goods at an authored station.
The \`deliver\` action consumes goods at a recipient, once, and awards earned
reputation. Every action is deterministic and records a before/after digest,
receipt and save ancestry. Failed actions do not change the checkpoint.

## CLI and portable custody

\`python -m skeleton scene-market demo\` prints a replay-verified winning save.
\`simulate --source-json JSON --actions-json JSON\` plays authored content.
\`resume --session-json JSON --actions-json JSON\` resumes an authenticated
checkpoint. \`verify --session-json JSON\` rebuilds all rewards from actions.
\`export --session-json JSON\` produces a bounded checksum-sealed offline
bundle; \`import --bundle-json JSON\` verifies its source and state lineage.
The engine does not read arbitrary files or execute source strings. JSON
inputs reject duplicate keys, nonfinite numbers and oversized payloads.

Regression tests cover complete playable delivery, checkpoint equivalence,
finite stock, currency conservation, positional gating, crafting and recipient
rewards, forgery, bundle tampering and main CLI routing.

This feature is staged on the Scene Production dependency branch and does
not independently certify release, CI, device support or other studios.
