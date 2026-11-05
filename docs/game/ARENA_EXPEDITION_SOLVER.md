# Expedition route solver (offline, deterministic)

Run `python -m skeleton combat-expedition-solve demo` for an original
Lantern Harbor expedition, or use `plan --source-json '<JSON>'` with a
source accepted by `combat-expedition simulate`. The `resume --session-json`
command starts from a **fully replay-verified** saved expedition; `verify`
and `verify-resume` recompute a planner receipt against the exact source
or checkpoint, respectively.

The search uses canonical combat outcomes, earned currency, inventory,
shop stock and healing. It never assumes a fight wins or grants unearned
items. Breadth-first search returns the shortest action sequence under
stable deterministic action ordering. `found` includes a replayable
action witness and its terminal state digest. `unreachable` means the
bounded finite state graph was exhausted; `inconclusive` means the
configured state/depth limit was hit, **not** that the game is impossible.

Limits: at most 256 explored states, 24 additional actions, canonical
expedition action budget of 96. Use `--max-states` and `--max-depth`
to reduce search work. The solver considers canonical automated fights,
purchases and consumable use; it does not synthesize player tactical
commands. The planner receipt is a deterministic checksum of gameplay
lineage, **not** an authentication signature or rights attestation.
Operator-controlled source origin and authorization remain mandatory.

A completed witness can be passed to `combat-expedition resume` or
`simulate`, exported with `combat-expedition export`, and re-imported
with `combat-expedition import`. No model provider, network or
non-deterministic random seed is required.
