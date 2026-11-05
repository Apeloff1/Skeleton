# Scene Escort Route Solver

`python -m skeleton scene-escort-solve demo` searches only legal source-bound
mission and convoy actions. It executes each candidate through the real
canonical runtime, tracks earned pickups and protection, and returns a
replay-verifiable delivered route with portable save bundle. The witness
can be verified independently using `scene-escort-solve verify` with the
original source and the witness JSON.

`solve --source-json SOURCE --max-depth N --max-states M` bounds the search.
A `found` route has an exact replay witness; `unreachable` means the
bounded search exhausted its legal reachable states without truncation.
`inconclusive` means the state or depth budget was reached, not that the
authored game is impossible. No reward is granted by the solver itself.

Run `python -m pytest skeleton/testing/test_scene_escort_solver.py -q`
alongside the scene escort runtime/author suites. Exact-head CI and
consumer qualification remain separate release gates.
