# Mission Liveness and Softlock Audit

Run `python -m skeleton scene-mission-liveness --demo` to inspect the
original mission, or `--source-json` / `--session-json` for authored worlds
and replay-verified checkpoints. The audit expands only actions accepted by
the real mission runtime. Reachable active states without a legal continuation
are recorded with action witnesses, save lineage, source/state digests and
portable export checksums. Use `--verify-json` to independently recompute the
search and replay each softlock witness.

The audit has bounded `--max-states`, `--max-depth`, and `--max-findings`
controls. A clean result is only claimed when the bounded graph exploration
completed. Otherwise status is `inconclusive`, or `softlock_found` with an
explicit incomplete flag. A softlock cannot be repaired by inventing a reward,
teleport, mission completion or unlocked ending. The safe fallback is restoring
a verified earlier checkpoint or revising the authored source, then replaying
the entire save. Portable checksums are not signatures or proof of provenance.
