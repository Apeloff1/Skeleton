# Original game production proposal queue — 2026-10-13

**DX-55–58:** Real persisted staged original game sources now have a
paged, source-versioned human review queue. It reads the existing canonical
\`reviews/proposals\` and \`reviews/accepted\` directories, never creates a
parallel database or permission owner, and binds each proposal to its actual
current-project base/source SHA-256.

\`studio.production.queue\` supports a 1–80 record filename cursor. It
classifies each current-project source as awaiting review, already human
committed, or stale/conflicted. Malformed, symlinked, oversized, invalid hash,
restricted, foreign-project and unsafe-path records are explicitly counted.
It does not treat a receipt or a proposal ID as an approval.

\`\`\`python
queue = runtime.invoke("studio.production.queue", {
    "project": "my_original_game",
    "limit": 30,
    "expected_snapshot": inventory_digest,
})["result"]
\`\`\`

The original Studio source tree remains the only commit destination.
**No repository tests were run** during this build-only pass.
