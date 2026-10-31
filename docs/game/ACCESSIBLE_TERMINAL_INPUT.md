# Accessible offline terminal controls

The canonical game-project CLI supports local-only single-key remapping.
Input profiles affect terminal interpretation only: saved sessions contain
semantic left/right/jump controls and are independently source-bound.

Example profile JSON:

    {"schema_version":"skeleton.game.terminal_input_profile.v1","bindings":{"left":"j","right":"l","jump":"i","wait":".","quit":"x"}}

Use with a previously created original game capsule:

    python -m skeleton app game-project --terminal-play-capsule original.json --terminal-input-profile accessible.json --save-session save.json
    python -m skeleton app game-project --verify-play-session save.json --session-capsule original.json

Profiles use the canonical bounded, no-symlink JSON reader (4096-byte limit).
Keys are lowercase ASCII letters/digits except idle, which stays '.'.
Bindings cannot collide; opposite directions cannot be pressed together.
Commands can combine a direction with jump. The quit key never manufactures
a save. A profile digest is recorded in the operator receipt, not the save.
Resuming with a different layout preserves deterministic source-bound replay.

This is offline ASCII turn-based play, not a native renderer. Profile hashes
are neither signatures nor authorization or legal release clearance. New
save files are exclusive and cannot overwrite existing content.
