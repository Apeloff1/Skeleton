# Verified read-only comparisons across checkpoint rewinds — 2026-10-15

The live comparative emulator desk now offers **Compare rewind branches** beside the existing export tools. With an operator's approved native core, save a private checkpoint, advance one or more real controller inputs, rewind, and advance an alternate sequence. The new comparison aligns actual native input steps **after the same savestate**, identifying first differences in controller vectors, libretro frame SHA-256, and PCM SHA-256.

Each row is backed by the complete, independently recalculated live-session receipt chain. Original ROM bytes, private savestates, raw game pixels and original PCM remain outside the browser API; the output consists of game/source identifiers, numeric offsets and SHA references. A separate read-only, authenticated `GET /api/branches` endpoint provides the same report for Jeeves/Dragon review.

A second rewind correctly compares against the **immediately preceding branch**, not every historical step recorded since the checkpoint. The report stops branches at reset or further rewind boundaries. Incomplete trajectories show exactly how many steps actually aligned. Different controller inputs do not automatically imply a video change or game-mechanics discovery; the tests specifically use a synthetic worker whose frames do not depend on the button to enforce this distinction.

This feature is not a substitute for independent experimental repetitions or lawful ownership/permissions. The fresh-worker replay qualifier still refuses savestate-based branches until a full state-custody protocol is qualified. No production weights or long-term Dragon memory are changed.

New source-contract tests: input/frame divergence alignment, tampered checkpoint refusal, read-only bearer-token protection and same-origin security. The existing manual focused emulator regression workflow compiles the new module but has no new push trigger.
