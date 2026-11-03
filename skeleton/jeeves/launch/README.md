# Launch-Ready AI Game Studio

Immediately usable local AI systems for building games from a brief to a playable pack.

## Entry point

```python
from skeleton.jeeves.launch import launch_build

result = launch_build("A dark metroidvania where the player absorbs enemy abilities")
print(result["ready_for_launch"])  # True when fidelity >= 0.92
print(result["fidelity"])
print(result["concrete"]["pack"])
```

## Modules

- `ai/conductor.py` — Full 9-stage pipeline (brief → emit → critique → refine)
- `ai/behaviors.py` — Behavior selection, boss phases, combat resolution
- `game/builders.py` — Room, entity, dialogue, loot, and Godot emit builders
- `game/progression.py` — XP, leveling, ability unlocks, quests, inventory
- `distill/engine.py` — Knowledge card distillation from pipeline results
- `__init__.py` — `LaunchAppFacade` and `launch_build()` convenience

## Fail-closed

Empty briefs raise. Missing critical artifacts fail the emit stage. Fidelity is tracked at every stage. A successful run clears the 0.92 launch threshold.
