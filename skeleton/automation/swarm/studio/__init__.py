"""Game-studio swarm.

A production roster on the canonical swarm DAG. The director plans a brief
into a dependency graph, role agents hand off artefacts, and QA runs the
playable headless. Model calls are injected and therefore mockable. Live
provider traffic stays outside this package: pass a callable that already
goes through ``skeleton.provider_runtime``.

Levels covered by this package:

- L00 ownership: ``skeleton/automation/swarm`` (mirrored to ``skeleton/ai/agents/swarm``).
- L01 dependencies: swarm DAG and handoff, memory RAG/MAG, generated-code sandbox.
- L02 contracts: role handoff keys and checkpoint schema ``skeleton.studio.checkpoint.v1``.
- L03 authority: sandbox grants are sealed before any brief text is admitted.
- L04 control flow: plan, wave, handoff, optional repair, QA.
- L05 state: checkpoint snapshots, including artefacts, files, and memory rows.
- L06 security: injection corpus preflight; untrusted pitches cannot widen grants.
- L07 recovery: resume skips finished roles; rollback restores a wave snapshot.
- L08 observability: session events for waves, handoffs, playtests, repairs.
- L09 economics: tool calls, denied calls, waves, repairs, estimated units.
- L10 evaluation: ``run_benchmark`` with a fast CI subset.
- L11 rollback: ``StudioSession.rollback`` plus overwrite-on-rerun of project files.
- L12 operator controls: ``StudioControls`` max waves, repairs, top_k, dry run.
- L13 gap: this is not an enterprise-superiority claim. It does not replace
  the brief-to-engine pipeline another owner is building, and it does not
  ship a commercial engine.

Remaining product gaps live in the pull request, not in a self-issued grade.
"""

from skeleton.automation.swarm.studio.eval import BENCHMARK_BRIEFS, run_benchmark
from skeleton.automation.swarm.studio.memory import ProjectMemory
from skeleton.automation.swarm.studio.planner import PlanError, plan_brief
from skeleton.automation.swarm.studio.roles import (
    STUDIO_ROLES,
    StudioContractError,
    StudioRole,
    production_role_registry,
    validate_artefact,
)
from skeleton.automation.swarm.studio.scheduler import StudioControls, StudioReport, StudioSession
from skeleton.automation.swarm.studio.tools import StudioTools, ToolError

__all__ = [
    "BENCHMARK_BRIEFS",
    "PlanError",
    "ProjectMemory",
    "STUDIO_ROLES",
    "StudioContractError",
    "StudioControls",
    "StudioReport",
    "StudioRole",
    "StudioSession",
    "StudioTools",
    "ToolError",
    "plan_brief",
    "production_role_registry",
    "run_benchmark",
    "validate_artefact",
]
