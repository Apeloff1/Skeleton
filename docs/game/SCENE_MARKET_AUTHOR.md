# Transactional Market Editor

Run \`python -m skeleton scene-market-author demo\` to edit the original
trade-and-delivery quest and preview its playable completion. The authoring
surface uses an exact normalized source digest as an optimistic concurrency
lease. Supported operations change authored prices, finite stock, coin pickup
values, existing ingredient requirements and delivery reputation. Unknown
targets, duplicate JSON keys, invalid quantities, stale source digests and
unplayable previews are rejected without publishing partial changes.

\`edit --source-json JSON --expected-source-digest SHA256 --operations-json JSON
[--preview-actions-json JSON]\` returns a portable receipt containing the
original source, validated operations, final normalized source, its digest and
an optional deterministic replay witness. \`verify --receipt-json JSON\`
replays the editor and preview from scratch. A checksum alone is not treated
as trusted authorship; receipt replay is mandatory. No arbitrary source code,
filesystem paths or external network access are executed by the editor.
