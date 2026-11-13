# Guard Patrol Source Editor

Use \`python -m skeleton scene-patrol-author demo\` for a complete
editable source record. \`edit --author-json --edit-json\` supports
\`set_offset\`, \`set_bypass\`, \`set_exit_block\` and \`rename_patrol\`.
Every edit carries \`expected_source_digest\`, the digest from the
last verified author record. Stale edits fail without mutation.

The source is normalized after every edit. Removing the final guard
exit, selecting an unknown bypass item, introducing a disconnected
patrol or adding a non-existent exit is rejected. \`preview\` accepts
optional \`--actions-json\` and replays those actions through the
canonical scene patrol engine, returning the actual save and visible
guard positions. \`verify\`, \`export\` and \`import\` rebuild the
entire edit journal. Digests are corruption checks, not signatures.
