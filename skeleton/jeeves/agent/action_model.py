"""Verified action/skill learning for the Jeeves agent runtime.

This layer learns from *host-verified outcomes*, not model self-assessment.
Each tool or reusable skill has a statistical profile describing success rate,
latency, cost, failure modes, risk, contexts, and preconditions.  Selection is
multi-objective: expected success, uncertainty/novelty, latency, monetary or
resource cost, risk, and historical verification quality all contribute.

The model may propose a tool or skill, but the host can compare that proposal
against empirical action models and choose a safer or more reliable route.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .types import (
    AgentContractError,
    RiskTier,
    ToolObservation,
    bounded_text,
    finite_number,
    json_safe,
    probability,
    require_id,
    require_tool_name,
    stable_fingerprint,
    stable_id,
)


class ActionModelError(RuntimeError):
    pass


class OutcomeKind(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    DENIED = "denied"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class SkillKind(str, Enum):
    TOOL = "tool"
    PROCEDURE = "procedure"
    RETRIEVAL = "retrieval"
    REASONING = "reasoning"
    VERIFICATION = "verification"
    COMPOSITE = "composite"


@dataclass(frozen=True, slots=True)
class RunningStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 0:
            raise AgentContractError("running stat count must be non-negative integer")
        mean = finite_number("mean", self.mean)
        m2 = finite_number("m2", self.m2)
        if m2 < -1e-12:
            raise AgentContractError("m2 must be non-negative")
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "m2", max(0.0, m2))
        if self.minimum is not None:
            object.__setattr__(self, "minimum", finite_number("minimum", self.minimum))
        if self.maximum is not None:
            object.__setattr__(self, "maximum", finite_number("maximum", self.maximum))

    @property
    def variance(self) -> float:
        return self.m2 / (self.count - 1) if self.count > 1 else 0.0

    @property
    def stddev(self) -> float:
        return math.sqrt(max(0.0, self.variance))

    def update(self, value: float) -> "RunningStats":
        value = finite_number("value", value)
        count = self.count + 1
        delta = value - self.mean
        mean = self.mean + delta / count
        delta2 = value - mean
        m2 = self.m2 + delta * delta2
        minimum = value if self.minimum is None else min(self.minimum, value)
        maximum = value if self.maximum is None else max(self.maximum, value)
        return RunningStats(count, mean, m2, minimum, maximum)


@dataclass(frozen=True, slots=True)
class BetaPosterior:
    alpha: float = 1.0
    beta: float = 1.0

    def __post_init__(self) -> None:
        alpha = finite_number("alpha", self.alpha)
        beta = finite_number("beta", self.beta)
        if alpha <= 0 or beta <= 0:
            raise AgentContractError("beta posterior parameters must be positive")
        object.__setattr__(self, "alpha", alpha)
        object.__setattr__(self, "beta", beta)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total * total * (total + 1.0))

    @property
    def uncertainty(self) -> float:
        return min(1.0, math.sqrt(self.variance) * 4.0)

    def observe(self, success_weight: float, failure_weight: float) -> "BetaPosterior":
        success = finite_number("success_weight", success_weight)
        failure = finite_number("failure_weight", failure_weight)
        if success < 0 or failure < 0:
            raise AgentContractError("beta observation weights must be non-negative")
        return BetaPosterior(self.alpha + success, self.beta + failure)

    def sample(self, rng: random.Random) -> float:
        return rng.betavariate(self.alpha, self.beta)


@dataclass(frozen=True, slots=True)
class ContextSignature:
    domain: str = "general"
    environment: str = "default"
    tags: tuple[str, ...] = ()
    feature_buckets: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", require_id("domain", self.domain))
        object.__setattr__(self, "environment", require_id("environment", self.environment))
        tags = tuple(sorted({require_id("tag", tag) for tag in self.tags}))
        object.__setattr__(self, "tags", tags)
        features = {require_id("feature", key): bounded_text("feature bucket", value, maximum=256) for key, value in dict(self.feature_buckets).items()}
        object.__setattr__(self, "feature_buckets", features)

    @property
    def key(self) -> str:
        return stable_fingerprint(
            {
                "domain": self.domain,
                "environment": self.environment,
                "tags": self.tags,
                "feature_buckets": dict(sorted(self.feature_buckets.items())),
            }
        )

    def similarity(self, other: "ContextSignature") -> float:
        if not isinstance(other, ContextSignature):
            return 0.0
        score = 0.0
        weight = 0.0
        weight += 0.30
        score += 0.30 if self.domain == other.domain else 0.0
        weight += 0.20
        score += 0.20 if self.environment == other.environment else 0.0
        tag_union = set(self.tags) | set(other.tags)
        if tag_union:
            weight += 0.25
            score += 0.25 * len(set(self.tags) & set(other.tags)) / len(tag_union)
        feature_keys = set(self.feature_buckets) | set(other.feature_buckets)
        if feature_keys:
            weight += 0.25
            matches = sum(1 for key in feature_keys if self.feature_buckets.get(key) == other.feature_buckets.get(key))
            score += 0.25 * matches / len(feature_keys)
        return score / weight if weight else 1.0


@dataclass(frozen=True, slots=True)
class SkillSpec:
    skill_id: str
    name: str
    kind: SkillKind
    risk: RiskTier = RiskTier.READ_ONLY
    description: str = ""
    preconditions: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    nominal_cost: float = 0.0
    nominal_latency_ms: float = 0.0
    deterministic: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill_id", require_id("skill_id", self.skill_id))
        object.__setattr__(self, "name", bounded_text("skill name", self.name, maximum=1024))
        if not isinstance(self.kind, SkillKind):
            object.__setattr__(self, "kind", SkillKind(str(self.kind)))
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(self, "description", bounded_text("description", self.description, maximum=4096, allow_empty=True))
        object.__setattr__(self, "preconditions", tuple(bounded_text("precondition", item, maximum=1024) for item in self.preconditions))
        object.__setattr__(self, "postconditions", tuple(bounded_text("postcondition", item, maximum=1024) for item in self.postconditions))
        object.__setattr__(self, "capabilities", tuple(sorted({require_id("capability", item) for item in self.capabilities})))
        object.__setattr__(self, "dependencies", tuple(sorted({require_id("dependency", item) for item in self.dependencies})))
        cost = finite_number("nominal_cost", self.nominal_cost)
        latency = finite_number("nominal_latency_ms", self.nominal_latency_ms)
        if cost < 0 or latency < 0:
            raise AgentContractError("nominal cost and latency must be non-negative")
        object.__setattr__(self, "nominal_cost", cost)
        object.__setattr__(self, "nominal_latency_ms", latency)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @classmethod
    def tool(
        cls,
        tool_name: str,
        *,
        risk: RiskTier = RiskTier.READ_ONLY,
        description: str = "",
        capabilities: Sequence[str] = (),
        nominal_cost: float = 0.0,
        nominal_latency_ms: float = 0.0,
        deterministic: bool = False,
    ) -> "SkillSpec":
        tool_name = require_tool_name(tool_name)
        return cls(
            skill_id=stable_id("skill", {"kind": "tool", "name": tool_name}),
            name=tool_name,
            kind=SkillKind.TOOL,
            risk=risk,
            description=description,
            capabilities=tuple(capabilities),
            nominal_cost=nominal_cost,
            nominal_latency_ms=nominal_latency_ms,
            deterministic=deterministic,
            metadata={"tool_name": tool_name},
        )


@dataclass(frozen=True, slots=True)
class ActionEpisode:
    episode_id: str
    run_id: str
    skill_id: str
    context: ContextSignature
    outcome: OutcomeKind
    verified: bool
    verification_score: float
    latency_ms: float
    cost: float = 0.0
    attempts: int = 1
    failure_mode: str | None = None
    observation_fingerprint: str | None = None
    started_at: float = 0.0
    ended_at: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_id", require_id("episode_id", self.episode_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "skill_id", require_id("skill_id", self.skill_id))
        if not isinstance(self.context, ContextSignature):
            raise AgentContractError("context must be ContextSignature")
        if not isinstance(self.outcome, OutcomeKind):
            object.__setattr__(self, "outcome", OutcomeKind(str(self.outcome)))
        if not isinstance(self.verified, bool):
            raise AgentContractError("verified must be boolean")
        object.__setattr__(self, "verification_score", probability("verification_score", self.verification_score))
        latency = finite_number("latency_ms", self.latency_ms)
        cost = finite_number("cost", self.cost)
        if latency < 0 or cost < 0:
            raise AgentContractError("latency and cost must be non-negative")
        object.__setattr__(self, "latency_ms", latency)
        object.__setattr__(self, "cost", cost)
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int) or self.attempts < 1:
            raise AgentContractError("attempts must be positive integer")
        if self.failure_mode is not None:
            object.__setattr__(self, "failure_mode", bounded_text("failure_mode", self.failure_mode, maximum=1024))
        if self.observation_fingerprint is not None:
            fingerprint = str(self.observation_fingerprint).strip().lower()
            if not fingerprint:
                raise AgentContractError("observation fingerprint cannot be empty")
            object.__setattr__(self, "observation_fingerprint", fingerprint)
        started = finite_number("started_at", self.started_at)
        ended = finite_number("ended_at", self.ended_at)
        if started < 0 or ended < started:
            raise AgentContractError("invalid episode timestamps")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "ended_at", ended)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def duration_ms(self) -> float:
        if self.ended_at > self.started_at:
            return (self.ended_at - self.started_at) * 1000.0
        return self.latency_ms


@dataclass(frozen=True, slots=True)
class ContextPerformance:
    context_key: str
    success: BetaPosterior = field(default_factory=BetaPosterior)
    verification: BetaPosterior = field(default_factory=BetaPosterior)
    latency: RunningStats = field(default_factory=RunningStats)
    cost: RunningStats = field(default_factory=RunningStats)
    attempts: RunningStats = field(default_factory=RunningStats)
    failure_modes: Mapping[str, int] = field(default_factory=dict)
    episode_count: int = 0
    last_used_at: float | None = None


@dataclass(frozen=True, slots=True)
class SkillProfile:
    spec: SkillSpec
    success: BetaPosterior = field(default_factory=BetaPosterior)
    verification: BetaPosterior = field(default_factory=BetaPosterior)
    latency: RunningStats = field(default_factory=RunningStats)
    cost: RunningStats = field(default_factory=RunningStats)
    attempts: RunningStats = field(default_factory=RunningStats)
    failure_modes: Mapping[str, int] = field(default_factory=dict)
    contexts: Mapping[str, ContextPerformance] = field(default_factory=dict)
    episode_count: int = 0
    success_streak: int = 0
    failure_streak: int = 0
    last_used_at: float | None = None
    last_success_at: float | None = None
    last_failure_at: float | None = None
    retired: bool = False

    @property
    def empirical_success(self) -> float:
        return self.success.mean

    @property
    def verification_quality(self) -> float:
        return self.verification.mean

    @property
    def uncertainty(self) -> float:
        return self.success.uncertainty


@dataclass(frozen=True, slots=True)
class SelectionWeights:
    success: float = 0.40
    verification: float = 0.18
    novelty: float = 0.08
    latency: float = 0.10
    cost: float = 0.08
    risk: float = 0.12
    context_match: float = 0.14

    def normalized(self) -> "SelectionWeights":
        values = [
            max(0.0, finite_number("weight", value))
            for value in (
                self.success,
                self.verification,
                self.novelty,
                self.latency,
                self.cost,
                self.risk,
                self.context_match,
            )
        ]
        total = sum(values)
        if total <= 0:
            raise ValueError("selection weights must contain positive mass")
        return SelectionWeights(*(value / total for value in values))


@dataclass(frozen=True, slots=True)
class SkillScore:
    skill_id: str
    total: float
    expected_success: float
    verification_quality: float
    novelty: float
    latency_score: float
    cost_score: float
    risk_score: float
    context_match: float
    samples: int
    rationale: str


@dataclass(frozen=True, slots=True)
class SkillSelection:
    selected: SkillScore | None
    alternatives: tuple[SkillScore, ...]
    required_capabilities: tuple[str, ...]
    context: ContextSignature
    reason: str


class SkillLibrary:
    """Empirical library of tools/procedures learned from verified episodes."""

    _RISK_PENALTY = {
        RiskTier.READ_ONLY: 0.02,
        RiskTier.REVERSIBLE: 0.10,
        RiskTier.MUTATING: 0.28,
        RiskTier.EXTERNAL: 0.38,
        RiskTier.HIGH_IMPACT: 0.70,
    }

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        max_episodes: int = 100_000,
        rng_seed: int = 0,
    ) -> None:
        if isinstance(max_episodes, bool) or not isinstance(max_episodes, int) or max_episodes < 1:
            raise ValueError("max_episodes must be positive integer")
        self._clock = clock
        self._max_episodes = max_episodes
        self._rng_seed = int(rng_seed)
        self._profiles: dict[str, SkillProfile] = {}
        self._episodes: deque[ActionEpisode] = deque(maxlen=max_episodes)
        self._episode_ids: set[str] = set()
        self._capability_index: dict[str, set[str]] = defaultdict(set)
        self._dependency_reverse: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    def register(self, spec: SkillSpec) -> SkillProfile:
        if not isinstance(spec, SkillSpec):
            raise TypeError("spec must be SkillSpec")
        with self._lock:
            prior = self._profiles.get(spec.skill_id)
            if prior is not None:
                if prior.spec != spec:
                    raise ActionModelError("skill id already registered with different specification")
                return prior
            for dependency in spec.dependencies:
                if dependency == spec.skill_id:
                    raise ActionModelError("skill cannot depend on itself")
            profile = SkillProfile(spec=spec)
            self._profiles[spec.skill_id] = profile
            for capability in spec.capabilities:
                self._capability_index[capability].add(spec.skill_id)
            for dependency in spec.dependencies:
                self._dependency_reverse[dependency].add(spec.skill_id)
            self._reject_dependency_cycles()
            return profile

    def profile(self, skill_id: str) -> SkillProfile | None:
        with self._lock:
            return self._profiles.get(require_id("skill_id", skill_id))

    def require_profile(self, skill_id: str) -> SkillProfile:
        profile = self.profile(skill_id)
        if profile is None:
            raise ActionModelError(f"unknown skill {skill_id}")
        return profile

    def retire(self, skill_id: str, retired: bool = True) -> SkillProfile:
        skill_id = require_id("skill_id", skill_id)
        with self._lock:
            profile = self.require_profile(skill_id)
            revised = replace(profile, retired=bool(retired))
            self._profiles[skill_id] = revised
            return revised

    def record(self, episode: ActionEpisode) -> SkillProfile:
        if not isinstance(episode, ActionEpisode):
            raise TypeError("episode must be ActionEpisode")
        with self._lock:
            profile = self.require_profile(episode.skill_id)
            if episode.episode_id in self._episode_ids:
                return profile
            if len(self._episodes) == self._episodes.maxlen and self._episodes:
                evicted = self._episodes[0]
                self._episode_ids.discard(evicted.episode_id)
            self._episodes.append(episode)
            self._episode_ids.add(episode.episode_id)
            revised = self._update_profile(profile, episode)
            self._profiles[episode.skill_id] = revised
            return revised

    def record_tool_observation(
        self,
        *,
        run_id: str,
        tool_name: str,
        observation: ToolObservation,
        context: ContextSignature | None = None,
        verified: bool,
        verification_score: float,
        cost: float = 0.0,
        attempts: int = 1,
        failure_mode: str | None = None,
        started_at: float | None = None,
        ended_at: float | None = None,
        risk: RiskTier = RiskTier.READ_ONLY,
        capabilities: Sequence[str] = (),
    ) -> SkillProfile:
        if not isinstance(observation, ToolObservation):
            raise TypeError("observation must be ToolObservation")
        tool_name = require_tool_name(tool_name)
        spec = SkillSpec.tool(tool_name, risk=risk, capabilities=capabilities)
        profile = self.profile(spec.skill_id)
        if profile is None:
            profile = self.register(spec)
        else:
            profile = self._reconcile_observed_tool_spec(profile, spec)
        if observation.ok and verified:
            outcome = OutcomeKind.SUCCESS
        elif observation.ok:
            outcome = OutcomeKind.PARTIAL
        else:
            lower = (observation.error or "").lower()
            outcome = OutcomeKind.TIMEOUT if "timeout" in lower else OutcomeKind.FAILURE
        now = self._clock()
        episode = ActionEpisode(
            episode_id=stable_id(
                "episode",
                {
                    "run": run_id,
                    "call": observation.call_id,
                    "tool": tool_name,
                    "payload": stable_fingerprint(observation.payload),
                    "ok": observation.ok,
                    "verified": verified,
                },
            ),
            run_id=run_id,
            skill_id=profile.spec.skill_id,
            context=context or ContextSignature(),
            outcome=outcome,
            verified=verified,
            verification_score=verification_score,
            latency_ms=observation.latency_ms,
            cost=cost,
            attempts=attempts,
            failure_mode=failure_mode or (observation.error[:512] if observation.error else None),
            observation_fingerprint=stable_fingerprint(observation.payload),
            started_at=now if started_at is None else started_at,
            ended_at=now if ended_at is None else ended_at,
            metadata={"call_id": observation.call_id, "cached": observation.cached},
        )
        return self.record(episode)

    def _reconcile_observed_tool_spec(
        self,
        profile: SkillProfile,
        observed: SkillSpec,
    ) -> SkillProfile:
        """Conservatively tighten a learned tool profile from runtime evidence.

        Tool skill identity is stable by tool name, so later observations can
        legitimately carry stronger risk/capability information than the first
        registration. Risk may only move upward; capabilities are unioned.
        """

        if profile.spec.kind is not SkillKind.TOOL or observed.kind is not SkillKind.TOOL:
            raise ActionModelError("tool observation cannot reconcile a non-tool skill")
        if profile.spec.skill_id != observed.skill_id:
            raise ActionModelError("tool observation skill identity mismatch")
        with self._lock:
            current = self._profiles.get(profile.spec.skill_id, profile)
            current_risk = current.spec.risk
            observed_risk = observed.risk
            risk = (
                observed_risk
                if self._RISK_PENALTY[observed_risk]
                > self._RISK_PENALTY[current_risk]
                else current_risk
            )
            capabilities = tuple(
                sorted(set(current.spec.capabilities) | set(observed.capabilities))
            )
            if risk is current_risk and capabilities == current.spec.capabilities:
                return current
            revised_spec = replace(
                current.spec,
                risk=risk,
                capabilities=capabilities,
            )
            revised = replace(current, spec=revised_spec)
            self._profiles[current.spec.skill_id] = revised
            for capability in capabilities:
                self._capability_index[capability].add(current.spec.skill_id)
            return revised

    def candidates(self, required_capabilities: Sequence[str]) -> tuple[SkillProfile, ...]:
        capabilities = tuple(sorted({require_id("capability", item) for item in required_capabilities}))
        with self._lock:
            if not capabilities:
                ids = set(self._profiles)
            else:
                sets = [self._capability_index.get(capability, set()) for capability in capabilities]
                ids = set.intersection(*map(set, sets)) if sets else set()
            values = [self._profiles[item] for item in ids if not self._profiles[item].retired]
        values.sort(key=lambda profile: profile.spec.skill_id)
        return tuple(values)

    def select(
        self,
        *,
        required_capabilities: Sequence[str] = (),
        context: ContextSignature | None = None,
        maximum_risk: RiskTier = RiskTier.HIGH_IMPACT,
        weights: SelectionWeights | None = None,
        exploration: float = 0.10,
        latency_budget_ms: float | None = None,
        cost_budget: float | None = None,
        top_k: int = 5,
    ) -> SkillSelection:
        context = context or ContextSignature()
        if not isinstance(maximum_risk, RiskTier):
            maximum_risk = RiskTier(str(maximum_risk))
        normalized = (weights or SelectionWeights()).normalized()
        exploration = probability("exploration", exploration)
        if top_k < 1:
            raise ValueError("top_k must be positive")
        candidates = [profile for profile in self.candidates(required_capabilities) if self._risk_allowed(profile.spec.risk, maximum_risk)]
        if not candidates:
            return SkillSelection(None, (), tuple(required_capabilities), context, "no registered skill satisfies capability/risk constraints")
        latency_norm = self._latency_normalizer(candidates, latency_budget_ms)
        cost_norm = self._cost_normalizer(candidates, cost_budget)
        scored: list[SkillScore] = []
        for profile in candidates:
            expected_success, context_match, context_samples = self._context_adjusted_success(profile, context)
            novelty = min(1.0, profile.uncertainty + 1.0 / math.sqrt(profile.episode_count + 1.0))
            latency_value = profile.latency.mean if profile.latency.count else profile.spec.nominal_latency_ms
            cost_value = profile.cost.mean if profile.cost.count else profile.spec.nominal_cost
            latency_score = latency_norm(latency_value)
            cost_score = cost_norm(cost_value)
            risk_score = 1.0 - self._RISK_PENALTY[profile.spec.risk]
            verification_quality = profile.verification_quality
            total = (
                normalized.success * expected_success
                + normalized.verification * verification_quality
                + normalized.novelty * novelty * exploration
                + normalized.latency * latency_score
                + normalized.cost * cost_score
                + normalized.risk * risk_score
                + normalized.context_match * context_match
            )
            failure_penalty = min(0.30, profile.failure_streak * 0.06)
            total = max(0.0, min(1.0, total - failure_penalty))
            scored.append(
                SkillScore(
                    skill_id=profile.spec.skill_id,
                    total=total,
                    expected_success=expected_success,
                    verification_quality=verification_quality,
                    novelty=novelty,
                    latency_score=latency_score,
                    cost_score=cost_score,
                    risk_score=risk_score,
                    context_match=context_match,
                    samples=profile.episode_count + context_samples,
                    rationale=(
                        f"success={expected_success:.3f}; verify={verification_quality:.3f}; novelty={novelty:.3f}; "
                        f"latency={latency_score:.3f}; cost={cost_score:.3f}; risk={risk_score:.3f}; "
                        f"context={context_match:.3f}; failure_streak={profile.failure_streak}"
                    ),
                )
            )
        scored.sort(key=lambda item: (item.total, item.expected_success, item.verification_quality, item.skill_id), reverse=True)
        alternatives = tuple(scored[:top_k])
        return SkillSelection(alternatives[0], alternatives, tuple(required_capabilities), context, "selected by empirical multi-objective action model")

    def thompson_select(
        self,
        *,
        required_capabilities: Sequence[str] = (),
        context: ContextSignature | None = None,
        maximum_risk: RiskTier = RiskTier.HIGH_IMPACT,
        decision_seed: str = "default",
    ) -> SkillProfile | None:
        context = context or ContextSignature()
        candidates = [profile for profile in self.candidates(required_capabilities) if self._risk_allowed(profile.spec.risk, maximum_risk)]
        if not candidates:
            return None
        seed = int(stable_fingerprint({"seed": decision_seed, "context": context.key})[:16], 16) ^ self._rng_seed
        rng = random.Random(seed)
        scored: list[tuple[float, SkillProfile]] = []
        for profile in candidates:
            posterior = self._best_context_posterior(profile, context)
            sample = posterior.sample(rng)
            risk_discount = 1.0 - self._RISK_PENALTY[profile.spec.risk]
            verification_discount = 0.5 + profile.verification_quality * 0.5
            scored.append((sample * risk_discount * verification_discount, profile))
        scored.sort(key=lambda item: (item[0], item[1].spec.skill_id), reverse=True)
        return scored[0][1]

    def failure_modes(self, skill_id: str, *, limit: int = 10) -> tuple[tuple[str, int], ...]:
        profile = self.require_profile(skill_id)
        values = sorted(profile.failure_modes.items(), key=lambda item: (-item[1], item[0]))
        return tuple(values[:limit])

    def dependency_closure(self, skill_id: str) -> tuple[str, ...]:
        skill_id = require_id("skill_id", skill_id)
        self.require_profile(skill_id)
        ordered: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(current: str) -> None:
            if current in visiting:
                raise ActionModelError("skill dependency cycle")
            if current in visited:
                return
            visiting.add(current)
            profile = self.require_profile(current)
            for dependency in profile.spec.dependencies:
                visit(dependency)
            visiting.remove(current)
            visited.add(current)
            ordered.append(current)

        visit(skill_id)
        return tuple(ordered)

    def recommend_fallbacks(self, skill_id: str, *, context: ContextSignature | None = None, limit: int = 3) -> tuple[SkillScore, ...]:
        profile = self.require_profile(skill_id)
        selection = self.select(
            required_capabilities=profile.spec.capabilities,
            context=context,
            maximum_risk=profile.spec.risk,
            top_k=max(limit + 1, 4),
        )
        return tuple(item for item in selection.alternatives if item.skill_id != skill_id)[:limit]

    def episodes(self, *, skill_id: str | None = None, run_id: str | None = None) -> tuple[ActionEpisode, ...]:
        with self._lock:
            values = list(self._episodes)
        if skill_id is not None:
            skill_id = require_id("skill_id", skill_id)
            values = [item for item in values if item.skill_id == skill_id]
        if run_id is not None:
            run_id = require_id("run_id", run_id)
            values = [item for item in values if item.run_id == run_id]
        return tuple(values)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            profiles = list(self._profiles.values())
        return {
            "skill_count": len(profiles),
            "episode_count": len(self._episodes),
            "skills": [
                {
                    "skill_id": profile.spec.skill_id,
                    "name": profile.spec.name,
                    "kind": profile.spec.kind.value,
                    "risk": profile.spec.risk.value,
                    "capabilities": profile.spec.capabilities,
                    "episodes": profile.episode_count,
                    "success_mean": profile.empirical_success,
                    "success_uncertainty": profile.uncertainty,
                    "verification_quality": profile.verification_quality,
                    "latency_mean_ms": profile.latency.mean,
                    "cost_mean": profile.cost.mean,
                    "success_streak": profile.success_streak,
                    "failure_streak": profile.failure_streak,
                    "retired": profile.retired,
                    "failure_modes": dict(sorted(profile.failure_modes.items(), key=lambda item: (-item[1], item[0]))[:5]),
                }
                for profile in sorted(profiles, key=lambda item: item.spec.skill_id)
            ],
            "fingerprint": self.fingerprint,
        }

    @property
    def fingerprint(self) -> str:
        with self._lock:
            payload = [
                (
                    profile.spec.skill_id,
                    profile.episode_count,
                    profile.success.alpha,
                    profile.success.beta,
                    profile.verification.alpha,
                    profile.verification.beta,
                    profile.latency.mean,
                    profile.cost.mean,
                    profile.failure_streak,
                    profile.retired,
                )
                for profile in sorted(self._profiles.values(), key=lambda item: item.spec.skill_id)
            ]
            return stable_fingerprint(payload)

    def _update_profile(self, profile: SkillProfile, episode: ActionEpisode) -> SkillProfile:
        success_weight, failure_weight = self._outcome_weights(episode)
        success = profile.success.observe(success_weight, failure_weight)
        verification = profile.verification.observe(
            episode.verification_score if episode.verified else 0.0,
            (1.0 - episode.verification_score) if episode.verified else 1.0,
        )
        latency = profile.latency.update(episode.latency_ms)
        cost = profile.cost.update(episode.cost)
        attempts = profile.attempts.update(float(episode.attempts))
        failure_modes = Counter(profile.failure_modes)
        if episode.outcome not in {OutcomeKind.SUCCESS} and episode.failure_mode:
            failure_modes[episode.failure_mode] += 1
        contexts = dict(profile.contexts)
        context_profile = contexts.get(episode.context.key) or ContextPerformance(context_key=episode.context.key)
        context_failure_modes = Counter(context_profile.failure_modes)
        if episode.outcome not in {OutcomeKind.SUCCESS} and episode.failure_mode:
            context_failure_modes[episode.failure_mode] += 1
        contexts[episode.context.key] = replace(
            context_profile,
            success=context_profile.success.observe(success_weight, failure_weight),
            verification=context_profile.verification.observe(
                episode.verification_score if episode.verified else 0.0,
                (1.0 - episode.verification_score) if episode.verified else 1.0,
            ),
            latency=context_profile.latency.update(episode.latency_ms),
            cost=context_profile.cost.update(episode.cost),
            attempts=context_profile.attempts.update(float(episode.attempts)),
            failure_modes=dict(context_failure_modes),
            episode_count=context_profile.episode_count + 1,
            last_used_at=episode.ended_at,
        )
        success_event = episode.outcome is OutcomeKind.SUCCESS and episode.verified
        failure_event = episode.outcome in {OutcomeKind.FAILURE, OutcomeKind.TIMEOUT, OutcomeKind.DENIED}
        return replace(
            profile,
            success=success,
            verification=verification,
            latency=latency,
            cost=cost,
            attempts=attempts,
            failure_modes=dict(failure_modes),
            contexts=contexts,
            episode_count=profile.episode_count + 1,
            success_streak=profile.success_streak + 1 if success_event else 0,
            failure_streak=profile.failure_streak + 1 if failure_event else 0,
            last_used_at=episode.ended_at,
            last_success_at=episode.ended_at if success_event else profile.last_success_at,
            last_failure_at=episode.ended_at if failure_event else profile.last_failure_at,
        )

    @staticmethod
    def _outcome_weights(episode: ActionEpisode) -> tuple[float, float]:
        verification = episode.verification_score if episode.verified else 0.25
        if episode.outcome is OutcomeKind.SUCCESS:
            return max(0.25, verification), 0.0
        if episode.outcome is OutcomeKind.PARTIAL:
            return 0.35 * verification, 0.65
        if episode.outcome is OutcomeKind.UNKNOWN:
            return 0.10, 0.10
        if episode.outcome is OutcomeKind.CANCELLED:
            return 0.0, 0.20
        if episode.outcome is OutcomeKind.DENIED:
            return 0.0, 0.40
        if episode.outcome is OutcomeKind.TIMEOUT:
            return 0.0, 0.85
        return 0.0, 1.0

    def _context_adjusted_success(self, profile: SkillProfile, context: ContextSignature) -> tuple[float, float, int]:
        if not profile.contexts:
            return profile.empirical_success, 0.5, 0
        best_similarity = -1.0
        best: ContextPerformance | None = None
        # Context keys are hashed, so reconstructing exact signatures is not possible
        # from the profile. Episodes retain signatures and provide the nearest match.
        candidate_signatures: dict[str, ContextSignature] = {}
        for episode in reversed(self._episodes):
            if episode.skill_id == profile.spec.skill_id and episode.context.key not in candidate_signatures:
                candidate_signatures[episode.context.key] = episode.context
        for key, performance in profile.contexts.items():
            signature = candidate_signatures.get(key)
            similarity = context.similarity(signature) if signature is not None else 0.0
            if similarity > best_similarity:
                best_similarity = similarity
                best = performance
        if best is None:
            return profile.empirical_success, 0.0, 0
        shrinkage = min(0.85, best.episode_count / (best.episode_count + 5.0)) * max(0.0, best_similarity)
        adjusted = profile.empirical_success * (1.0 - shrinkage) + best.success.mean * shrinkage
        return adjusted, max(0.0, best_similarity), best.episode_count

    def _best_context_posterior(self, profile: SkillProfile, context: ContextSignature) -> BetaPosterior:
        _, similarity, _ = self._context_adjusted_success(profile, context)
        if not profile.contexts or similarity <= 0:
            return profile.success
        candidate_signatures: dict[str, ContextSignature] = {}
        for episode in reversed(self._episodes):
            if episode.skill_id == profile.spec.skill_id and episode.context.key not in candidate_signatures:
                candidate_signatures[episode.context.key] = episode.context
        best_key = max(
            profile.contexts,
            key=lambda key: context.similarity(candidate_signatures.get(key, ContextSignature(domain="unknown", environment="unknown"))),
        )
        performance = profile.contexts[best_key]
        weight = max(0.0, min(1.0, similarity))
        return BetaPosterior(
            alpha=profile.success.alpha * (1.0 - weight) + performance.success.alpha * weight,
            beta=profile.success.beta * (1.0 - weight) + performance.success.beta * weight,
        )

    @classmethod
    def _risk_allowed(cls, risk: RiskTier, maximum: RiskTier) -> bool:
        order = [RiskTier.READ_ONLY, RiskTier.REVERSIBLE, RiskTier.MUTATING, RiskTier.EXTERNAL, RiskTier.HIGH_IMPACT]
        return order.index(risk) <= order.index(maximum)

    @staticmethod
    def _latency_normalizer(candidates: Sequence[SkillProfile], explicit_budget: float | None) -> Callable[[float], float]:
        observed = [
            profile.latency.mean if profile.latency.count else profile.spec.nominal_latency_ms
            for profile in candidates
        ]
        scale = explicit_budget if explicit_budget is not None else max(1.0, max(observed, default=1.0))
        scale = max(1.0, float(scale))
        return lambda value: math.exp(-max(0.0, value) / scale)

    @staticmethod
    def _cost_normalizer(candidates: Sequence[SkillProfile], explicit_budget: float | None) -> Callable[[float], float]:
        observed = [profile.cost.mean if profile.cost.count else profile.spec.nominal_cost for profile in candidates]
        scale = explicit_budget if explicit_budget is not None else max(1e-6, max(observed, default=1.0))
        scale = max(1e-6, float(scale))
        return lambda value: math.exp(-max(0.0, value) / scale)

    def _reject_dependency_cycles(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(skill_id: str) -> None:
            if skill_id in visiting:
                raise ActionModelError("skill dependency graph contains a cycle")
            if skill_id in visited:
                return
            visiting.add(skill_id)
            profile = self._profiles.get(skill_id)
            if profile is not None:
                for dependency in profile.spec.dependencies:
                    if dependency in self._profiles:
                        visit(dependency)
            visiting.remove(skill_id)
            visited.add(skill_id)

        for skill_id in self._profiles:
            visit(skill_id)


@dataclass(frozen=True, slots=True)
class CompositeStep:
    skill_id: str
    required: bool = True
    success_threshold: float = 0.60

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill_id", require_id("skill_id", self.skill_id))
        object.__setattr__(self, "success_threshold", probability("success_threshold", self.success_threshold))


@dataclass(frozen=True, slots=True)
class CompositeSkillPlan:
    composite_id: str
    steps: tuple[CompositeStep, ...]
    predicted_success: float
    predicted_latency_ms: float
    predicted_cost: float
    weakest_link_skill_id: str | None


class SkillComposer:
    """Build conservative composite success estimates from learned skills."""

    def __init__(self, library: SkillLibrary) -> None:
        self.library = library

    def compose(self, steps: Sequence[CompositeStep]) -> CompositeSkillPlan:
        if not steps:
            raise ValueError("composite requires at least one step")
        if any(not isinstance(step, CompositeStep) for step in steps):
            raise TypeError("steps must contain CompositeStep")
        success = 1.0
        latency = 0.0
        cost = 0.0
        weakest: tuple[float, str] | None = None
        for step in steps:
            profile = self.library.require_profile(step.skill_id)
            step_success = profile.empirical_success
            if step.required:
                success *= step_success
            else:
                success *= 0.5 + 0.5 * step_success
            latency += profile.latency.mean if profile.latency.count else profile.spec.nominal_latency_ms
            cost += profile.cost.mean if profile.cost.count else profile.spec.nominal_cost
            if weakest is None or step_success < weakest[0]:
                weakest = (step_success, step.skill_id)
        payload = [(step.skill_id, step.required, step.success_threshold) for step in steps]
        return CompositeSkillPlan(
            composite_id=stable_id("composite", payload),
            steps=tuple(steps),
            predicted_success=max(0.0, min(1.0, success)),
            predicted_latency_ms=latency,
            predicted_cost=cost,
            weakest_link_skill_id=weakest[1] if weakest else None,
        )

    def viable(self, plan: CompositeSkillPlan) -> bool:
        for step in plan.steps:
            profile = self.library.require_profile(step.skill_id)
            if step.required and profile.empirical_success < step.success_threshold:
                return False
        return True
