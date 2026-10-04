from __future__ import annotations

import hashlib

import pytest

from skeleton.eval.experiment_registry import (
    ExperimentBudget, ExperimentEligibility, ExperimentManifest,
    ExperimentMetric, MetricDirection, TrafficMode,
)
from skeleton.learning.mirror_room import (
    AdversarialMirrorRoom, AdversarialRatchetPolicy, EpisodeOutcome,
    FixedAdversarialSuite, HighEndContentConstitution,
    IndependentQualityJudgeReceipt, MirrorBudget,
    MirrorCandidate, MirrorMetricPolicy, MirrorRoomError, MirrorRoomSpec,
    MirrorScenario, SandboxPolicy, ScenarioSplit,
    qualify_high_end_content_delivery,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


CONSTITUTION = HighEndContentConstitution.canonical()


def _spec() -> MirrorRoomSpec:
    manifest = ExperimentManifest(
        experiment_id="exp.high-end-content.v1",
        hypothesis="100 adversarial attempts ratchet all content quality dimensions.",
        owner="p1-learning",
        source_commit="a" * 40,
        environment_id="mirror.high-end-content.offline",
        candidate_ref="candidate:high-end-content.v1",
        eligibility=ExperimentEligibility(
            traffic_mode=TrafficMode.OFFLINE,
            max_traffic_fraction=0.0,
            allowed_data_classes=("public",),
            tenant_ids=(),
            external_side_effects_allowed=False,
        ),
        budget=ExperimentBudget(
            max_samples=12_000, max_tokens=300_000,
            max_cost_units=300.0, max_wall_time_s=7200.0,
        ),
        metrics=tuple(
            ExperimentMetric(
                metric_id=d.metric_id,
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=1,
                source=f"independent-{d.dimension_id}",
            )
            for d in CONSTITUTION.dimensions
        ),
        parent_experiment_id=None,
        tags=("mirror-room", "high-end-content", "100-attempt"),
    )
    return MirrorRoomSpec(
        manifest=manifest,
        production_baseline=MirrorCandidate(
            candidate_id="content-v000", version="version-content-v000",
            producer_id="release", change_ref="change:content-v000",
            change_digest=_sha("content-v000"), parameters={"quality": 0.0},
        ),
        metrics=tuple(
            MirrorMetricPolicy(
                metric_id=d.metric_id, direction=MetricDirection.MAXIMIZE,
                minimum_improvement=0.0001, confidence_level=0.95,
                weight=d.weight,
            )
            for d in CONSTITUTION.dimensions
        ),
        sandbox_policy=SandboxPolicy(
            allowed_capabilities=("compute",), max_steps_per_episode=2,
            max_tokens_per_episode=16, max_cost_units_per_episode=0.02,
        ),
        budget=MirrorBudget(
            max_generations=100, max_candidates_per_generation=1,
            max_episodes=12_000, max_total_steps=24_000,
            max_total_tokens=192_000, max_total_cost_units=240.0,
        ),
        hard_example_limit=16,
        stagnation_patience=100,
    )


def _base_scenarios():
    return (
        MirrorScenario("content-train", ScenarioSplit.TRAIN, {"difficulty": .001, "kind": "base"}),
        MirrorScenario(
            "content-validation",
            ScenarioSplit.VALIDATION,
            {"difficulty": 0.0, "kind": "validation"},
        ),
        MirrorScenario("content-holdout-a", ScenarioSplit.HOLDOUT, {"difficulty": .010, "kind": "holdout-a"}),
        MirrorScenario("content-holdout-b", ScenarioSplit.HOLDOUT, {"difficulty": .012, "kind": "holdout-b"}),
    )


def _challenges():
    dims = [x.dimension_id for x in CONSTITUTION.dimensions]
    families = (
        "ambiguity",
        "counterexample",
        "constraint-collision",
        "distribution-shift",
        "long-context",
    )
    return tuple(
        MirrorScenario(
            f"content-attack-{attempt:03d}",
            ScenarioSplit.TRAIN,
            {
                "difficulty": .002 + attempt * .00002,
                "attempt": attempt,
                "kind": "adversarial-content",
            },
            tags=(
                "adversarial",
                f"quality:{dims[(attempt - 1) % len(dims)]}",
                (
                    "attack:"
                    + families[
                        ((attempt - 1) // len(dims)) % len(families)
                    ]
                ),
            ),
        )
        for attempt in range(1, 101)
    )


class ContentExecutor:
    executor_id = "independent-content-evaluator"

    def execute(self, *, candidate, scenario, seed, policy):
        value = min(1.0, max(
            0.0,
            .93 + float(candidate.parameters["quality"]) - float(scenario.payload["difficulty"]),
        ))
        return EpisodeOutcome(
            metric_values={d.metric_id: value for d in CONSTITUTION.dimensions},
            observation_digest=_sha(f"{candidate.digest}:{scenario.digest}:{seed}:{value}"),
            steps=1, tokens=4, cost_units=.005, capabilities_used=("compute",),
        )


class ContentGenerator:
    generator_id = "content-ratchet-learner"

    def __init__(self):
        self.calls = 0

    def propose(self, feedback, *, limit):
        self.calls += 1
        quality = float(feedback.champion.parameters["quality"]) + .0007
        cid = f"content-v{self.calls:03d}"
        return (MirrorCandidate(
            candidate_id=cid, version=f"version-{cid}",
            producer_id=self.generator_id, change_ref=f"change:{cid}",
            change_digest=_sha(f"{cid}:{quality}"),
            parameters={"quality": quality},
            parent_candidate_id=feedback.champion.candidate_id,
            evidence_refs=(f"proposal:{cid}",),
        ),)


def _campaign(*, attempts=None, challenges=None):
    actual = challenges or _challenges()
    room = AdversarialMirrorRoom(
        _spec(), ContentExecutor(),
        FixedAdversarialSuite(
            adversary_id="independent-content-red-team",
            challenges=actual,
        ),
        policy=AdversarialRatchetPolicy(minimum_accepted_upgrades=10),
    )
    return room.run(
        run_id="high-end-content",
        generator=ContentGenerator(),
        scenarios=_base_scenarios(),
        attempts=attempts,
    ), actual



def _judges(campaign):
    scores = {
        dimension.dimension_id: 0.99
        for dimension in CONSTITUTION.dimensions
    }
    return tuple(
        IndependentQualityJudgeReceipt(
            judge_id=f"quality-judge-{index}",
            channel_id=f"quality-channel-{index}",
            candidate_digest=campaign.final_baseline.digest,
            constitution_digest=CONSTITUTION.digest,
            dimension_scores=scores,
            evidence_digest=_sha(f"judge-evidence-{index}"),
            calibration_digest=_sha(f"judge-calibration-{index}"),
            evaluated_at=100,
        )
        for index in range(1, CONSTITUTION.minimum_blind_judges + 1)
    )


@pytest.fixture(scope="module")
def complete_campaign():
    return _campaign()


def test_high_end_content_dossier_requires_full_ratchet_gauntlet_and_holdout(
    complete_campaign,
):
    campaign, challenges = complete_campaign
    dossier = qualify_high_end_content_delivery(
        campaign, constitution=CONSTITUTION, challenge_catalog=challenges,
        judge_receipts=_judges(campaign),
        verifier_id="high-end-delivery-verifier",
        evaluation_refs=("eval:red-team", "eval:quality-panel", "eval:sealed-holdout"),
        verified_at=100,
    )
    assert dossier.attempts_completed == 100
    assert dossier.accepted_upgrades == 100
    assert campaign.gauntlet_report is not None and campaign.gauntlet_report.passed
    assert dossier.final_candidate_id == "content-v100"
    assert (
        dossier.overall_validation_score
        >= CONSTITUTION.minimum_overall_validation_score
    )
    assert (
        dossier.overall_validation_gain
        >= CONSTITUTION.minimum_cumulative_validation_gain
    )
    assert (
        dossier.overall_gauntlet_score
        >= CONSTITUTION.minimum_overall_gauntlet_score
    )
    assert (
        dossier.overall_holdout_score
        >= CONSTITUTION.minimum_overall_holdout_score
    )
    assert (
        dossier.worst_case_holdout_score
        >= CONSTITUTION.minimum_worst_case_holdout_score
    )
    assert all(
        value >= CONSTITUTION.minimum_dimension_lift
        for value in dossier.validation_lifts.values()
    )
    assert all(
        value >= CONSTITUTION.minimum_attacks_per_dimension
        for value in dossier.attack_counts.values()
    )
    assert all(
        value >= CONSTITUTION.minimum_attack_families_per_dimension
        for value in dossier.attack_family_counts.values()
    )
    assert (
        dossier.judge_panel_maximum_spread
        <= CONSTITUTION.maximum_judge_spread
    )
    assert dossier.production_authority is False
    bars = [
        item.required_weighted_gain
        for item in campaign.attempts
    ]
    assert bars[-1] / bars[0] >= (
        CONSTITUTION.minimum_standard_escalation_ratio
    )
    assert all(
        sum(
            int(item.accepted)
            for item in campaign.attempts
            if start <= item.attempt <= start + 24
        ) >= CONSTITUTION.minimum_upgrades_per_quartile
        for start in (1, 26, 51, 76)
    )
    assert dossier.evidence_ref().category == "mirror_room_high_end_content_delivery"


def test_high_end_delivery_is_blocked_before_attempt_100():
    campaign, challenges = _campaign(attempts=3)
    with pytest.raises(MirrorRoomError, match="not ready"):
        qualify_high_end_content_delivery(
            campaign, constitution=CONSTITUTION, challenge_catalog=challenges,
            judge_receipts=_judges(campaign),
            verifier_id="high-end-delivery-verifier",
            evaluation_refs=("eval:red-team", "eval:quality-panel", "eval:sealed-holdout"),
            verified_at=3,
        )


def test_quality_constitution_requires_broad_adversarial_coverage():
    first = CONSTITUTION.dimensions[0].dimension_id
    narrow = tuple(
        MirrorScenario(
            f"narrow-attack-{attempt:03d}", ScenarioSplit.TRAIN,
            {"difficulty": .002 + attempt * .00002, "attempt": attempt, "kind": "narrow-content"},
            tags=("adversarial", f"quality:{first}", "attack:single"),
        )
        for attempt in range(1, 101)
    )
    campaign, catalog = _campaign(challenges=narrow)
    with pytest.raises(
        MirrorRoomError,
        match="insufficient adversarial (coverage|family diversity)",
    ):
        qualify_high_end_content_delivery(
            campaign, constitution=CONSTITUTION, challenge_catalog=catalog,
            judge_receipts=_judges(campaign),
            verifier_id="high-end-delivery-verifier",
            evaluation_refs=("eval:red-team", "eval:quality-panel", "eval:sealed-holdout"),
            verified_at=100,
        )


def test_quality_catalog_digest_drift_fails_closed(complete_campaign):
    campaign, challenges = complete_campaign
    changed = list(challenges)
    first = changed[0]
    changed[0] = MirrorScenario(
        first.scenario_id, first.split, dict(first.payload),
        tags=("adversarial", "quality:style"),
    )
    with pytest.raises(MirrorRoomError, match="digest drift"):
        qualify_high_end_content_delivery(
            campaign, constitution=CONSTITUTION, challenge_catalog=tuple(changed),
            judge_receipts=_judges(campaign),
            verifier_id="high-end-delivery-verifier",
            evaluation_refs=("eval:red-team", "eval:quality-panel", "eval:sealed-holdout"),
            verified_at=100,
        )

def test_high_end_delivery_rejects_non_independent_judge_panel(
    complete_campaign,
):
    campaign, challenges = complete_campaign
    with pytest.raises(
        MirrorRoomError,
        match="configured independent quality judges",
    ):
        qualify_high_end_content_delivery(
            campaign,
            constitution=CONSTITUTION,
            challenge_catalog=challenges,
            judge_receipts=_judges(campaign)[
                : CONSTITUTION.minimum_blind_judges - 1
            ],
            verifier_id="high-end-delivery-verifier",
            evaluation_refs=(
                "eval:red-team",
                "eval:quality-panel",
                "eval:sealed-holdout",
            ),
            verified_at=100,
        )

def test_canonical_high_end_constitution_is_sota_hardened() -> None:
    assert len(CONSTITUTION.dimensions) >= 15
    assert CONSTITUTION.minimum_accepted_upgrades >= 25
    assert CONSTITUTION.minimum_blind_judges >= 5
    assert CONSTITUTION.minimum_cumulative_validation_gain >= 0.02
    assert CONSTITUTION.minimum_dimension_lift >= 0.01
    assert CONSTITUTION.minimum_attack_families_per_dimension >= 3
    assert CONSTITUTION.minimum_standard_escalation_ratio >= 4.0
    assert CONSTITUTION.minimum_upgrades_per_quartile >= 3


def test_high_end_delivery_rejects_attack_family_monoculture() -> None:
    dims = [x.dimension_id for x in CONSTITUTION.dimensions]
    monoculture = tuple(
        MirrorScenario(
            f"mono-attack-{attempt:03d}",
            ScenarioSplit.TRAIN,
            {
                "difficulty": .002 + attempt * .00002,
                "attempt": attempt,
                "kind": "family-monoculture",
            },
            tags=(
                "adversarial",
                f"quality:{dims[(attempt - 1) % len(dims)]}",
                "attack:single-family",
            ),
        )
        for attempt in range(1, 101)
    )
    campaign, catalog = _campaign(challenges=monoculture)
    with pytest.raises(
        MirrorRoomError,
        match="insufficient adversarial coverage: family diversity",
    ):
        qualify_high_end_content_delivery(
            campaign,
            constitution=CONSTITUTION,
            challenge_catalog=catalog,
            judge_receipts=_judges(campaign),
            verifier_id="high-end-delivery-verifier",
            evaluation_refs=(
                "eval:red-team",
                "eval:quality-panel",
                "eval:sealed-holdout",
            ),
            verified_at=100,
        )


def test_high_end_delivery_rejects_wide_blind_judge_disagreement(
    complete_campaign,
) -> None:
    campaign, challenges = complete_campaign
    judges = list(_judges(campaign))
    scores = dict(judges[0].dimension_scores)
    scores["style"] = max(
        CONSTITUTION.dimensions[
            [d.dimension_id for d in CONSTITUTION.dimensions].index("style")
        ].minimum_holdout_floor,
        0.90,
    )
    first = judges[0]
    judges[0] = IndependentQualityJudgeReceipt(
        judge_id=first.judge_id,
        channel_id=first.channel_id,
        candidate_digest=first.candidate_digest,
        constitution_digest=first.constitution_digest,
        dimension_scores=scores,
        evidence_digest=first.evidence_digest,
        calibration_digest=first.calibration_digest,
        evaluated_at=first.evaluated_at,
    )

    with pytest.raises(
        MirrorRoomError,
        match="judge panel disagreement too wide",
    ):
        qualify_high_end_content_delivery(
            campaign,
            constitution=CONSTITUTION,
            challenge_catalog=challenges,
            judge_receipts=tuple(judges),
            verifier_id="high-end-delivery-verifier",
            evaluation_refs=(
                "eval:red-team",
                "eval:quality-panel",
                "eval:sealed-holdout",
            ),
            verified_at=100,
        )
