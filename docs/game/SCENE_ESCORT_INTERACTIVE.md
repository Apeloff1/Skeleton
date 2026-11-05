# Interactive Scene Escort

`python -m skeleton scene-escort-play demo` starts the original lantern
caravan. The player enters `choose CHOICE OPTION`, `collect PICKUP`,
`protect`, `travel EXIT`, `finish ENDING`, or a complete canonical JSON
escort action. Each turn emits a machine-readable JSON line containing
available runtime-validated actions, convoy integrity, earned supplies,
mission progress and a digest. No input bypasses canonical mission actions.

The `play --source-json JSON` and `resume --session-json JSON` commands
support authored sources and replay-verified interruption recovery. Pin
`--expected-source-digest` to reject source drift. Checkpoints are emitted
on configured intervals, terminal states, EOF, invalid-input exhaustion,
no legal actions, and turn-budget exhaustion. A terminal event includes a
portable bundle independently importable by `scene-escort import`.

Input is byte-bounded and duplicate JSON keys are rejected. Three invalid
attempts terminate with a verified checkpoint rather than an implicit
action or reward. The CLI returns nonzero on lost convoys and invalid
input. Run `python -m pytest skeleton/testing/test_scene_escort_interactive.py
-q` with the runtime/solver/author suites; exact-head CI remains mandatory.
