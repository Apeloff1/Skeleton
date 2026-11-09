# Live comparative native checkpoints and rewinds — 2026-10-15

The live emulator desk can now save and restore **actual private libretro savestates** for each selected game. Each game screen has an explicit **Save private checkpoint** and **Rewind to checkpoint** control below the existing controller deck. These are operator actions, not a background trainer or a synthetic screenshot animation.

## Bounds and native behavior

- Each native lane may capture **at most two checkpoints** over the entire live desk lifetime. Only the latest checkpoint is retained, keeping memory bounded by the native host's existing <=8 MiB savestate contract. Ten active lanes retain at most one private state per lane.
- The operator may rewind a lane at most **twice**. An actual `EmulatorEnvironment.restore` call must restore the exact committed source frame SHA. The source core binary and study identity are retained.
- The 256-input **lifetime** step ceiling never resets after rewind. Returning to a prior episode cursor does not create additional training or playback budget.
- An explicit native reset discards the previous private checkpoint to prevent cross-episode state confusion. A native worker error closes the affected lane; it does not fabricate a successful rewind.
- The HTTP control plane retains 127.0.0.1 binding, random process authorization, exact same-origin POST checks, and per-request body limits. The browser cannot supply raw state bytes, paths or commands.

## Evidence custody and independent replay

The UI, JSON state and exported study report contain **only** SHA-256 hashes of native memory-state bytes and snapshot descriptors. No encoded savestate, game RAM, emulator memory page or ROM is sent through the live HTTP API.

Each checkpoint or rewind is a new SHA-chained event tied to the source-media/core hash, native episode step, exact checkpoint ID, reset generation and actual restored frame. The offline verifier validates every event, including that a rewind returned to a checkpoint from the same reset generation. Up to 256 steps, 4 resets, 2 checkpoints and 2 rewinds (264 events) are admitted.

**Important replay limitation:** A timeline after `native_rewind` is a savestate fork, not a new power-on/reset epoch. The existing fresh-worker replay qualifier cannot yet prove such a branch without audited state custody. For a rewound game, its `replayable_controller_tapes` field is deliberately empty and `replay_gate` names the missing qualification. The native replay CLI fails closed, rather than treating the branch suffix as a standalone controller recording.

Synthetic worker tests cover exact restored episode cursor and frame, SHA-chain verification, no private game memory in exported payloads, tampered checkpoint rejection, reset invalidation, strict checkpoint/rewind caps, and same-origin HTTP authorization. They are included in the existing manually triggered focused emulator qualification workflow.

This is production source implementation, **not proof** of actual physical-console accuracy, an installed commercial emulator, real game boot, or trained model weights. The existing lawful homebrew C ABI smoke fixture separately demonstrated native video/audio/controller/state callback behavior; a full Linux Bubblewrap-host run remains dependent on its isolated environment and CI status.
