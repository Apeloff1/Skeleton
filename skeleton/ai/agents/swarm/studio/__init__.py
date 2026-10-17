"""Game-studio swarm, as planner and QA stages of ``build_playable_game``.

The roster plans a compiled ``skeleton.game_design_spec.v1`` and reviews the
Godot checker, core loop, and playtest. It does not emit a second project.
Model calls are injected. Live provider traffic stays outside this package:
pass a callable that already goes through ``skeleton.provider_runtime``.

Levels covered by this package:

- L00 ownership: ``skeleton/automation/swarm`` (mirrored to ``skeleton/ai/agents/swarm``).
- L01 dependencies: swarm DAG and handoff, memory RAG/MAG, generated-code sandbox.
- L02 contracts: role handoff keys and checkpoint schema ``skeleton.studio.checkpoint.v1``.
- L03 authority: sandbox grants are sealed before any brief text is admitted.
- L04 control flow: plan waves, then ``build_playable_game`` planner/QA hooks.
- L05 state: on-disk checkpoints. Waves store file hashes, not repeated copies.
- L06 security: injection corpus preflight; a rejected brief never reaches the builder.
- L07 recovery: resume restores every tracked file; finished roles are not repeated.
- L08 observability: session events for waves, handoffs, QA, and repair requests.
- L09 economics: tool calls, denied calls, waves, repairs, estimated units, 120s budget.
- L10 evaluation: held-out briefs scored on builder output, plus negative controls.
- L11 rollback: ``StudioSession.rollback`` rewrites and deletes workspace files.
- L12 operator controls: ``StudioControls`` waves, repairs, top_k, playtest mode, dry run.
- L13 gap: headless boot stays at zero unless a Godot log contains ``CORE_LOOP_OK``.
  This package does not fork ``Forge.materialise``.
"""

from skeleton.automation.swarm.studio.eval import (
    BENCHMARK_BRIEFS,
    HELD_OUT_BRIEFS,
    run_benchmark,
)
from skeleton.automation.swarm.studio.memory import ProjectMemory
from skeleton.automation.swarm.studio.planner import PlanError, plan_brief
from skeleton.automation.swarm.studio.playtester import review_build, score_build
from skeleton.automation.swarm.studio.roles import (
    STUDIO_ROLES,
    StudioContractError,
    StudioRole,
    production_role_registry,
    validate_artefact,
)
from skeleton.automation.swarm.studio.scheduler import (
    StudioControls,
    StudioReport,
    StudioSession,
)
from skeleton.automation.swarm.studio.tools import StudioTools, ToolError

__all__ = [
    "BENCHMARK_BRIEFS",
    "HELD_OUT_BRIEFS",
    "STUDIO_ROLES",
    "PlanError",
    "ProjectMemory",
    "StudioContractError",
    "StudioControls",
    "StudioReport",
    "StudioRole",
    "StudioSession",
    "StudioTools",
    "ToolError",
    "plan_brief",
    "production_role_registry",
    "review_build",
    "run_benchmark",
    "score_build",
    "validate_artefact",
]
