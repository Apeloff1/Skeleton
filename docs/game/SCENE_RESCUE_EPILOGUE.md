# NPC rescue consequences and deterministic endings

`python -m skeleton scene-rescue-epilogue demo` plays the original
weather-gated rescue and emits a portable replay-derived ending. Each NPC
receives a safe, lost, escorting, or waiting narrative tied to canonical
weather travel, action history, deadlines, and earned rewards.

`render --session-json JSON` derives an ending from any saved rescue
checkpoint. Active sessions explicitly report an unfinished journey, not
a victory. `verify --epilogue-json JSON` replays the entire nested
checkpoint and checks every narrative line and reward.

`compare --first-json JSON --second-json JSON` contrasts two branches
of the **same source** and reports the earliest differing action, NPC
status changes, and earned reward delta. The output includes both full
replay-verifiable saves. `verify-comparison --comparison-json JSON`
reconstructs the comparison; edited claims fail closed.

The integrity receipt is a deterministic hash, **not** an authentication
signature or provenance proof. Treat externally supplied sources as
untrusted. No story is invented from unverified NPC state.

Focused tests:
`python -m pytest skeleton/testing/test_scene_weather_rescue_epilogue.py -q`
