# Interactive Market — bounded offline player stream

Run \`python -m skeleton scene-market-play demo\` to walk the original
trade-and-delivery quest. Every accepted movement, pickup, purchase, craft
and delivery passes through the canonical market reducer; the stream adapter
cannot mint goods or bypass authored collision, stock or recipient gates.

Use \`play --source-json JSON\` for a new authored game, or
\`play --session-json JSON\` for a replay-verified resume. An optional
\`--source-digest SHA256\` pins the trusted source, and
\`--checkpoint-every N\` (1..64) emits periodic complete snapshots.
The line-oriented player accepts \`move DIR\`, \`collect ID\`,
\`travel ID\`, \`buy OFFER\`, \`craft RECIPE\`, \`deliver ID\`, or a
strict JSON action. Each response is a machine-readable JSON line.

Input EOF and three invalid commands emit the last valid checkpoint
and return an error, never fabricate a terminal victory. Checkpoints
carry full source, action journal and save lineage; consumers must
call \`verify_market\` before trusting them. The CLI never opens
arbitrary files or performs network requests.
