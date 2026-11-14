# Cinder Ridge world workbench — interactive original-game editing

The workbench is a player-accessible map/source editor. It uses the existing
canonical Cinder Ridge world schema, immutable CAS authoring and reachability
checks; it does not fork the gameplay engine or invent a second save format.

```bash
python -m skeleton.game.gameplay.ridge_rescue.workbench_cli interactive
python -m skeleton.game.gameplay.ridge_rescue.workbench_cli open --output /tmp/ridge-editor.json
python -m skeleton.game.gameplay.ridge_rescue.workbench_cli inspect --session /tmp/ridge-editor.json
python -m skeleton.game.gameplay.ridge_rescue.workbench_cli preview --actions '[]'
```

Editor commands: `tile X Y .|#|~|^`, `move civilian|raider|resource
ID X Y`, `resource ID COUNT`, `turns COUNT`, `name TITLE`, `undo`,
`show`, `export`, and `quit`. Every accepted edit produces a new
immutable revision, validates actor occupancy, terrain and reachability, and
replays all preceding edits. Scripted editing accepts a JSON command list
with an exact `--expected-head` CAS lease; a stale revision is refused.

`preview` runs real player actions on the edited world, checks the
canonical portable replay and reports earned outcomes. `export` includes
the original source, complete edit history, resulting world and digests.
`verify-export` independently replays all edits. Portable digests are
integrity evidence, not signatures. Files are written create-only on
supported descriptor-anchored POSIX hosts; Windows and device release
qualification remain outstanding.
