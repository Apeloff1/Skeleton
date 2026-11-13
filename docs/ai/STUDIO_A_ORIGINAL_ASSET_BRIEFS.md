# Original asset briefs → historical engine compiler

This is a real descriptor-to-engine compilation adapter, not a static asset
catalog. Every brief binds to a canonical authored world digest and an existing
scene. Authors must explicitly review and attest their original rights before
compilation. This is a declaration, **not** independent plagiarism or license
verification; publisher rights and consumer qualification remain held.

\`\`\`sh
python -m skeleton world-assets --store ./private-worlds propose \
  --world-id harbor --id hero --scene opening --kind sprite \
  --description 'Original sailor silhouette' --alt-text 'Sailor in a blue coat'
python -m skeleton world-assets --store ./private-worlds inspect --world-id harbor
\`\`\`

Review via an explicit JSON operation:
\`\`\`json
{"action":"review","value":{"id":"hero","originality_attested":true}}
\`\`\`

\`\`\`sh
python -m skeleton world-assets --store ./private-worlds edit \
  --world-id harbor --expected-digest <CURRENT_ASSET_DIGEST> \
  --operation-file ./review.json
python -m skeleton world-assets --store ./private-worlds compile \
  --world-id harbor --expected-digest <NEW_ASSET_DIGEST> \
  --era eight_bit_tile_1983
\`\`\`

Compilation calls \`skeleton.jeeves.game_engine_assets.compile_asset_build\`,
enforcing the selected engine's actual allowed kinds, palette, dimensions,
storage and era policies. The output is a deterministic compiled engine manifest
with source and asset digests and a SHA-256 publication receipt. It is not an
authenticity signature and not a visual asset renderer. The operator can review
the resulting manifest before downstream asset realization.

Focused tests:
\`\`\`sh
python -m pytest -q skeleton/testing/test_jeeves_world_asset_briefs.py
\`\`\`

Any world revision invalidates its asset source lease. Review is invalidated
when the asset descriptor changes. Source and compiled manifests use bounded
descriptor-anchored custody, exclusive leases and atomic publication.
