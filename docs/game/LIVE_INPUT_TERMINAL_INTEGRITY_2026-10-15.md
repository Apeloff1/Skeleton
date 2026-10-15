# Live comparative input and terminal-step integrity fixes

The real multi-lane controller desk now validates selected input-device types, not only port numbers. A keyboard payload on a joypad port, pointer on keyboard, or any input on disconnected ports is rejected *before any lane in the request executes*. Analog ports accept native analog axes and RetroPad button masks; mouse and pointer keep their own bounded typed vectors.

Batches that reach actual `episode_complete` early no longer send another native action to the finished episode. They return the real completed count and terminal frame, report a terminal boundary rather than a worker crash, and preserve every prior hash-linked receipt. A single burst may complete fewer steps than requested **without** implying those missing steps ran.

Exported native evidence now includes the exact approved core binary SHA-256. The offline verifier binds it to each native step. Tests use fake workers for terminal boundaries, input-type rejection and core-replacement detection; actual native emulator tests remain a separate requirement.

This does not make special controllers accurate or qualify hardware fidelity.
