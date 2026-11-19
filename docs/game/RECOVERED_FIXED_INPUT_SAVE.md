# Recovered movement and SQLite replay qualification

The fixed-input-replay command composes the pre-existing device-agnostic
ActionMap/InputState, integer fixed clock, swept character collision, and
simulation rollback contracts. An explicit bounded input order supplies
controller state, authored obstacle boxes, remapping information, elapsed
microseconds and quantized control samples. One semantic axis snapshot is
used for the emitted ticks of a frame; excess host time is recorded as
dropped, not invented as simulation. The replay can restore a separately
pinned snapshot by reprocessing the same source prefix. The midpoint
rollback witness is derived from the canonical rollback contract.

The recovered-save-qualify command executes either the movement replay or
the synthesized quest campaign, then stores the midpoint through
ProjectSaver/GameSavePlane in a fresh temporary SQLite database with the
canonical replay journal. It closes the connection, reloads the exact
source and save bytes, continues the replay, stores a completed version,
reopens that version, computes the project diff, appends a rollback,
and reopens again to verify retained prior history. No pre-existing
database is used. The temporary directory is automatically cleaned.
This measures disk-backed connection reopening when actually run, not
process restart, crash durability or physical device qualification.

Both commands require the explicit local operator flag. Native engine,
device, source qualification and release holds are unchanged. The
qualification test source is selected by the existing gate.
