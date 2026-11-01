# Weather-Gated NPC Rescue Missions

`python -m skeleton scene-weather-rescue demo` plays an original Lantern
Harbor rescue. The player escorts a stranded canal medic from the quay to
the gate shelter, collects the canonical brass key, traverses a weather
gate during a clear interval, survives one storm exposure, and earns 25
reward points only after a replay-verified shelter arrival.

The source defines up to eight unique NPCs with origin, shelter, deadline,
storm-exposure tolerance and reward. `rescue NPC` and `shelter NPC`
are distinct authored mission actions. Every action advances the canonical
weather clock; travel, pickup, inventory, weather restrictions and scene
endings remain owned by the existing scene/weather engines. NPCs can wait,
be escorted, reach safety, or be lost to exposure/deadline. Lost NPCs
cannot be recovered by editing a save or importing a forged receipt.

Commands: `new --source-json ...`, `play --source-json ...
--actions-json ...`, `resume --session-json ... --actions-json ...`,
`verify --session-json ...`, `pack --session-json ...`, and
`unpack --package-json ...`. The original demo uses four actions:
rescue, collect, travel north and shelter. All outcomes and earned rewards
are reconstructed from canonical action journals with bounded JSON exports.

This is a deterministic offline game mission, not a provider-based NPC,
a cryptographic signature, network authority or device-release certificate.
