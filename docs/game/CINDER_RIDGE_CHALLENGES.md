# Cinder Ridge — eight original playable rescue frontiers

Eight independently authored terrain challenges use the **same canonical
rescue engine** rather than eight copied engines. Each challenge contains
a distinct map, named survivor, obstacle topology, time budget and an actual
action trace. Two require finite gathering, signal crafting and beacon
activation for the protected ending. One requires stamina recovery across
a hazardous fog causeway. The others exercise directional evacuation and
different impassable-terrain constraints.

```bash
python -m skeleton.game.gameplay.ridge_rescue.challenges_cli list
python -m skeleton.game.gameplay.ridge_rescue.challenges_cli play --id north-pass
python -m skeleton.game.gameplay.ridge_rescue.challenges_cli play --id beacon-approach --output /tmp/ridge-beacon.json
python -m skeleton.game.gameplay.ridge_rescue.challenges_cli verify --bundle /tmp/ridge-beacon.json
```

Challenge IDs are strict allowlisted catalog entries. No caller-controlled
relative path is joined to the asset directory. Loading each scenario
replays the complete authored action sequence through movement, collision,
stamina, survival, crafting, rescue and earned ending checks. If the
content becomes unplayable or is tampered with, loading fails closed.
Portable game bundles can be independently verified. These source
fixtures and tests still require actual execution before qualification.
