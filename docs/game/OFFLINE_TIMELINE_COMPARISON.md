# Compare verified offline game timelines

Use the canonical app to compare two independent source-bound play sessions
without changing either save or inventing gameplay outcomes.

    python -m skeleton app game-project --compare-play-sessions first.json --other-session alternate.json --session-capsule original.json

Both histories are replayed against the same verified original capsule.
The receipt reports the common semantic control prefix, first divergent frame
(including the end of a shorter history), independent session digests, avatar
positions and victory frames. Identical histories have no divergent frame.

Malformed or forged sessions, source edits, symlinks and incompatible schema
versions fail closed. The operation writes no files and uses no network.
It is an offline analysis receipt, not a native renderer, signed proof or
legal release clearance. Saves remain layout-independent even if accessible
terminal remapping was used during original play.
