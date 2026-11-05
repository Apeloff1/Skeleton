# Offline UI authoring — source-leased scene editor

The browser editor is generated from the exact canonical world source. It
supports selecting a scene, editing its title and original narrative, and
exporting a typed JSON operation. No network, eval, innerHTML, third-party
scripts, or implicit source mutation is used. A CSP-hashed inline controller
and text-only DOM updates prevent HTML injection.

\`\`\`sh
python -m skeleton world-editor --store ./private-worlds \
  --world-id harbor --expected-digest <CURRENT_WORLD_DIGEST>
\`\`\`

Open the generated \`harbor.editor.html\` locally, review the scene text and
click **Export reviewed edit**. Apply the downloaded operation explicitly:

\`\`\`sh
python -m skeleton world-canon --store ./private-worlds edit \
  --id harbor --expected-digest <DISPLAYED_SOURCE_DIGEST> \
  --operation-file ./harbor.opening.reviewed-edit.json
python -m skeleton world-canon --store ./private-worlds compile \
  --id harbor --expected-digest <NEW_WORLD_DIGEST>
\`\`\`

A stale digest fails closed. Browser export does not imply approval or
publication. Downstream asset, timeline and plan leases must be regenerated
and reviewed after a canonical world revision.

Focused tests:
\`\`\`sh
python -m pytest -q skeleton/testing/test_jeeves_world_editor.py
\`\`\`
