# Executable Jeeves/Dragon game-building tool plane

The companion and native game studio previously shipped a planning catalog.
That catalog was not an executor. `studio_execution_plane.py` now takes a
verified `ToolPlan` and **actually runs** a bounded subset of the canonical
game-building APIs with replayable, chained receipts.

## End-to-end controlled execution

```python
from pathlib import Path
from skeleton.ai.game_builder import (
    Actor, Phase, GameBuildIntent, ToolFabric, ToolRequest,
    canonical_digest, execute_local_tool_plan,
)

intent = GameBuildIntent(
    project_id="my-original-homebrew-2026",
    title="Star Garden", subtitle="Entirely original gameplay",
    seed=9, width=11, height=11, levels=1,
    collectibles_per_level=1, hazards_per_level=0,
    theme="space", starting_health=3,
)
digest = canonical_digest(intent.to_payload())
fabric = ToolFabric()
workflow = [
    (Actor.JEEVES, Phase.ORIGINAL, "world.generate"),
    (Actor.DRAGON, Phase.STEPPING_STONE, "game.simulate"),
    (Actor.DRAGON, Phase.STEPPING_STONE, "game.browser"),
    (Actor.DRAGON, Phase.STEPPING_STONE, "game.godot"),
    (Actor.COMPANION, Phase.STEPPING_STONE, "companion.practice"),
    (Actor.MIRROR, Phase.REVIEW, "mirror.fuzz"),
    (Actor.JEEVES, Phase.CONSUMER, "release.assess"),
    (Actor.JEEVES, Phase.CONSUMER, "package.source"),
]
requests = tuple(
    ToolRequest(actor, phase, tool, digest,
                "Produce independently verified original game")
    for actor, phase, tool in workflow
)
plan = fabric.plan(
    requests, authorized=True, allow_filesystem_write=True,
)
result = execute_local_tool_plan(
    intent, plan, fabric=fabric,
    authorized=True,
    destination=Path("/tmp/my-original-homebrew"),
    mirror_attempts=128, companion_games=2,
)
assert result.project.proof.final_state.status == "won"
assert result.mirror.passed
assert result.exported_path is not None
```

`authorized=True` is a trusted-local acknowledgement, **not** a substitute
for real authentication. Externally supplied agent instructions cannot grant
additional capabilities. The only executable IDs are `world.generate`,
`world.authored`, `game.simulate`, `game.browser`, `game.godot`,
`game.editor`, `companion.practice`, `mirror.fuzz`,
`release.assess`, and `package.source`.

All output is original source; the dispatcher does not call an external
model, toolchain, URL, shell, crawler, SDK, or package manager. Registering
metadata for an external tool is **insufficient** to execute it.

Each action checks the original intent's canonical digest and bound role,
phase, budget and tool-spec digest; the entire plan is checked for duplicates,
missing prerequisite dependencies, unsupported IDs and filesystem grants
before execution. Results include output digests, deterministic result
evidence digests, a receipt hash chain, mirror-room status and real companion
practice packages. For writes, a new, non-existing destination is required;
the atomic exporter refuses to overwrite. The source export must follow a
passing mirror room. Consumer or store publication never follows automatically.

The dispatcher can execute standalone generated or independently
human-reviewed authored worlds. Research source handoffs still use the
canonical reviewed-knowledge/RightsLedger adapter in
`original_game_studio.py`; there is **no** implicit crawler/model access from
this implementation.

## Next full-scale adapters

Deliver a typed, independently pinned adapter implementation for each of:
original sprite and audio generation; open-source art tools; Godot and other
engine asset import; original NPC, quest and simulation engines; physically
licensed homebrew compilers and emulators; release-specific QA; multi-platform
hardware runner interfaces. Each executor must supply both a native
integration test and receipt evidence before the capability is marked runnable.
No closed console SDK, firmware or game asset is included or assumed licensed.
