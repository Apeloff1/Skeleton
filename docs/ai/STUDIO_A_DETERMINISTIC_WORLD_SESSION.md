# Studio A — Deterministic original-world player sessions

`world-session` turns a source-proven Jeeves world into an actual
CLI-playable experience with durable, private player state. The author
creates the world from their original prompt with `world-canon`, edits
the typed scene/choice graph, and compiles the offline HTML5 player.
The player uses `world-session` to make real canonical choices,
earn flags, reach endings and resume an exact replayed checkpoint.

## Commands

```sh
python -m skeleton world-session --store ./private new --world-id marsh --slot first
python -m skeleton world-session --store ./private inspect --world-id marsh --slot first
python -m skeleton world-session --store ./private choose --world-id marsh --slot first --choice-id board --expected-digest <current-session-digest>
python -m skeleton world-session --store ./private export --world-id marsh --slot first > checkpoint-envelope.json
python -m skeleton world-session --store ./private import --world-id marsh --slot restored --checkpoint-file checkpoint.json
```

The `export` CLI emits `{"ok":true,"checkpoint":...}`, so extract
the `checkpoint` object before passing a JSON file to `import`.
Each read replays the full choice trace from the original world, checks
earned flags, source digest, ending and revision, and refuses forged
state or illegal transitions. Updates use an expected-digest compare-
and-swap under the per-world lock. Import creates a **new** slot only;
it cannot silently overwrite a saved player. Portable SHA-256 checksums
detect accidental or hostile corruption but are **not signatures** and
do not authenticate authorship.

The player state is bounded to 512 choices, and all private reads/writes
are descriptor-anchored with no-follow file handling. Changing the
world source invalidates old sessions until a separately reviewed
migration is implemented; no silent remapping of narrative history.
This is a canonical CLI play and persistence proof, not a claim of
device certification or deployed game quality.

Focused tests: `skeleton/testing/test_jeeves_world_session.py`.
