# Accessible Weather Rescue Play

`python -m skeleton scene-weather-rescue-play --demo` opens an original
text-driven NPC rescue game. Available commands are `rescue NPC`,
`shelter NPC`, `collect PICKUP`, `travel EXIT`, `wait` or strict
canonical JSON. The scene view shows weather, NPC status/exposure, pickups,
inventory, available exits and whether a gate is weather-blocked.

Use `--source-json ...` to play an authored rescue or `--resume-json ...`
to continue a replay-verified checkpoint. `--expected-source-digest ...`
pins source identity. The canonical weather/scene engine applies every
player action; invalid commands do not mutate game state. After three
rejected commands or EOF, the last valid checkpoint is emitted before
a nonzero exit. Optional periodic checkpoints are also emitted.

The original playable route is: rescue canal_medic, collect find_key,
travel north, shelter canal_medic. Only successful shelter arrival earns
25 points. This is an offline accessible CLI, not graphical/device
qualification or network multiplayer authorization.
