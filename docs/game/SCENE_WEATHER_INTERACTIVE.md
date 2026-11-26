# Interactive weather-gated scene play

`python -m skeleton scene-weather-play --demo` starts an original offline
Lantern Harbor journey. The text commands are `collect PICKUP`,
`travel EXIT` and `wait`. Strict JSON actions are also accepted.
Each scene frame shows weather, available pickups, inventory, exit
requirements and weather-blocked exits. The canonical scene engine owns
movement and inventory; the weather overlay gates collisions and advances
its deterministic cycle with each accepted action.

Use `--source-json '<authored weather source>'` to play your own world or
`--session-json '<replay-verified weather save>'` to resume. Optional
`--expected-digest` binds the session to the intended source. The
`--checkpoint-every` setting is bounded to 1..64 actions.

The CLI emits newline-delimited JSON events: started, scene, accepted,
rejected, checkpoint and terminal. On EOF or three invalid commands it
emits the **last verified checkpoint** and exits nonzero, without inventing
progress. A terminal checkpoint can be passed to `scene-weather-package`
for portable offline delivery and independently replayed by
`scene-weather verify`. This feature performs no filesystem writes,
network requests or provider calls. Checkpoint digests are not signatures.
