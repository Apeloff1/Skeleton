# Live original-game input bridge: historical B024 → canonical gameplay

The recovered B024 semantic action maps were initially only static control
profiles. This integration adds \`genre_playable_adapter.py\`: it converts
only actually-compatible B024 digital controls into the **current**,
receipt-bound \`skeleton.game.presentation.input_router.InputProfile\`.

The existing \`input_gameplay_bridge.play_inputs\` and
\`verify_input_gameplay\` remain the gameplay/save/replay authorities.
There is no duplicate gameplay simulation, new network endpoint or direct
OS input capture.

The B024 movement presets now include keyboard WASD and four digital gamepad
D-pad controls. Gamepad analog sticks and touch swipe axes remain in B024,
but do **not** silently become digital directions in the current Boolean
event router. Source-compatible interactions can use keyboard E, gamepad east
or touch long-press. Unsupported racing/flight steering, firearm combat and
genuinely analog input require their own engine-specific adapters.

The adapter can apply validated B024 user remaps and generates a source-bound
revisioned modern input profile. It then executes real original-game movement,
object interaction, inventory changes, collision checks, save/restore and
replay verification, with an enclosing digest protected against tampering.

The integrated regression uses the existing original Lantern Harbor campaign
fixture and verifies keyboard, controller/touch, remapping, genuine inventory
pickup, source identity and adversarial mutations. This does not claim
physical device drivers were playtested, nor that all 67 genre mechanics are
implemented by the grid campaign.

Focused tests:
\`python -m pytest -q skeleton/testing/test_input_gameplay_bridge.py skeleton/testing/test_genre_playable_adapter.py skeleton/game/presentation/test_genre_action_profiles.py skeleton/game/presentation/test_input_actions.py\`

Exact-head merge-readiness, backend, malware, hygiene, app E2E and native
device acceptance required prior to main or release promotion.
