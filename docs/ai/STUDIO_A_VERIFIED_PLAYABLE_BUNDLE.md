# Studio A unified verified playable bundle

\`world-bundle\` is the integrated authoring handoff. It requires three
independently reviewed, exact-source-bound inputs: the canonical world, original
asset briefs, and causal timeline. It compiles actual historical-era asset
recipes through Jeeves' engine compiler, embeds playable HTML with a strict CSP,
and emits a temporal manifest with verified ending witnesses.

\`\`\`sh
python -m skeleton world-bundle --store ./private-worlds compile \
  --world-id harbor --world-digest <WORLD_SHA256> \
  --asset-digest <ASSET_SHA256> --timeline-digest <TIMELINE_SHA256> \
  --era eight_bit_tile_1983
python -m skeleton world-bundle --store ./private-worlds verify \
  --world-id harbor
\`\`\`

The compiler publishes \`.bundle.html\`, \`.bundle.manifest.json\`, and finally
\`.bundle.receipt.json\`. The receipt is the publication marker; partial
artifact writes never count as a verified bundle. Verification reopens all
three files through no-follow descriptors, checks exact current source leases,
checks artifact SHA-256 digests, and **recompiles** HTML and engine manifests
deterministically to detect forged receipts or drift.

This is an offline browser-playable choice world with engine-facing asset and
temporal handoffs, not a claim that Studio B's engine consumed the manifest or
that any device, rights, publisher authenticity, CI, or release gate passed.
The SHA-256 receipts are integrity references, not cryptographic signatures.

Focused acceptance:
\`\`\`sh
python -m pytest -q skeleton/testing/test_jeeves_world_bundle.py
\`\`\`
