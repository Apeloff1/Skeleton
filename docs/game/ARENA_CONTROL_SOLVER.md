# Replay-Verified Control-Point Solver

`python -m skeleton arena-control-solve demo` searches the original Lantern
Harbor beacon match for a player-team win. Opponents use the canonical
deterministic tactical policy; all actions, collisions, damage, captures and
save lineage are recomputed by the same offline runtime as manual play.

`solve --source-json ... --team wayfarers [--resume-json ...]
[--max-nodes 256] [--max-depth 8]` accepts authored source or a replay-verified
checkpoint. Search is breadth-first over canonical legal attacks, moves,
guard and rest. Each opponent action is deterministic and counted in the
actual checkpoint's action budget. The result contains a source-bound
starting checkpoint, action witness and terminal replay snapshot.

`verify --receipt-json ...` independently reruns the bounded search and
compares the entire result. Invalid source, mismatched resume source,
edited receipts, illegal actions and excessive budgets fail closed.

The search is deliberately bounded: at most 256 expanded nodes and 8
player decisions. `unproven_within_budget` means no witness was found
under those limits, **not** that victory is impossible. It is not a
qualification claim about AI optimality or real-device performance.
