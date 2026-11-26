# Source-bound NPC continuity journal

This Studio A journal is an integrated, read-only chronology of canonical
scene timing, authored directed transit, accepted NPC meetings and earned
knowledge exchanges. It does not simulate physical travel or spoken dialogue.

Use \`scripts/studio_npc_continuity_cli.py\` with a canonical exchange receipt,
source digest and either \`--prompt\` or \`--authoring\`. The typed authoring
shape is \`{"notes":[{"event_key":"scene:...","text":"..."}]}\`. Event keys
must already exist in the replayed journal; notes cannot add or alter events.
The HTML companion escapes source facts and annotations and includes a
restrictive CSP. A knowledge fact is shown only when its exchange is earned.

The CLI can \`--publish\` an immutable private receipt, \`--restore\` it,
or \`--editor-directory\` to publish an offline CSP-hashed editor. Import
editor JSON using \`--import-authoring\` with \`--baseline-journal\`; source,
session, exchange and baseline digests are rechecked before compilation.

The Jeeves static router exposes \`studio_original_npc_continuity\`.
The playable handoff is the already-proven canonical HTML5 quest plus an
auditable companion HTML digest. Native scene rendering, physical travel,
NPC speech and device/release certification are not claimed.

Focused tests:
\`pytest -q tests/test_studio_ecosystem_npc_continuity_journal.py\`.
