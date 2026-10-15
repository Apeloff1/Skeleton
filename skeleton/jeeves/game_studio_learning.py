"""Executable bounded Jeeves/Dragon/adversarial studio learning campaigns.

Campaign budgets are plans; only committed, actually executed rounds advance
cursor. Deterministic specialist checks are not LLM art critics. The existing
application workspace owns authorization, leases, durable rounds and lessons.
"""

from __future__ import annotations

import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
import math
import random
import struct
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .game_learning import (
    GameLearningCancelled,
    GameLearningConfig,
    GameLearningError,
    GamePolicyLearner,
    _copy_json,
)
from .game_learning_parallel import GameEnvironmentRequest
from .game_style_analysis import MECHANIC_CATALOG, canonical, digest

CAMPAIGN_SCHEMA = "skeleton.game.studio_campaign.v2"
ROUND_SCHEMA = "skeleton.game.studio_round.v1"
LESSON_SCHEMA = "skeleton.game.studio_lesson.v1"
CONTEXT_FIELDS = ("target_id", "genre", "engine", "source_digest", "code_digest")
TRANSFER_FIELDS = ("target_id", "genre", "engine", "code_digest")
PROPOSAL_TRANSFER = "proposal_only_not_measurement"
OBJECTIVE_CATALOG = {
    "return": {"unit": "actual environment reward", "default_weight": 1.0},
    "completion": {"unit": "completed episode fraction", "default_weight": 0.5},
    "survival": {"unit": "episode fraction without observed death", "default_weight": 0.5},
    "coverage": {"unit": "distinct observed binned states / executed steps", "default_weight": 0.2},
    "diversity": {"unit": "normalized action entropy", "default_weight": 0.1},
}
CURRICULA = ("fresh", "mixed", "counterexample")


def campaign_catalog() -> dict[str, Any]:
    return _copy(
        {
            "schema_version": "skeleton.game.studio_catalog.v2",
            "objectives": OBJECTIVE_CATALOG,
            "curricula": list(CURRICULA),
            "proposal_families": ["policy", "mechanics", "economy", "entities", "layout", "fidelity"],
            "evaluation_seeds": {"minimum": 1, "maximum": 8, "default": 3},
            "objective_weight_bounds": [0, 10],
            "objective_normalization": "Return delta/max(1,abs baseline mean return); other deltas use their measured fractions.",
            "constraints": {
                "max_mean_step_ms": {
                    "unit": "offline operation wall milliseconds",
                    "minimum": 0,
                    "maximum": 60000,
                    "default": None,
                    "optional": True,
                },
                "max_death_regression": {
                    "unit": "episode fraction",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0,
                },
                "max_worst_seed_regression": {
                    "unit": "actual environment reward",
                    "minimum": 0,
                    "maximum": 1e9,
                    "default": 0,
                },
            },
            "curriculum_descriptions": {
                "fresh": "New training seeds; exact-environment admitted parent weights may still continue.",
                "mixed": "At most one eligible prior counterexample seed reexecuted as training, then new seeds.",
                "counterexample": "Eligible prior counterexample seeds reexecuted up to episode budget; remaining episodes use new seeds.",
            },
            "counterexample_limit": 16,
            "counterexample_bytes": 524288,
            "measurement_claim": "Actual numerical measures; no subjective quality or model critic",
        }
    )


def _int(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise GameLearningError(f"{name} must be an integer within[{low},{high}]")
    return value


def _copy(value: Any, limit: int = 8 * 1024 * 1024) -> Any:
    return json.loads(canonical(value, limit=limit))


def _implementation() -> str:
    names = (
        "game_studio_learning.py",
        "game_learning.py",
        "game_learning_parallel.py",
        "game_learning_runtime.py",
        "game_learning_demonstrations.py",
        "game_style_analysis.py",
        "game_successor.py",
        "game_successor_assets.py",
        "game_successor_runtime.py",
        "game_successor_world.py",
        "game_console_editor.py",
        "game_console_simulation.py",
        "game_console_graph.py",
        "game_console_assets.py",
        "game_emulator_host.py",
        "game_studio_review.py",
        "game_studio_environment.py",
        "game_studio_rule_curriculum.py",
    )
    return digest(
        {
            "python": list(sys.version_info[:3]),
            "files": {
                name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in names
                if Path(__file__).with_name(name).is_file()
            },
        }
    )


def _guard(cancel: Callable[[], bool] | None, authorize: Callable[[], None] | None) -> None:
    if cancel is not None and cancel():
        raise GameLearningCancelled("studio campaign slice cancelled")
    if authorize is not None:
        result = authorize()
        if result is False or result is not None and result is not True:
            raise GameLearningError("studio campaign authorization did not finish synchronously")


@dataclass(frozen=True, slots=True)
class CampaignConfig:
    round_limit: int = 100000
    slice_rounds: int = 4
    episodes_per_round: int = 1
    episode_steps: int = 256
    seed: int = 0
    min_improvement: float = 0.0
    max_slice_steps: int = 131072
    evaluation_seeds: int = 3
    curriculum: str = "mixed"
    objective_weights: Mapping[str, float] | None = None
    max_mean_step_ms: float | None = None
    max_death_regression: float = 0.0
    max_worst_seed_regression: float = 0.0

    def __post_init__(self) -> None:
        _int(self.round_limit, "campaign rounds", 1, 100000)
        _int(self.slice_rounds, "slice rounds", 1, 8)
        _int(self.episodes_per_round, "round training episodes", 1, 10)
        _int(self.episode_steps, "episode steps", 1, 4096)
        _int(self.seed, "campaign seed", 0, 2**63 - 1)
        _int(self.max_slice_steps, "slice step budget", 1, 131072)
        _int(self.evaluation_seeds, "paired evaluation seeds", 1, 8)
        if self.curriculum not in CURRICULA:
            raise GameLearningError("unsupported campaign curriculum")
        weights = {k: v["default_weight"] for k, v in OBJECTIVE_CATALOG.items()}
        if self.objective_weights is not None:
            if not isinstance(self.objective_weights, Mapping) or set(self.objective_weights) - set(weights):
                raise GameLearningError("unknown campaign objective")
            weights.update(self.objective_weights)
        if any(
            type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 10 for v in weights.values()
        ) or not any(weights.values()):
            raise GameLearningError("objective weights must be finite, bounded and nonzero")
        object.__setattr__(self, "objective_weights", MappingProxyType(weights))
        for name, maximum in (("max_death_regression", 1), ("max_worst_seed_regression", 1e9)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise GameLearningError("campaign regression constraint outside bounds")
        if self.max_mean_step_ms is not None and (
            type(self.max_mean_step_ms) not in (int, float)
            or not math.isfinite(self.max_mean_step_ms)
            or not 0 < self.max_mean_step_ms <= 60000
        ):
            raise GameLearningError("actual mean step latency constraint outside bounds")
        if (
            type(self.min_improvement) not in (int, float)
            or not 0 <= self.min_improvement <= 1000000
            or not math.isfinite(self.min_improvement)
        ):
            raise GameLearningError("minimum improvement must be finite and nonnegative")

    def as_dict(self) -> dict[str, Any]:
        return {
            f.name: dict(self.objective_weights) if f.name == "objective_weights" else getattr(self, f.name)
            for f in fields(self)
        }


def validate_lesson(value: Mapping[str, Any], *, context_digest: str) -> dict[str, Any]:
    raw = _copy(dict(value), 262144)
    required = {
        "schema_version",
        "context_digest",
        "round_index",
        "role",
        "outcome",
        "candidate_digest",
        "facts",
        "recommendation",
        "evidence_digest",
        "lesson_digest",
    }
    if (
        set(raw) != required
        or raw["schema_version"] != LESSON_SCHEMA
        or raw["context_digest"] != context_digest
    ):
        raise GameLearningError("lesson schema or target/genre/engine/source/code scope differs")
    _int(raw["round_index"], "lesson round", 1, 100000)
    if raw["role"] not in ("jeeves", "dragon", "adversary", "decision") or raw["outcome"] not in (
        "accepted",
        "rejected",
    ):
        raise GameLearningError("lesson role/outcome differs")
    unsigned = {k: v for k, v in raw.items() if k != "lesson_digest"}
    if raw["lesson_digest"] != digest(unsigned):
        raise GameLearningError("lesson evidence digest differs")
    for field in ("candidate_digest", "evidence_digest"):
        if (
            not isinstance(raw[field], str)
            or len(raw[field]) != 64
            or any(c not in "0123456789abcdef" for c in raw[field])
        ):
            raise GameLearningError("lesson identity is not SHA-256")
    if (
        not isinstance(raw["facts"], dict)
        or not isinstance(raw["recommendation"], str)
        or len(raw["recommendation"]) > 1024
    ):
        raise GameLearningError("lesson facts/recommendation exceed bounds")
    return raw


def make_proposal_prior(
    lesson: Mapping[str, Any],
    *,
    origin_context: Mapping[str, Any],
    destination_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve issued empirical evidence while proposing across admitted builds.

    The application must reauthorize the historical source and issuing owner.
    This envelope grants no source rights or empirical authority in a new build.
    """
    origin = _copy(dict(origin_context), 65536)
    destination = _copy(dict(destination_context), 65536)
    for context in (origin, destination):
        if not all(isinstance(context.get(k), str) and 1 <= len(context[k]) <= 256 for k in CONTEXT_FIELDS):
            raise GameLearningError("proposal requires explicit original and destination contexts")
        for name in ("source_digest", "code_digest"):
            value = context[name]
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise GameLearningError("proposal source/code identity is not SHA-256")
    if any(origin[k] != destination[k] for k in TRANSFER_FIELDS):
        raise GameLearningError("proposal target/genre/engine/code eligibility differs")
    original = validate_lesson(lesson, context_digest=digest(origin))
    raw = {
        "transfer_kind": PROPOSAL_TRANSFER,
        "lesson": original,
        "origin_context": origin,
        "origin_context_digest": digest(origin),
        "destination_context_digest": digest(destination),
        "evidence_digest": original["evidence_digest"],
    }
    raw["prior_digest"] = digest(raw)
    return _copy(raw, 262144)


def validate_proposal_prior(
    value: Mapping[str, Any], *, destination_context: Mapping[str, Any]
) -> dict[str, Any]:
    raw = _copy(dict(value), 262144)
    if set(raw) != {
        "transfer_kind",
        "lesson",
        "origin_context",
        "origin_context_digest",
        "destination_context_digest",
        "evidence_digest",
        "prior_digest",
    }:
        raise GameLearningError("proposal prior schema differs")
    expected = make_proposal_prior(
        raw["lesson"],
        origin_context=raw["origin_context"],
        destination_context=destination_context,
    )
    if raw != expected:
        raise GameLearningError("proposal prior original evidence or destination binding differs")
    return raw


class StudioLearningCampaign:
    """Episode-bounded optimization with an atomic committed-round protocol."""

    def __init__(
        self,
        request: GameEnvironmentRequest,
        config: CampaignConfig,
        context: Mapping[str, Any],
        lineage: Mapping[str, Any],
        policy_snapshot: Mapping[str, Any] | None = None,
        snapshot: Mapping[str, Any] | None = None,
        lessons: Sequence[Mapping[str, Any]] = (),
        proposal_priors: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        if not isinstance(request, GameEnvironmentRequest) or not isinstance(config, CampaignConfig):
            raise GameLearningError("typed studio request/config required")
        execution = request.as_dict()
        execution["max_steps"] = config.episode_steps
        request = GameEnvironmentRequest.from_dict(execution)
        self.request, self.config = request, config
        self.context = _copy(dict(context), 65536)
        if not all(
            isinstance(self.context.get(k), str) and 1 <= len(self.context[k]) <= 256 for k in CONTEXT_FIELDS
        ):
            raise GameLearningError("explicit target/genre/engine/source/code context required")
        if self.context["target_id"] != request.target_id:
            raise GameLearningError("campaign target differs from execution request")
        for name in ("source_digest", "code_digest"):
            value = self.context[name]
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise GameLearningError("campaign source/code identity is not SHA-256")
        self.context_digest = digest(self.context)
        if len(proposal_priors) > 128:
            raise GameLearningError("proposal prior count exceeds128")
        self.proposal_priors = [
            validate_proposal_prior(v, destination_context=self.context) for v in proposal_priors
        ]
        _copy(self.proposal_priors, 262144)
        if len({v["prior_digest"] for v in self.proposal_priors}) != len(self.proposal_priors):
            raise GameLearningError("duplicate proposal prior")
        self.lineage = _copy(dict(lineage), 65536)
        if not self.lineage or self.lineage.get("rights_acknowledged") is False:
            raise GameLearningError("explicit admitted source lineage required")
        self.implementation_digest = _implementation()
        initial_policy = None if policy_snapshot is None else _copy(policy_snapshot)
        self.binding = {
            "request_digest": request.digest,
            "config": config.as_dict(),
            "context_digest": self.context_digest,
            "lineage_digest": digest(self.lineage),
            "implementation_digest": self.implementation_digest,
            "proposal_priors_digest": digest(self.proposal_priors),
            "initial_policy_digest": (
                None if initial_policy is None else initial_policy.get("snapshot_digest")
            ),
        }
        self.campaign_id = "studio-" + digest(self.binding)[:40]
        self.cursor = 0
        self.cumulative_steps = 0
        self.champion = request
        self.champion_policy = initial_policy
        self.bandit_state = {}
        self.counterexamples = []
        self.history_digest = digest({"campaign_id": self.campaign_id, "genesis": self.binding})
        self.last_round_digest = None
        self.lesson_count = 0
        self.recent_lessons = []
        if len(lessons) > 128:
            raise GameLearningError("imported lesson count exceeds128")
        seen = set()
        for value in lessons:
            lesson = validate_lesson(value, context_digest=self.context_digest)
            if lesson["lesson_digest"] in seen:
                raise GameLearningError("duplicate imported lesson")
            seen.add(lesson["lesson_digest"])
            self.recent_lessons.append(lesson)
        self.recent_lessons = self.recent_lessons[-64:]
        if snapshot is not None:
            self._restore(snapshot)
        self._validate_policy(self.champion, self.champion_policy)
        self._executing = False
        self._lock = threading.Lock()

    @staticmethod
    def _spec(request: GameEnvironmentRequest):
        env = request.build()
        try:
            return env.spec
        finally:
            close = getattr(env, "close", None)
            if callable(close):
                close()

    def _validate_policy(self, request, policy):
        if policy is not None:
            GamePolicyLearner.from_snapshot(policy, expected_spec=self._spec(request))

    def snapshot(self) -> dict[str, Any]:
        raw = {
            "schema_version": CAMPAIGN_SCHEMA,
            "campaign_id": self.campaign_id,
            "binding": self.binding,
            "cursor": self.cursor,
            "round_limit": self.config.round_limit,
            "cumulative_steps": self.cumulative_steps,
            "champion_request": self.champion.as_dict(),
            "champion_request_digest": self.champion.digest,
            "champion_policy": self.champion_policy,
            "champion_policy_digest": (
                None if self.champion_policy is None else self.champion_policy["snapshot_digest"]
            ),
            "history_digest": self.history_digest,
            "last_round_digest": self.last_round_digest,
            "lesson_count": self.lesson_count,
            "recent_lessons": self.recent_lessons,
            "proposal_priors": self.proposal_priors,
            "bandit_state": self.bandit_state,
            "counterexamples": self.counterexamples,
        }
        raw["snapshot_digest"] = digest(raw)
        return _copy(raw)

    def _restore(self, value):
        raw = _copy(dict(value))
        expected = {
            "schema_version",
            "campaign_id",
            "binding",
            "cursor",
            "round_limit",
            "cumulative_steps",
            "champion_request",
            "champion_request_digest",
            "champion_policy",
            "champion_policy_digest",
            "history_digest",
            "last_round_digest",
            "lesson_count",
            "recent_lessons",
            "proposal_priors",
            "bandit_state",
            "counterexamples",
            "snapshot_digest",
        }
        if (
            set(raw) != expected
            or raw["schema_version"] != CAMPAIGN_SCHEMA
            or raw["campaign_id"] != self.campaign_id
            or raw["binding"] != self.binding
        ):
            raise GameLearningError("campaign snapshot/source/code/config binding differs")
        if raw["snapshot_digest"] != digest({k: v for k, v in raw.items() if k != "snapshot_digest"}):
            raise GameLearningError("campaign snapshot digest differs")
        if raw["proposal_priors"] != self.proposal_priors:
            raise GameLearningError("campaign proposal provenance differs")
        self.cursor = _int(raw["cursor"], "campaign cursor", 0, self.config.round_limit)
        if raw["round_limit"] != self.config.round_limit:
            raise GameLearningError("campaign round admission differs")
        episodes = self.config.episodes_per_round + 4 * self.config.evaluation_seeds
        self.cumulative_steps = _int(
            raw["cumulative_steps"],
            "campaign actual steps",
            self.cursor * episodes,
            self.cursor * episodes * self.config.episode_steps,
        )
        self.lesson_count = _int(raw["lesson_count"], "campaign lessons", 0, 400000)
        if self.lesson_count != self.cursor * 4:
            raise GameLearningError("committed lesson count differs from actual round cursor")
        state = raw["bandit_state"]
        if not isinstance(state, dict) or len(state) > 128:
            raise GameLearningError("campaign bandit capacity differs")
        total = 0
        admitted_arms = {arm["id"] for arm in self.proposal_catalog(self.request)}
        for arm, row in state.items():
            if (
                not isinstance(arm, str)
                or len(arm) > 128
                or arm not in admitted_arms
                or not isinstance(row, dict)
                or set(row) != {"trials", "accepted", "reward_sum"}
            ):
                raise GameLearningError("campaign bandit schema differs")
            trials = _int(row["trials"], "proposal trials", 1, self.cursor)
            _int(row["accepted"], "accepted proposal trials", 0, trials)
            reward = row["reward_sum"]
            if type(reward) not in (int, float) or not math.isfinite(reward) or abs(reward) > trials + 1e-9:
                raise GameLearningError("proposal reward accounting differs")
            total += trials
        if total != self.cursor:
            raise GameLearningError("bandit trials differ from committed round cursor")
        self.bandit_state = state
        if not isinstance(raw["counterexamples"], list) or len(raw["counterexamples"]) > 16:
            raise GameLearningError("counterexample capacity differs")
        self.counterexamples = _copy(raw["counterexamples"], 524288)
        seen_counterexamples = set()
        for record in self.counterexamples:
            if not isinstance(record, dict) or set(record) != {
                "round_index",
                "seed",
                "request_digest",
                "environment_digest",
                "policy_digest",
                "reason",
                "return",
                "trace_digest",
                "trace_format",
                "trace",
                "record_digest",
            }:
                raise GameLearningError("counterexample schema differs")
            _int(record["round_index"], "counterexample round", 1, self.cursor)
            _int(record["seed"], "counterexample seed", 0, 2**63 - 1)
            if (
                record["reason"] not in ("observed_death_regression", "rejected_candidate_comparison")
                or type(record["return"]) not in (int, float)
                or not math.isfinite(record["return"])
                or abs(record["return"]) > 4096 * 1e9 * 32
            ):
                raise GameLearningError("counterexample measured outcome differs")
            if record["trace_format"] not in ("skeleton.game.trace.v1", "length_prefixed_transition_sha256"):
                raise GameLearningError("counterexample trace representation differs")
            if (
                record["record_digest"]
                != digest({k: v for k, v in record.items() if k not in ("record_digest", "trace")})
                or record["record_digest"] in seen_counterexamples
            ):
                raise GameLearningError("counterexample evidence differs or repeats")
            for name in ("request_digest", "environment_digest", "policy_digest", "trace_digest"):
                value = record[name]
                if (
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(c not in "0123456789abcdef" for c in value)
                ):
                    raise GameLearningError("counterexample evidence identity differs")
            if record["trace"] is not None:
                trace = record["trace"]
                if not isinstance(trace, dict) or record["trace_format"] != "skeleton.game.trace.v1":
                    raise GameLearningError("retained counterexample must be an exact full trace")
                if (
                    trace.get("trace_digest") != record["trace_digest"]
                    or digest({k: v for k, v in trace.items() if k != "trace_digest"})
                    != record["trace_digest"]
                    or trace.get("seed") != record["seed"]
                    or trace.get("environment", {}).get("environment_digest") != record["environment_digest"]
                ):
                    raise GameLearningError("retained full counterexample trace differs")
            seen_counterexamples.add(record["record_digest"])
        champion = GameEnvironmentRequest.from_dict(raw["champion_request"])
        if (
            champion.target_id != self.request.target_id
            or champion.kind != self.request.kind
            or champion.digest != raw["champion_request_digest"]
        ):
            raise GameLearningError("champion target/request identity differs")
        if (
            self.request.kind not in ("successor", "console_editor")
            and champion.digest != self.request.digest
        ):
            raise GameLearningError(
                "read-only native/reference campaign cannot substitute its admitted source"
            )
        # An admitted rematerialized native root is operational, not semantic.
        self.champion = self.request if champion.digest == self.request.digest else champion
        self.champion_policy = raw["champion_policy"]
        actual = None if self.champion_policy is None else self.champion_policy.get("snapshot_digest")
        if actual != raw["champion_policy_digest"]:
            raise GameLearningError("champion policy identity differs")
        if not isinstance(raw["recent_lessons"], list) or len(raw["recent_lessons"]) > 64:
            raise GameLearningError("campaign recent lesson memory exceeds64")
        self.recent_lessons = [
            validate_lesson(v, context_digest=self.context_digest) for v in raw["recent_lessons"]
        ]
        if len({v["lesson_digest"] for v in self.recent_lessons}) != len(self.recent_lessons):
            raise GameLearningError("campaign recent lesson identities duplicate")
        for field in ("history_digest", "last_round_digest"):
            value = raw[field]
            if value is None and field == "last_round_digest" and self.cursor == 0:
                continue
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise GameLearningError("campaign history identity differs")
        self.history_digest, self.last_round_digest = raw["history_digest"], raw["last_round_digest"]

    def _seed(self, index, role):
        return int.from_bytes(
            hashlib.sha256(f"{self.config.seed}:{index}:{role}".encode()).digest()[:8], "big"
        ) % (2**63)

    def _decision(self, mechanic, *, proposed_value=None):
        own = [
            v
            for v in self.recent_lessons
            if v["role"] == "decision" and v["facts"].get("mechanic") == mechanic
        ]
        priors = [
            v
            for v in self.proposal_priors
            if v["lesson"]["role"] == "decision" and v["lesson"]["facts"].get("mechanic") == mechanic
        ]
        candidates = [(v, None) for v in own] if own else [(v["lesson"], v) for v in priors]
        if proposed_value is not None:
            rejected = [
                pair
                for pair in candidates
                if pair[0]["outcome"] == "rejected"
                and any(
                    isinstance(c, dict) and c.get("after") == proposed_value
                    for c in pair[0]["facts"].get("candidate_changes", [])
                )
            ]
            if rejected:
                return rejected[-1]
        return (None, None) if not candidates else candidates[-1]

    @staticmethod
    def _proposal_facts(prior):
        return (
            {}
            if prior is None
            else {
                "proposal_prior_digest": prior["prior_digest"],
                "proposal_origin_context_digest": prior["origin_context_digest"],
                "proposal_evidence_digest": prior["evidence_digest"],
                "transfer_kind": PROPOSAL_TRANSFER,
            }
        )

    def proposal_catalog(self, request=None):
        """Only fields actually consumed by the current typed environment."""
        request = self.champion if request is None else request
        arms = [{"id": "policy.continue", "family": "policy", "kind": "policy"}]
        if request.kind == "successor":
            spec = json.loads(request.tree["game/successor/spec.json"])
            groups = {"movement", "combat", "resources", "adventure", "fishing", "farming", "camera"}
            excluded = {
                "movement.gravity",
                "movement.max_fall_speed",
                "combat.enemy_damage",
                "combat.damage",
                "adventure.dungeon_count",
                "fishing.fish_variants",
                "farming.crop_variants",
            }
            for path in sorted(MECHANIC_CATALOG):
                group, key = path.split(".")
                if (
                    group in groups
                    and path not in excluded
                    and type(spec.get("mechanics", {}).get(group, {}).get(key)) in (int, float)
                ):
                    arms.append({"id": path, "family": "mechanics", "kind": "numeric", "path": path})
            world = spec["world"]
            for name in ("crop_variants", "fish_variants"):
                if world.get(name):
                    arms.append(
                        {
                            "id": "economy." + name + ".value",
                            "family": "economy",
                            "kind": "variant_value",
                            "section": name,
                        }
                    )
            if world.get("crop_variants"):
                arms.append(
                    {"id": "economy.crop_variants.seed_cost", "family": "economy", "kind": "seed_cost"}
                )
            if world.get("enemies"):
                arms.extend(
                    [
                        {"id": "entities.enemy_speed", "family": "entities", "kind": "enemy_speed"},
                        {"id": "entities.enemy_health", "family": "entities", "kind": "enemy_health"},
                    ]
                )
            if world.get("checkpoints"):
                arms.append({"id": "layout.checkpoint_shift", "family": "layout", "kind": "checkpoint_shift"})
            if world.get("collectibles"):
                arms.append(
                    {"id": "layout.collectible_shift", "family": "layout", "kind": "collectible_shift"}
                )
            if world.get("terrain"):
                arms.append({"id": "map.terrain_path", "family": "layout", "kind": "terrain_path"})
            if spec.get("fidelity", {"profile": "pixel"})["profile"] != "cinematic":
                arms.append({"id": "fidelity.profile", "family": "fidelity", "kind": "fidelity"})
        elif request.kind == "studio":
            from .game_studio_environment import parse_studio_source
            from skeleton.ai.game_builder.system_editors import editor_spec

            source = parse_studio_source(json.loads(request.tree["game/studio/session.json"]))
            for field in editor_spec(source["editor"])["fields"]:
                key = field["key"]
                if key == "homebrew_only" or field["kind"] not in ("int", "bool", "enum"):
                    continue
                if field["kind"] == "int" and field["minimum"] == field["maximum"]:
                    continue
                if field["kind"] == "enum" and len(field["options"]) < 2:
                    continue
                arms.append({
                    "id": "studio." + key,
                    "family": "mechanics",
                    "kind": "studio_rule_setting",
                    "key": key,
                    "field_kind": field["kind"],
                    "minimum": field["minimum"],
                    "maximum": field["maximum"],
                    "options": field["options"],
                })
        elif request.kind == "console_editor":
            from .game_console_editor import ConsoleProject

            document = ConsoleProject.from_files(request.tree, target_id=request.target_id).as_dict()
            bounds = {
                "speed": (1, 600, False),
                "gravity": (0, 4000, False),
                "jump_speed": (1, 1000, False),
                "attack_damage": (1, 100, True),
                "attack_range": (1, 256, False),
                "day_length_seconds": (1, 3600, False),
                "season_days": (1, 365, True),
                "crop_growth_days": (1, 90, True),
                "fishing_probability": (0, 1, False),
            }
            for key, values in bounds.items():
                if document["config"]["movement_mode"] != "platformer" and key in ("gravity", "jump_speed"):
                    continue
                arms.append(
                    {
                        "id": "config." + key,
                        "family": (
                            "economy"
                            if key
                            in (
                                "day_length_seconds",
                                "season_days",
                                "crop_growth_days",
                                "fishing_probability",
                            )
                            else "mechanics"
                        ),
                        "kind": "editor_numeric",
                        "key": key,
                        "bounds": list(values),
                    }
                )
            if any(row["kind"] == "enemy" for row in document["entities"]):
                arms.append(
                    {"id": "entities.enemy_health", "family": "entities", "kind": "editor_enemy_health"}
                )
        return arms

    def _select_proposal(self, index):
        arms = self.proposal_catalog()
        if self.champion_policy is not None and "policy.continue" not in self.bandit_state:
            arm = next(a for a in arms if a["id"] == "policy.continue")
            return arm, {
                "algorithm": "deterministic_ucb1",
                "arm_id": arm["id"],
                "family": arm["family"],
                "prior_trials": 0,
                "prior_accepted": 0,
                "selection_score": None,
                "eligible_arm_count": len(arms),
                "selection_reason": "first_actual_admitted_parent_continuation",
            }
        total = max(1, self.cursor)
        scored = []
        for arm in arms:
            row = self.bandit_state.get(arm["id"], {"trials": 0, "accepted": 0, "reward_sum": 0.0})
            score = (
                None
                if row["trials"] == 0
                else row["reward_sum"] / row["trials"] + math.sqrt(2 * math.log(total + 1) / row["trials"])
            )
            tie = self._seed(index, "bandit:" + arm["id"])
            scored.append((row["trials"] == 0, score or 0.0, -tie, arm, row))
        _, score, _, arm, row = max(scored, key=lambda item: item[:3])
        return arm, {
            "algorithm": "deterministic_ucb1",
            "arm_id": arm["id"],
            "family": arm["family"],
            "prior_trials": row["trials"],
            "prior_accepted": row["accepted"],
            "selection_score": None if not row["trials"] else score,
            "eligible_arm_count": len(arms),
        }

    def _mutate(self, index):
        arm, selection = self._select_proposal(index)
        rng = random.Random(self._seed(index, "mutation:" + arm["id"]))
        request = self.champion
        tree = dict(request.tree or {})
        facts = {
            "supported": False,
            "strategy": "continue_actual_current_policy",
            "mechanic": arm["id"],
            "changes": [],
            "proposal_selection": selection,
        }
        if arm["kind"] == "policy":
            return request, facts
        decision, prior = self._decision(arm["id"])
        direction = 1 if rng.random() >= 0.5 else -1
        if (
            decision is not None
            and type(decision["facts"].get("direction")) is int
            and decision["facts"]["direction"] in (-1, 1)
        ):
            known = decision["facts"]["direction"]
            direction = -known if decision["outcome"] == "rejected" else known
        facts.update(
            supported=True,
            strategy="bandit_selected_typed_mutation",
            direction=direction,
            **self._proposal_facts(prior),
        )
        changes = facts["changes"]

        def change(container, key, path, low, high, integer=False):
            old = container[key]
            new = (
                old + direction * max(1, round(abs(old) * 0.05))
                if integer
                else old + direction * max(abs(old) * 0.05, (high - low) * 0.001)
            )
            new = max(low, min(high, new))
            if integer:
                new = int(new)
            container[key] = new
            changes.append({"path": path, "before": old, "after": new})

        if request.kind == "successor":
            from .game_successor_runtime import emit_successor_project

            spec = json.loads(tree["game/successor/spec.json"])
            world, kind = spec["world"], arm["kind"]
            if kind == "numeric":
                group, key = arm["path"].split(".")
                low, high, _, _, integer = MECHANIC_CATALOG[arm["path"]]
                change(spec["mechanics"][group], key, arm["path"], low, high, integer)
            elif kind in ("variant_value", "seed_cost"):
                section = arm.get("section", "crop_variants")
                key = "seed_cost" if kind == "seed_cost" else "value"
                for row in world[section]:
                    change(row, key, "world." + section + "." + row["id"] + "." + key, 1, 100, True)
            elif kind in ("enemy_speed", "enemy_health"):
                key = "hp" if kind == "enemy_health" else "speed"
                for row in world["enemies"]:
                    row.setdefault(key, 3 if key == "hp" else 40)
                    change(
                        row,
                        key,
                        "world.enemies." + row["id"] + "." + key,
                        1 if key == "hp" else 0,
                        64 if key == "hp" else 200,
                        key == "hp",
                    )
            elif kind in ("checkpoint_shift", "collectible_shift"):
                section = "checkpoints" if kind == "checkpoint_shift" else "collectibles"
                row = world[section][rng.randrange(len(world[section]))]
                old = row["x"]
                row["x"] = max(0, min(world["width"] - 32, old + direction * world.get("tile_size", 32)))
                changes.append(
                    {"path": "world." + section + "." + row["id"] + ".x", "before": old, "after": row["x"]}
                )
            elif kind == "terrain_path":
                rows = world["terrain"]
                tile = world.get("tile_size", 32)
                x, y = int(world["spawn"][0] / tile) + 2, int(world["spawn"][1] / tile)
                y, x = min(len(rows) - 1, y), min(len(rows[0]) - 1, x)
                old = rows[y][x]
                if old in "03456":
                    new = "4" if old != "4" else "0"
                    rows[y] = rows[y][:x] + new + rows[y][x + 1 :]
                    changes.append({"path": f"world.terrain[{y}][{x}]", "before": old, "after": new})
            elif kind == "fidelity":
                profiles = ("pixel", "enhanced", "cinematic")
                old = spec.get("fidelity", {"profile": "pixel"})["profile"]
                new = profiles[min(2, profiles.index(old) + 1)]
                decision, prior = self._decision(arm["id"], proposed_value=new)
                rejected = (
                    decision is not None
                    and decision["outcome"] == "rejected"
                    and any(
                        isinstance(c, dict) and c.get("after") == new
                        for c in decision["facts"].get("candidate_changes", [])
                    )
                )
                if rejected:
                    facts.update(
                        supported=False,
                        proposal_rejected=True,
                        strategy="remembered_fidelity_rejection",
                        **self._proposal_facts(prior),
                    )
                    return request, facts
                spec["fidelity"] = {"profile": new}
                changes.append({"path": "fidelity.profile", "before": old, "after": new})
                facts["subjective_quality_improvement_claim"] = False
            tree.update(emit_successor_project(spec))
        elif request.kind == "console_editor":
            from .game_console_editor import ConsoleProject

            project = ConsoleProject.from_files(tree, target_id=request.target_id)
            document = project.as_dict()
            if arm["kind"] == "editor_numeric":
                low, high, integer = arm["bounds"]
                change(document["config"], arm["key"], arm["id"], low, high, integer)
            else:
                for row in document["entities"]:
                    if row["kind"] == "enemy":
                        change(row["properties"], "health", "entities." + row["id"] + ".health", 1, 100, True)
            tree = ConsoleProject(document, tree).export_files()
        elif request.kind == "studio":
            from .game_studio_environment import (
                parse_studio_source, studio_request_tree,
            )
            from .game_studio_rule_curriculum import (
                PROPOSAL_SCHEMA, RuleCurriculumError, apply_rule_proposal, _sha,
            )

            source = parse_studio_source(json.loads(tree["game/studio/session.json"]))
            key = arm["key"]
            old = source["settings"][key]
            if arm["field_kind"] == "int":
                minimum, maximum = arm["minimum"], arm["maximum"]
                increment = max(1, round(max(1, abs(old)) * 0.08))
                new = max(minimum, min(maximum, old + direction * increment))
                if new == old:
                    new = max(minimum, min(maximum, old - direction * increment))
                operation = {"scope":"settings", "path":key, "op":"set", "value":new}
            elif arm["field_kind"] == "bool":
                new = not old
                operation = {"scope":"settings", "path":key, "op":"toggle", "value":None}
            else:
                choices = arm["options"]
                new = choices[(choices.index(old) + direction) % len(choices)]
                operation = {"scope":"settings", "path":key, "op":"set", "value":new}
            proposal = {
                "schema_version": PROPOSAL_SCHEMA,
                "proposal_id": "campaign-" + str(index).zfill(6),
                "base_digest": _sha(source),
                "reason": "Explore a distinct original-game mechanic under verified replay.",
                "scene_seed": None if source["scene"] is None else source["scene"]["seed"],
                "operations": [operation],
            }
            try:
                changed = apply_rule_proposal(source, proposal)
            except RuleCurriculumError as exc:
                facts.update(
                    supported=False,
                    proposal_rejected=True,
                    strategy="studio_rule_violates_canonical_bounds",
                    validation_error=str(exc)[:256],
                )
                return request, facts
            tree = studio_request_tree(changed)
            changes.append({
                "path":"game/studio/session.json/settings/" + key,
                "before":old,"after":new,
                "source_before_digest":_sha(source),
                "source_after_digest":_sha(changed),
                "rule_proposal_digest":_sha(proposal),
                "source_rule_validated":True,
            })
            facts["strategy"]="bandit_selected_source_verified_game_rule"
            facts["model_weights_modified"]=False
            facts["runtime_engine_changed"]=False
        raw = request.as_dict()
        raw["tree"] = tree
        request = GameEnvironmentRequest.from_dict(raw)
        facts["proposal_rejected"] = not changes or request.digest == self.champion.digest
        return request, facts

    def _play(self, request, seed, policy, *, jitter, cancel, authorize):
        _guard(cancel, authorize)
        env = request.build(cancel=cancel)
        try:
            observation = env.reset(seed)
            controller = None if policy is None else GamePolicyLearner.from_snapshot(policy)
            if controller is not None:
                before, after = controller.descriptor, env.spec.as_dict()
                if any(before[k] != after[k] for k in ("actions", "observation_bins", "reward_components")):
                    raise GameLearningError("frozen policy transfer changed action/bin/reward semantics")
            rng = random.Random(seed ^ 0xA0761D6478BD642F)
            total, steps, step_seconds = 0.0, 0, 0.0
            actions, events, states = {}, {}, set()
            components = {key: 0.0 for key in env.spec.reward_components}
            trace_steps, trace_bytes = [], 0
            stream = hashlib.sha256()
            initial_observation = dict(observation)
            render_start = time.perf_counter()
            first = env.preview() if hasattr(env, "preview") else None
            first_render_ms = (time.perf_counter() - render_start) * 1000
            for sequence in range(1, self.config.episode_steps + 1):
                _guard(cancel, authorize)
                state = tuple(
                    sum(value >= bound for bound in env.spec.observation_bins[key])
                    for key, value in sorted(observation.items())
                )
                states.add(state)
                action = (
                    env.spec.actions[rng.randrange(len(env.spec.actions))]
                    if controller is None
                    else controller.predict(observation)["action"]
                )
                if jitter and sequence % 11 == 0:
                    action = env.spec.actions[rng.randrange(len(env.spec.actions))]
                started = time.perf_counter()
                step = env.step(action)
                step_seconds += time.perf_counter() - started
                values = dict(step.reward_components)
                if set(values) != set(components) or any(
                    type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e9
                    for v in values.values()
                ):
                    raise GameLearningError("actual evaluation reward components differ")
                reward = math.fsum(values.values())
                data = {
                    "sequence": sequence,
                    "observation": observation,
                    "action": action,
                    "next_observation": step.observation,
                    "reward": reward,
                    "reward_components": values,
                    "terminated": step.terminated,
                    "truncated": step.truncated
                    or (sequence == self.config.episode_steps and not step.terminated),
                }
                if step.info:
                    data["info"] = dict(step.info)
                if step.transition_digest:
                    data["transition_digest"] = step.transition_digest
                data = _copy_json(data, limit=65536)
                encoded = canonical(data, limit=65536)
                stream.update(len(encoded).to_bytes(4, "big"))
                stream.update(encoded)
                if trace_steps is not None:
                    trace_bytes += len(encoded)
                    if trace_bytes <= 230000:
                        trace_steps.append(_copy(data, 65536))
                    else:
                        trace_steps = None
                observation = step.observation
                total += reward
                for key, value in values.items():
                    components[key] += value
                steps += 1
                actions[action] = actions.get(action, 0) + 1
                for event in step.info.get("events", ()):
                    if isinstance(event, str) and len(event) <= 128:
                        events[event] = events.get(event, 0) + 1
                if step.terminated or step.truncated:
                    break
            render_start = time.perf_counter()
            last = env.preview() if hasattr(env, "preview") else None
            last_render_ms = (time.perf_counter() - render_start) * 1000
            from .game_studio_review import analyze_frame_sequence

            observed_sequence = analyze_frame_sequence(
                [
                    {
                        "step": 0,
                        "frame": first,
                        "observation": initial_observation,
                        "render_wall_ms": first_render_ms,
                    },
                    {
                        "step": steps,
                        "frame": last,
                        "observation": dict(observation),
                        "step_wall_ms": step_seconds * 1000 / steps,
                        "render_wall_ms": last_render_ms,
                    },
                ],
                source_identity={
                    "request_digest": request.digest,
                    "environment_digest": env.spec.environment_digest,
                    "seed": seed,
                    "policy_digest": None if policy is None else policy["snapshot_digest"],
                },
            )
            info = dict(step.info)
            trace = None
            if trace_steps is not None:
                trace = {
                    "schema_version": "skeleton.game.trace.v1",
                    "environment": env.spec.as_dict(),
                    "episode_id": "studio-eval:"
                    + digest(
                        {
                            "seed": seed,
                            "request": request.digest,
                            "policy": None if policy is None else policy["snapshot_digest"],
                            "jitter": jitter,
                        }
                    )[:40],
                    "seed": seed,
                    "source_lineage": self.lineage,
                    "transitions": trace_steps,
                    "return": math.fsum(t["reward"] for t in trace_steps),
                    "steps": steps,
                }
                trace["trace_digest"] = digest(trace)
                if len(canonical(trace, limit=524288)) > 262144:
                    trace = None
            entropy = -math.fsum((count / steps) * math.log(count / steps) for count in actions.values())
            entropy /= math.log(len(env.spec.actions)) if len(env.spec.actions) > 1 else 1
            dead = info.get("dead") is True or observation.get("alive") == 0 or observation.get("health") == 0
            return {
                "seed": seed,
                "environment_digest": env.spec.environment_digest,
                "policy_digest": None if policy is None else policy["snapshot_digest"],
                "controller": "seeded_random" if controller is None else "frozen_q_policy",
                "input_perturbation": "one_random_action_every11steps" if jitter else "none",
                "steps": steps,
                "return": total,
                "reward_components": components,
                "actions": actions,
                "events": events,
                "observed_states": len(states),
                "state_coverage": len(states) / steps,
                "action_entropy": entropy,
                "mean_step_ms": step_seconds * 1000 / steps,
                "mean_render_ms": (first_render_ms + last_render_ms) / 2,
                "sequence_review": {
                    k: observed_sequence[k]
                    for k in (
                        "schema_version",
                        "status",
                        "metrics",
                        "findings",
                        "temporal_events",
                        "limitations",
                        "review_digest",
                    )
                },
                "won": info.get("won") is True
                or info.get("success") is True
                or info.get("goal_reached") is True,
                "dead": dead,
                "first_frame": self._frame(first),
                "last_frame": self._frame(last),
                "trace_digest": stream.hexdigest() if trace is None else trace["trace_digest"],
                "trace_format": (
                    "length_prefixed_transition_sha256" if trace is None else "skeleton.game.trace.v1"
                ),
                "_trace": trace,
            }
        finally:
            close = getattr(env, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _frame(frame):
        if frame is None:
            return {"available": False}
        if not isinstance(frame, Mapping):
            raise GameLearningError("actual frame projection differs")
        uri = frame.get("data_uri")
        if not isinstance(uri, str) or not uri.startswith("data:image/png;base64,"):
            return {"available": False, "reason": "no_supported_png_projection"}
        if len(uri) > 700000:
            raise GameLearningError("actual frame exceeds bounded preview bytes")
        try:
            raw = base64.b64decode(uri.split(",", 1)[1], validate=True)
        except ValueError as exc:
            raise GameLearningError("actual frame base64 differs") from exc
        if len(raw) > 524288 or len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise GameLearningError("actual frame PNG boundary differs")
        width, height = struct.unpack("!II", raw[16:24])
        if not 1 <= width <= 2048 or not 1 <= height <= 2048 or width * height > 1048576:
            raise GameLearningError("actual preview raster dimensions exceed bounds")
        actual = hashlib.sha256(raw).hexdigest()
        if frame.get("png_digest") not in (None, actual):
            raise GameLearningError("actual preview receipt differs")
        from .game_console_assets import decode_png

        decoded_width, decoded_height, pixels = decode_png(raw)
        if (decoded_width, decoded_height) != (width, height):
            raise GameLearningError("actual preview decoded dimensions differ")
        stride = max(1, math.ceil(math.sqrt(width * height / 65536)))
        palette = [0] * 4096
        luminance = [0] * 256
        sampled = opaque = edge_pairs = edges = 0
        previous_row = []
        for y in range(0, height, stride):
            row = []
            for x in range(0, width, stride):
                offset = (y * width + x) * 4
                r, g, b, alpha = pixels[offset : offset + 4]
                sampled += 1
                if alpha >= 16:
                    opaque += 1
                    palette[(r >> 4) * 256 + (g >> 4) * 16 + (b >> 4)] += 1
                    value = (54 * r + 183 * g + 19 * b) >> 8
                    luminance[value] += 1
                else:
                    value = 0
                if row:
                    edge_pairs += 1
                    edges += abs(value - row[-1]) >= 12
                if previous_row:
                    edge_pairs += 1
                    edges += abs(value - previous_row[len(row)]) >= 12
                row.append(value)
            previous_row = row
        occupied = sum(count > 0 for count in palette)
        levels = [index for index, count in enumerate(luminance) if count]
        contrast = 0 if not levels else levels[-1] - levels[0]
        dominant = 1.0 if not opaque else max(palette) / opaque
        edge_density = edges / max(1, edge_pairs)
        visual = {
            "sampled_pixels": sampled,
            "opaque_fraction": opaque / max(1, sampled),
            "occupied_quantized_palette_bins": occupied,
            "palette_capacity": 4096,
            "luminance_range": contrast,
            "dominant_color_fraction": dominant,
            "edge_density": edge_density,
            "sample_stride": stride,
            "flat_raster": occupied < 2 or contrast < 4,
            "readable_signal": opaque / max(1, sampled) >= 0.02
            and occupied >= 2
            and contrast >= 4
            and dominant <= 0.999
            and edge_density >= 0.0001,
            "classification": "actual_bounded_pixel_statistics_not_subjective_aesthetics",
        }
        return {
            "available": True,
            "width": width,
            "height": height,
            "png_bytes": len(raw),
            "png_digest": actual,
            "pixel_digest": frame.get("pixel_digest"),
            "art_digest": frame.get("art_digest"),
            "fidelity": _copy(frame.get("fidelity"), 2048),
            "visual_metrics": visual,
            "classification": "measured_raster_identity_and_dimensions_not_subjective_art_quality",
        }

    def _dragon(self, request, play):
        tree = request.tree or {}
        size = sum(len(v.encode()) for v in tree.values())
        checks = {
            "source_request_digest": request.digest,
            "project_bytes": size,
            "bounded_project": size <= 4 * 1024 * 1024,
            "actual_frame_available": play["last_frame"]["available"],
            "source_lineage_digest": digest(self.lineage),
            "originality": (
                "original_authored_successor"
                if request.kind == "successor"
                else "source_owner_admitted_content_not_semantic_originality_proof"
            ),
            "model_critic_executed": False,
            "visual_metrics": play["last_frame"].get("visual_metrics"),
            "measured_sequence_review": play["sequence_review"],
        }
        if request.kind == "successor":
            from .game_successor import validate_successor_routes

            spec = json.loads(tree["game/successor/spec.json"])
            try:
                checks["layout"] = validate_successor_routes(spec)
                checks["source_rules_passed"] = True
            except ValueError as exc:
                checks["layout"] = {"classification": "analytic_geometry_rejection", "error": str(exc)[:512]}
                checks["source_rules_passed"] = False
            crop_variants = spec["world"].get("crop_variants", [])
            checks["economy"] = {
                "classification": "authored_numeric_constraint_not_measured_profitability",
                "crop_seed_value_ordering": all(row["value"] > row["seed_cost"] for row in crop_variants),
                "variant_count": len(crop_variants),
            }
            checks["source_rules_passed"] = (
                checks["source_rules_passed"] and checks["economy"]["crop_seed_value_ordering"]
            )
        elif request.kind == "console_editor":
            from .game_console_editor import ConsoleProject, inspect_console_project

            project = ConsoleProject.from_files(tree, target_id=request.target_id)
            report = inspect_console_project(project)
            checks["layout"] = {
                "document_digest": project.digest,
                "validation": report,
                "classification": "typed_source_capacity_rules_not_hardware_execution_proof",
            }
            checks["source_rules_passed"] = not any(
                row["status"] in ("blocked", "fail") for row in report["checks"]
            )
            for row in report["checks"]:
                if row["id"] == "navigation" and row["status"] == "measured_grid":
                    checks["source_rules_passed"] = (
                        checks["source_rules_passed"]
                        and not row["metrics"]["spawn_blocked"]
                        and all(row["metrics"]["goal_reachability"].values())
                    )
        else:
            checks["layout"] = {
                "available": False,
                "reason": "opaque_native_source_not_automatically_rewritten",
            }
            checks["source_rules_passed"] = True
        checks["passed"] = (
            checks["bounded_project"]
            and checks["actual_frame_available"]
            and bool((checks["visual_metrics"] or {}).get("readable_signal"))
            and checks["source_rules_passed"]
        )
        checks["report_digest"] = digest(checks)
        return checks

    @staticmethod
    def _objectives(plays):
        count = len(plays)
        return {
            "return": math.fsum(p["return"] for p in plays) / count,
            "completion": sum(p["won"] for p in plays) / count,
            "survival": 1 - sum(p["dead"] for p in plays) / count,
            "coverage": math.fsum(p["state_coverage"] for p in plays) / count,
            "diversity": math.fsum(p["action_entropy"] for p in plays) / count,
        }

    def _round(self, index, cancel, authorize):
        _guard(cancel, authorize)
        if _implementation() != self.implementation_digest:
            raise GameLearningError("studio implementation changed during campaign")
        try:
            candidate, mutation = self._mutate(index)
        except (ValueError, KeyError) as exc:
            arm, selection = self._select_proposal(index)
            candidate = self.champion
            mutation = {
                "supported": False,
                "proposal_rejected": True,
                "strategy": "typed_proposal_failed_validation",
                "mechanic": arm["id"],
                "changes": [],
                "proposal_selection": selection,
                "validation_error": str(exc)[:512],
            }
        candidate_spec = self._spec(candidate)
        champion_spec = (
            candidate_spec if candidate.digest == self.champion.digest else self._spec(self.champion)
        )
        learning_config = GameLearningConfig(
            seed=self._seed(index, "q"),
            max_updates=max(1, self.config.episodes_per_round * self.config.episode_steps),
            max_episodes=self.config.episodes_per_round,
            max_states=4096,
            epsilon=max(0.05, 0.3 * (0.995 ** min(self.cursor, 10000))),
        )
        parent = self.champion_policy if candidate.digest == self.champion.digest else None
        if parent is not None:
            model = GamePolicyLearner.fork(
                parent,
                newpolicy_id=f"{self.campaign_id}-r{index}",
                newsource_lineage=self.lineage,
                config=learning_config,
                expected_spec=candidate_spec,
            )
        else:
            model = GamePolicyLearner(
                candidate_spec,
                learning_config,
                policy_id=f"{self.campaign_id}-r{index}",
                source_lineage=self.lineage,
            )
        inherited_training = set(model.snapshot()["training_seeds"])
        counterexamples = [
            r
            for r in self.counterexamples
            if r["environment_digest"] == candidate_spec.environment_digest
            and r["seed"] not in inherited_training
        ]
        replay_count = (
            0
            if self.config.curriculum == "fresh"
            else min(
                len(counterexamples),
                self.config.episodes_per_round if self.config.curriculum == "counterexample" else 1,
            )
        )
        chosen = []
        for record in reversed(counterexamples):
            if record["seed"] not in {r["seed"] for r in chosen}:
                chosen.append(record)
            if len(chosen) == replay_count:
                break
        if not replay_count:
            chosen = []
        training_seeds = [r["seed"] for r in chosen]
        while len(training_seeds) < self.config.episodes_per_round:
            seed = self._seed(index, f"train-{len(training_seeds)}")
            if seed in inherited_training or seed in training_seeds:
                raise GameLearningError("campaign training seed collision")
            training_seeds.append(seed)
        trained = model.train(
            lambda: candidate.build(cancel=cancel),
            episodes=self.config.episodes_per_round,
            seeds=training_seeds,
            cancel=cancel,
            authorize=authorize,
        )
        policy = trained.snapshot
        blocked = set(policy["training_seeds"])
        if self.champion_policy is not None:
            blocked.update(self.champion_policy["training_seeds"])
        ordinary_seeds = [self._seed(index, f"heldout-{i}") for i in range(self.config.evaluation_seeds)]
        jitter_seeds = [self._seed(index, f"adversarial-{i}") for i in range(self.config.evaluation_seeds)]
        all_eval = ordinary_seeds + jitter_seeds
        if len(set(all_eval)) != len(all_eval) or blocked.intersection(all_eval):
            raise GameLearningError("campaign evaluation partitions collide with current/inherited training")
        # All scenario comparisons are read-only, seed-paired and independent.
        # Studio reference engines support concurrently isolated instances;
        # native emulator providers keep their existing sequential evaluation.
        evaluations = [
            (self.champion, seed, self.champion_policy, False, "baseline")
            for seed in ordinary_seeds
        ] + [
            (candidate, seed, policy, False, "measured")
            for seed in ordinary_seeds
        ] + [
            (self.champion, seed, self.champion_policy, True, "baseline_adv")
            for seed in jitter_seeds
        ] + [
            (candidate, seed, policy, True, "measured_adv")
            for seed in jitter_seeds
        ]

        def evaluate_one(item):
            req, sample_seed, evaluator, perturbed, role = item
            return role, self._play(
                req, sample_seed, evaluator, jitter=perturbed,
                cancel=cancel, authorize=authorize,
            )

        if self.champion.kind == "studio" and candidate.kind == "studio":
            with ThreadPoolExecutor(
                max_workers=min(4, len(evaluations)),
                thread_name_prefix="jeeves-round-evaluation",
            ) as workers:
                results = list(workers.map(evaluate_one, evaluations))
        else:
            results = [evaluate_one(item) for item in evaluations]
        grouped = {role: [] for role in (
            "baseline", "measured", "baseline_adv", "measured_adv"
        )}
        for role, execution in results:
            grouped[role].append(execution)
        baseline, measured = grouped["baseline"], grouped["measured"]
        baseline_adv, measured_adv = grouped["baseline_adv"], grouped["measured_adv"]
        if any(
            p["environment_digest"] != candidate_spec.environment_digest for p in measured + measured_adv
        ) or any(
            p["environment_digest"] != champion_spec.environment_digest for p in baseline + baseline_adv
        ):
            raise GameLearningError("actual evaluation environment changed after pinned training/selection")
        dragons = [self._dragon(candidate, play) for play in measured]
        dragon = _copy(dragons[0])
        dragon["paired_seed_reviews"] = [
            {"seed": seed, "passed": d["passed"], "report_digest": d["report_digest"]}
            for seed, d in zip(ordinary_seeds, dragons, strict=True)
        ]
        dragon["passed"] = all(d["passed"] for d in dragons)
        dragon.pop("report_digest", None)
        dragon["report_digest"] = digest(dragon)
        before, after = self._objectives(baseline), self._objectives(measured)
        deltas = {key: after[key] - before[key] for key in before}
        normalized = dict(deltas)
        normalized["return"] /= max(1, abs(before["return"]))
        weighted = math.fsum(normalized[k] * self.config.objective_weights[k] for k in normalized)
        improvement = deltas["return"]
        adv_before, adv_after = self._objectives(baseline_adv), self._objectives(measured_adv)
        adversarial_delta = adv_after["return"] - adv_before["return"]
        ordinary_pairs = [c["return"] - b["return"] for b, c in zip(baseline, measured, strict=True)]
        adv_pairs = [c["return"] - b["return"] for b, c in zip(baseline_adv, measured_adv, strict=True)]
        mean_step_ms = math.fsum(p["mean_step_ms"] for p in measured + measured_adv) / (
            2 * self.config.evaluation_seeds
        )
        death_regression = max(
            before["survival"] - after["survival"], adv_before["survival"] - adv_after["survival"]
        )
        scenario_mirror = None
        # All ten mirror angles are evidence-based conservative gates;
        # they never automatically certify subjective game quality or cause
        # changes in production weights. Full training-seed holds remain
        # disjoint from this measured evaluation.
        if (self.champion.kind == "studio" and candidate.kind == "studio"
                and mutation.get("supported") and candidate.digest != self.champion.digest):
            from .game_studio_environment import parse_studio_source
            from .game_studio_scenario_lab import ANGLES, mirrored_rule_comparison

            original = parse_studio_source(
                json.loads(self.champion.tree["game/studio/session.json"])
            )
            variant = parse_studio_source(
                json.loads(candidate.tree["game/studio/session.json"])
            )
            scenario_mirror = mirrored_rule_comparison(
                original, variant,
                seed=self._seed(index, "mirrored-angles") % (2**31 - 16),
                steps=min(6, self.config.episode_steps), angles=ANGLES,
            )
        constraints = {
            "mirrored_rule_has_observed_mechanics_effect": (
                scenario_mirror is None or
                scenario_mirror["informative_for_rule_selection"]
            ),
            "mirrored_original_rule_nonregression": (
                scenario_mirror is None
                or scenario_mirror["worst_return_difference"]
                >= -self.config.max_worst_seed_regression - 1e-9
            ),
            "visual_source_resource_floor": dragon["passed"],
            "typed_proposal_valid": not mutation.get("proposal_rejected", False),
            "ordinary_mean_return_nonregression": improvement >= -1e-9,
            "perturbed_mean_return_nonregression": adversarial_delta >= -1e-9,
            "worst_seed_return_nonregression": min(ordinary_pairs + adv_pairs)
            >= -self.config.max_worst_seed_regression - 1e-9,
            "death_rate_nonregression": death_regression <= self.config.max_death_regression + 1e-9,
            "measured_step_latency_limit": self.config.max_mean_step_ms is None
            or mean_step_ms <= self.config.max_mean_step_ms,
        }
        accepted = all(constraints.values()) and weighted > max(1e-9, self.config.min_improvement)
        comparisons = list(zip(baseline + baseline_adv, measured + measured_adv, strict=True))
        new_counterexamples = []
        for baseline_play, play in sorted(
            comparisons, key=lambda pair: pair[1]["return"] - pair[0]["return"]
        ):
            if not accepted and (len(new_counterexamples) < 2 or play["dead"] and not baseline_play["dead"]):
                record = {
                    "round_index": index,
                    "seed": play["seed"],
                    "request_digest": candidate.digest,
                    "environment_digest": play["environment_digest"],
                    "policy_digest": policy["snapshot_digest"],
                    "reason": (
                        "observed_death_regression"
                        if play["dead"] and not baseline_play["dead"]
                        else "rejected_candidate_comparison"
                    ),
                    "return": play["return"],
                    "trace_digest": play["trace_digest"],
                    "trace_format": play["trace_format"],
                    "trace": play["_trace"],
                }
                record["record_digest"] = digest({k: v for k, v in record.items() if k != "trace"})
                new_counterexamples.append(record)
                if len(new_counterexamples) >= 4:
                    break
        for play in baseline + measured + baseline_adv + measured_adv:
            play.pop("_trace", None)
        steps = trained.updates + sum(p["steps"] for p in baseline + measured + baseline_adv + measured_adv)
        if scenario_mirror is not None:
            steps += sum(
                row["baseline_executed_steps"] + row["candidate_executed_steps"]
                for row in scenario_mirror["mirrors"]
            )
        curriculum = {
            "kind": self.config.curriculum,
            "training_seeds": training_seeds,
            "reexecuted_counterexamples": [
                {
                    "seed": r["seed"],
                    "original_round": r["round_index"],
                    "record_digest": r["record_digest"],
                    "transition": "prior_evaluation_seed_now_explicit_training",
                }
                for r in chosen
            ],
            "fresh_training_episodes": len(training_seeds) - len(chosen),
            "exploration_epsilon": learning_config.epsilon,
            "training_parent_digest": None if parent is None else parent["snapshot_digest"],
            "changed_environment_table_reset": parent is None and self.champion_policy is not None,
        }
        roles = {
            "jeeves": {
                "actual_training_episodes": self.config.episodes_per_round,
                "actual_updates": trained.updates,
                "policy_digest": policy["snapshot_digest"],
                "training_seeds": training_seeds,
                "play": measured[0],
                "champion_play": baseline[0],
                "fresh_candidate_policy": parent is None,
                "evaluations": measured,
                "champion_evaluations": baseline,
                "curriculum": curriculum,
            },
            "dragon": dragon,
            "adversary": {
                "seed": jitter_seeds[0],
                "candidate": measured_adv[0],
                "champion": baseline_adv[0],
                "actual_return_delta": adversarial_delta,
                "evaluations": measured_adv,
                "champion_evaluations": baseline_adv,
                "seed_partitions_disjoint": True,
                "source_bound_six_angle_mirror": scenario_mirror,
                "semantic_generalization_claim": False,
            },
        }
        for name, evidence in roles.items():
            if "report_digest" not in evidence:
                evidence["report_digest"] = digest({"role": name, "evidence": evidence})
        reward = math.tanh(weighted) if all(constraints.values()) else -1.0
        raw = {
            "schema_version": ROUND_SCHEMA,
            "campaign_id": self.campaign_id,
            "round_index": index,
            "context_digest": self.context_digest,
            "previous_history_digest": self.history_digest,
            "candidate_digest": candidate.digest,
            "champion_before_digest": self.champion.digest,
            "mutation": mutation,
            "roles": roles,
            "actual_steps": steps,
            "status": "accepted" if accepted else "rejected",
            "champion_promoted": accepted,
            "objective_vector": {
                "baseline": before,
                "candidate": after,
                "delta": deltas,
                "normalized_delta": normalized,
                "weights": dict(self.config.objective_weights),
                "weighted_gain": weighted,
                "quality_claim": False,
            },
            "constraints": constraints,
            "performance": {
                "mean_step_wall_ms": mean_step_ms,
                "limit_ms": self.config.max_mean_step_ms,
                "render_time_included": False,
                "mirrored_effectiveness": (
                    None if scenario_mirror is None else {
                        "informative": scenario_mirror["informative_for_rule_selection"],
                        "classification": scenario_mirror["effectiveness_classification"],
                        "measured_behavior_differences": scenario_mirror["measured_behavior_differences"],
                        "productive_state_changes": scenario_mirror["productive_state_changes"],
                        "total_executed_steps": scenario_mirror["total_executed_steps"],
                        "actual_replayed_action_applications": scenario_mirror["total_replayed_action_applications"],
                        "novelty_per_100_replayed_actions": scenario_mirror["novelty_per_100_replayed_actions"],
                        "worst_return_difference": scenario_mirror["worst_return_difference"],
                    }
                ),
            },
            "bandit_observation": {
                "arm_id": mutation["proposal_selection"]["arm_id"],
                "reward": reward,
                "accepted": accepted,
                "isolated_mechanic_causality_claim": False,
            },
            "counterexample_summaries": [
                {k: v for k, v in r.items() if k != "trace"} for r in new_counterexamples
            ],
            "decision": {
                "ordinary_return_delta": improvement,
                "adversarial_return_delta": adversarial_delta,
                "worst_seed_return_delta": min(ordinary_pairs + adv_pairs),
                "mirrored_worst_return_delta": (
                    None if scenario_mirror is None
                    else scenario_mirror["worst_return_difference"]
                ),
                "death_rate_regression": death_regression,
                "minimum_improvement": self.config.min_improvement,
                "minimum_improvement_unit": "weighted_normalized_objective_gain",
                "hard_checks_passed": all(constraints.values()),
                "gameplay_gain_is_not_an_aesthetic_score": True,
                "reason": (
                    "measured_multiobjective_gain_and_all_constraints"
                    if accepted
                    else "candidate_failed_one_or_more_declared_gates"
                ),
            },
            "proposals": [],
            "lessons": [],
            "implementation_digest": self.implementation_digest,
        }
        evidence_digest = digest(roles)
        for role in ("jeeves", "dragon", "adversary", "decision"):
            facts = {
                "actual_steps": steps,
                "ordinary_return_delta": improvement,
                "adversarial_return_delta": adversarial_delta,
                "objective_gain": weighted,
                "constraints": constraints,
                "mechanic": mutation.get("mechanic"),
                "direction": mutation.get("direction"),
                "candidate_changes": mutation["changes"],
                "proposal_arm": mutation["proposal_selection"]["arm_id"],
                "evaluation_seed_count": self.config.evaluation_seeds,
                "counterexamples": [r["record_digest"] for r in new_counterexamples],
            }
            lesson = {
                "schema_version": LESSON_SCHEMA,
                "context_digest": self.context_digest,
                "round_index": index,
                "role": role,
                "outcome": raw["status"],
                "candidate_digest": candidate.digest,
                "facts": facts,
                "recommendation": (
                    "Retain this measured candidate within the exact admitted context."
                    if accepted
                    else "Retain champion; use measured counterexamples and avoid this unsupported or regressing proposal without new evidence."
                ),
                "evidence_digest": evidence_digest,
            }
            lesson["lesson_digest"] = digest(lesson)
            raw["lessons"].append(lesson)
        if accepted and mutation["supported"]:
            raw["proposals"] = [
                {
                    "operation": "project_compile",
                    "target_id": candidate.target_id,
                    "request_digest": candidate.digest,
                    "status": "requires_existing_scoped_build_tool_execution",
                    "successful_build_claim": False,
                }
            ]
        raw["round_digest"] = digest(raw)
        return _copy(raw, 262144), candidate, policy, new_counterexamples

    def run_slice(self, rounds: int, *, on_checkpoint=None, authorize=None, cancel=None) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise GameLearningError("campaign already executing a slice")
        try:
            return self._run_slice(rounds, on_checkpoint=on_checkpoint, authorize=authorize, cancel=cancel)
        finally:
            self._lock.release()

    def _run_slice(
        self,
        rounds: int,
        *,
        on_checkpoint: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        authorize: Callable[[], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        count = _int(rounds, "requested actual slice rounds", 1, self.config.slice_rounds)
        if self._executing:
            raise GameLearningError("campaign already executing a slice")
        if self.cursor + count > self.config.round_limit:
            raise GameLearningError("campaign requested beyond admitted total round budget")
        # Account for twenty baseline/candidate audited mirror episodes.
        # Their real steps must be admitted
        # *before* a campaign slice starts, not only after checkpointing.
        studio_mirror_allowance = (
            20 * min(6, self.config.episode_steps)
            if self.champion.kind == "studio" else 0
        )
        planned = (
            count * (
                (self.config.episodes_per_round + 4 * self.config.evaluation_seeds)
                * self.config.episode_steps + studio_mirror_allowance
            )
        )
        if planned > self.config.max_slice_steps:
            raise GameLearningError("campaign planned slice exceeds cumulative step budget")
        _guard(cancel, authorize)
        self._executing = True
        reports = []
        actual = 0
        try:
            for _ in range(count):
                previous = self.snapshot()
                report, candidate, policy, counterexamples = self._round(self.cursor + 1, cancel, authorize)
                if actual + report["actual_steps"] > self.config.max_slice_steps:
                    raise GameLearningError("executed campaign steps exceeded admitted slice budget")
                _guard(cancel, authorize)
                if _implementation() != self.implementation_digest:
                    raise GameLearningError("studio code changed before round commit")
                try:
                    self.cursor += 1
                    self.cumulative_steps += report["actual_steps"]
                    actual += report["actual_steps"]
                    observation = report["bandit_observation"]
                    arm = observation["arm_id"]
                    row = self.bandit_state.setdefault(arm, {"trials": 0, "accepted": 0, "reward_sum": 0.0})
                    row["trials"] += 1
                    row["accepted"] += int(observation["accepted"])
                    row["reward_sum"] += observation["reward"]
                    retained = self.counterexamples + counterexamples
                    while len(retained) > 16 or len(canonical(retained, limit=8 * 1024 * 1024)) > 524288:
                        # Keep full recent evidence when it fits; keep seed receipts
                        # for larger trajectories rather than truncating a trace.
                        full = next((r for r in retained if r["trace"] is not None), None)
                        if full is not None:
                            full = dict(full)
                            full["trace"] = None
                            full["record_digest"] = digest(
                                {k: v for k, v in full.items() if k not in ("record_digest", "trace")}
                            )
                            retained = [
                                (
                                    full
                                    if r["seed"] == full["seed"] and r["round_index"] == full["round_index"]
                                    else r
                                )
                                for r in retained
                            ]
                        else:
                            retained.pop(0)
                    self.counterexamples = retained
                    self.lesson_count += len(report["lessons"])
                    self.recent_lessons = (self.recent_lessons + report["lessons"])[-64:]
                    self.history_digest = digest(
                        {"previous": self.history_digest, "round_digest": report["round_digest"]}
                    )
                    self.last_round_digest = report["round_digest"]
                    if report["champion_promoted"]:
                        self.champion, self.champion_policy = candidate, policy
                    committed = self.snapshot()
                    if on_checkpoint is not None:
                        result = on_checkpoint(committed, report)
                        if result is not None and result is not True:
                            close = getattr(result, "close", None)
                            if callable(close):
                                close()
                            raise GameLearningError("campaign checkpoint did not finish synchronously")
                except BaseException:
                    self._restore(previous)
                    raise
                reports.append(report)
            return {
                "snapshot": self.snapshot(),
                "rounds": reports,
                "actual_rounds": len(reports),
                "actual_steps": actual,
                "planned_steps": planned,
                "remaining_rounds": self.config.round_limit - self.cursor,
                "status": (
                    "completed" if self.cursor == self.config.round_limit else "paused_between_bounded_slices"
                ),
            }
        finally:
            self._executing = False
