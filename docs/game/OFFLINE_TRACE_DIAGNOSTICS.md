# Replay-verified gameplay frame diagnostics

The canonical app exposes real deterministic simulation outcomes for a bounded
window of frames in a saved original game. Use inclusive one-based frame bounds:

    python -m skeleton app game-project --inspect-play-trace save.json --session-capsule original.json --trace-start 1 --trace-end 32

Every source capsule and complete saved history is verified before inspection.
The trace includes the actual controller buttons, avatar, grounded state, goal
trigger and vertical distance traversed per frame, with a canonical SHA-256
digest for the window. Each request is limited to 64 frames and cannot extend
past the saved history. The operation never changes saves, reads network data
or claims a native renderer or signed release.
