"""Run-level deterministic replay for selected Mirror Room learning lineage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import (
    MirrorCandidate,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorScenario,
    ScenarioSplit,
    _digest,
    _sha256,
    _token,
)
from .engine import MirrorRunReceipt
from .sandbox import MirrorSandbox, SandboxExecutor, SandboxUsage


@dataclass(frozen=True, slots=True)
class MirrorRunReplayReceipt:
    run_digest: str
    spec_digest: str
    executor_id: str
    episode_digests: tuple[str, ...]
    replayed_episode_digests: tuple[str, ...]
    episodes_replayed: int
    usage: SandboxUsage
    exact_match: bool
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_digest", _sha256("run_digest", self.run_digest))
        object.__setattr__(self, "spec_digest", _sha256("spec_digest", self.spec_digest))
        object.__setattr__(self, "executor_id", _token("executor_id", self.executor_id))
        object.__setattr__(
            self,
            "episode_digests",
            tuple(
                _sha256("episode_digest", item)
                for item in self.episode_digests
            ),
        )
        object.__setattr__(
            self,
            "replayed_episode_digests",
            tuple(
                _sha256("replayed_episode_digest", item)
                for item in self.replayed_episode_digests
            ),
        )
        if (
            isinstance(self.episodes_replayed, bool)
            or not isinstance(self.episodes_replayed, int)
            or self.episodes_replayed < 0
        ):
            raise MirrorRoomError("episodes_replayed must be a non-negative integer")
        if not isinstance(self.usage, SandboxUsage):
            raise MirrorRoomError("replay usage must be SandboxUsage")
        if not isinstance(self.exact_match, bool):
            raise MirrorRoomError("exact_match must be boolean")
        if self.production_authority is not False or self.direct_self_modify is not False:
            raise MirrorRoomError("replay receipt is evidence-only")

    @property
    def digest(self) -> str:
        return _digest({
            "run_digest": self.run_digest,
            "spec_digest": self.spec_digest,
            "executor_id": self.executor_id,
            "episode_digests": list(self.episode_digests),
            "replayed_episode_digests": list(self.replayed_episode_digests),
            "episodes_replayed": self.episodes_replayed,
            "usage": {
                "episodes": self.usage.episodes,
                "steps": self.usage.steps,
                "tokens": self.usage.tokens,
                "cost_units": self.usage.cost_units,
            },
            "exact_match": self.exact_match,
            "production_authority": False,
            "direct_self_modify": False,
        })


def _sealed_holdout_digest(scenarios: Sequence[MirrorScenario]) -> str:
    return _digest({
        "split": ScenarioSplit.HOLDOUT.value,
        "scenario_digests": sorted(
            x.digest for x in scenarios if x.split is ScenarioSplit.HOLDOUT
        ),
    })


def verify_selected_lineage(
    run: MirrorRunReceipt,
    *,
    spec: MirrorRoomSpec,
    executor: SandboxExecutor,
    scenarios: Sequence[MirrorScenario],
) -> MirrorRunReplayReceipt:
    if not isinstance(run, MirrorRunReceipt):
        raise TypeError("run must be MirrorRunReceipt")
    if not isinstance(spec, MirrorRoomSpec):
        raise TypeError("spec must be MirrorRoomSpec")
    if run.spec_digest != spec.digest:
        raise MirrorRoomError("replay spec does not match Mirror Run")
    if getattr(executor, "executor_id", None) != run.executor_id:
        raise MirrorRoomError("replay executor identity changed")

    scenario_tuple = tuple(scenarios)
    if any(not isinstance(x, MirrorScenario) for x in scenario_tuple):
        raise MirrorRoomError("replay scenarios must contain MirrorScenario")
    scenario_map = {x.scenario_id: x for x in scenario_tuple}
    if len(scenario_map) != len(scenario_tuple):
        raise MirrorRoomError("replay scenario IDs must be globally unique")
    if _sealed_holdout_digest(scenario_tuple) != run.sealed_holdout_digest:
        raise MirrorRoomError("sealed holdout identity changed before replay")

    candidates: dict[str, MirrorCandidate] = {
        run.production_baseline.candidate_id: run.production_baseline
    }
    reports = []
    for generation in run.generations:
        for evaluation in generation.evaluations:
            candidates[evaluation.candidate.candidate_id] = evaluation.candidate
            if evaluation.selected or evaluation.selected_for_learning:
                reports.extend(
                    (
                        evaluation.training_report,
                        evaluation.validation_report,
                    )
                )
    if run.holdout_report is not None:
        reports.append(run.holdout_report)
    if not reports:
        raise MirrorRoomError("Mirror Run has no selected lineage to replay")

    sandbox = MirrorSandbox(spec, executor)
    original: list[str] = []
    replayed: list[str] = []
    for report in reports:
        baseline = candidates.get(report.baseline_candidate_id)
        candidate = candidates.get(report.candidate_id)
        if baseline is None or candidate is None:
            raise MirrorRoomError("replay candidate lineage is incomplete")
        for comparison in report.scenario_comparisons:
            scenario = scenario_map.get(comparison.scenario_id)
            if scenario is None:
                raise MirrorRoomError("replay scenario is unavailable")
            if scenario.digest != comparison.scenario_digest:
                raise MirrorRoomError("replay scenario content changed")
            b = sandbox.verify_replay(
                comparison.baseline_receipt,
                candidate=baseline,
                scenario=scenario,
            )
            c = sandbox.verify_replay(
                comparison.candidate_receipt,
                candidate=candidate,
                scenario=scenario,
            )
            original.extend((comparison.baseline_receipt.digest, comparison.candidate_receipt.digest))
            replayed.extend((b.digest, c.digest))

    if tuple(original) != tuple(replayed):
        raise MirrorRoomError("deterministic selected lineage replay diverged")
    return MirrorRunReplayReceipt(
        run_digest=run.digest,
        spec_digest=spec.digest,
        executor_id=run.executor_id,
        episode_digests=tuple(original),
        replayed_episode_digests=tuple(replayed),
        episodes_replayed=len(replayed),
        usage=sandbox.usage,
        exact_match=True,
    )


__all__ = ["MirrorRunReplayReceipt", "verify_selected_lineage"]
