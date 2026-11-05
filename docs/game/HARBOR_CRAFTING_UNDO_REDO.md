# Replay-verified interactive undo and redo

Lantern Quay terminal play now supports `undo` and `redo` alongside `hint`,
`save` and the original gameplay commands. Undo reconstructs the exact
historical checkpoint from original source and the remaining action prefix.
Redo replays the removed action through the canonical gameplay engine.

After undo, choosing a different action clears the redo stack. Invalid undo
or redo commands do not advance the tick or modify the save. The terminal
never directly edits currency, inventory, NPC position, quest flags or ending.
Victory is still earned only by a legal delivery and final choice. The
terminal returns immediately on a verified victory; saved checkpoints can
be replayed or branched using the separate journal CLI.

The history is bounded by the world's existing 1024-tick limit and the
terminal's bounded command loop. `save` and EOF/quit checkpoints remain
portable JSON with source and event replay validation.
