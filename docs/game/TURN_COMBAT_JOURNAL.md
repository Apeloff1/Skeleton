# Source-bound offline turn combat

The canonical engine owner is `skeleton/game/gameplay/turn_combat.py`.
Run `python -m skeleton combat demo` to play an original scripted encounter
entirely offline. This is a real deterministic turn simulator, **not** a
rendered Godot combat adapter or autonomous NPC combat AI.

For an authored scenario, use:

```bash
python -m skeleton combat simulate --scenario-json '{"schema_version":"skeleton.turn_combat.v1","world_id":"moor","encounter_id":"watch","turn_limit":8,"actors":[{"id":"hero","team":"crew","max_hp":10,"attack":5,"defense":1,"speed":3},{"id":"foe","team":"wild","max_hp":6,"attack":3,"defense":0,"speed":1}]}' --actions-json '[{"kind":"attack","actor_id":"hero","target_id":"foe"},{"kind":"guard","actor_id":"foe"},{"kind":"attack","actor_id":"hero","target_id":"foe"}]'
```

The JSON result includes a versioned normalized source, canonical SHA-256
source digest, immutable turn journal, canonical gameplay EventBus digest,
save lineage and a deterministic terminal phase. To verify or continue an
exported result, use `combat verify --session-json '<json>'` or
`combat resume --session-json '<json>' --actions-json '<json>'`.
The caller owns durable storage; stdout can be redirected to an operator
controlled file. No file is read or written by the combat engine.

Actions are attack (enemy target), guard (next hit mitigation), and rest
(bounded healing). Speed and actor ID determine turn order. Commands from
other actors, friendly fire, illegal targets, malformed input, excessive
actors/turns and changes to a recorded save fail closed. Invalid commands
do not mutate the previous session. All numbers are bounded integers.
Source input, action batches and exported saves have strict versioned fields.

**Trust boundary:** Hashes detect accidental corruption and support
deterministic replay, but are not signatures. A malicious author can
rewrite source and all hashes. Authenticate and authorize source manifests
through the existing application provenance layer before accepting them
from another principal. This module has no provider, network, model,
native 3D, sound or device qualification claims.

Regression: `python -m pytest skeleton/testing/test_turn_combat_journal.py -q`.
