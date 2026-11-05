# Player field journal — original authored session notes

A player can annotate a visited scene without modifying story canon or claiming
that an AI authored their note. The journal is stored under the same private
descriptor-anchored world custody as the canonical replayed session. Notes
record a scene, the exact choice-prefix digest, and the session revision.
Validation replays the actual canonical choices at each note's recorded
revision, including after the player advances to later scenes.

Use `python -m skeleton world-field-journal --store PRIVATE create --world-id delta --slot player`
to create an empty journal. `preview --note-id first --text "My note"`
returns a typed, read-only proposal. `append` requires both the current
journal digest and the exact session digest. `edit` requires the journal
digest and a previously recorded note ID. Stale updates fail closed.

`compile` requires the current journal and session digests and emits a
CSP-locked, HTML-escaped offline page plus a source-bound receipt. `verify`
recomputes both from current canonical custody. `editor` generates a
network-disabled, CSP-hashed page that exports typed JSON edits for explicit
operator CLI application; it does not publish on its own.

The Jeeves tools `world.field_journal_preview` and
`world.field_journal_propose_preview` are read-only. This is a player-authored
note surface, not a privileged AI memory store, release-certified game build,
or cross-device synchronization mechanism.
