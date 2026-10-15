"""Deterministic evidence-aware curriculum for actual ROM emulator training.

Repeated actual emulator receipts, rather than invented priors or 'skill
levels', choose the next experimental perspective. A source episode's return
may be only visual-change reward and is NEVER treated as a win signal.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .game_learning import _digest

CURRICULUM_SCHEMA = "skeleton.game.emulator_evidence_curriculum.v1"
ANGLES = (
    "exploration", "policy", "adversarial", "temporal", "boundary",
    "recovery", "perturbation", "causal", "reversal", "boomerang",
)


class EmulatorCurriculumError(ValueError):
    pass


@dataclass(frozen=True)
class CurriculumRecord:
    angle: str
    run_index: int
    transitions: int
    new_signatures: int
    return_sum: float
    counterfactual_diversity: float
    actual_replay_steps: int
    training_actions: tuple[str, ...]
    verified: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "angle": self.angle,
            "run_index": self.run_index,
            "transitions": self.transitions,
            "new_signatures": self.new_signatures,
            "return_sum": self.return_sum,
            "counterfactual_diversity": self.counterfactual_diversity,
            "actual_replay_steps": self.actual_replay_steps,
            "training_actions": list(self.training_actions),
            "verified": self.verified,
        }


class EvidenceCurriculum:
    """Bounded UCB-style angle selection grounded in *audited* gameplay data."""

    def __init__(self, actions: Sequence[str], *, seed: int = 0) -> None:
        if (
            not isinstance(actions, (list, tuple)) or not 2 <= len(actions) <= 32
            or any(not isinstance(item, str) or not item or len(item) > 64 for item in actions)
            or len(set(actions)) != len(actions)
        ):
            raise EmulatorCurriculumError("typed, bounded training action basis required")
        if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise EmulatorCurriculumError("curriculum seed exceeds bounds")
        self.actions = tuple(actions)
        self.seed = seed
        self.records: list[CurriculumRecord] = []
        self._action_uses = {action: 0 for action in self.actions}

    def _angle_records(self, angle: str) -> list[CurriculumRecord]:
        return [item for item in self.records if item.angle == angle]

    def select(self) -> tuple[str, dict[str, Any]]:
        index = len(self.records)
        if index >= 256:
            raise EmulatorCurriculumError("curriculum lifetime exhausted")
        untried = [angle for angle in ANGLES if not self._angle_records(angle)]
        if untried:
            selected = untried[0]
            return selected, {
                "policy": "mandatory_ten_angle_coverage",
                "angle": selected,
                "run_index": index,
                "selected_for_proof_before_exploitation": True,
            }
        total = len(self.records)
        scores = {}
        for angle in ANGLES:
            history = self._angle_records(angle)
            count = len(history)
            gain = math.fsum(item.new_signatures / max(1, item.transitions)
                             for item in history) / count
            contrast = math.fsum(item.counterfactual_diversity for item in history) / count
            novelty_uncertainty = math.sqrt(2 * math.log(total + 1) / count)
            time_since = (total - 1 - max(item.run_index for item in history)) / total
            recent = history[-3:]
            persistence = (sum(item.new_signatures > 0 for item in recent) / len(recent))
            mean_cost = math.fsum(item.actual_replay_steps / max(1, item.transitions)
                                 for item in history) / count
            # All components are epistemic proxies, not achievement/skill.
            scores[angle] = (
                2.0 * gain
                + 0.55 * contrast
                + 0.4 * novelty_uncertainty
                + 0.35 * time_since
                + 0.3 * persistence
                - 0.035 * min(mean_cost, 16)
            )
        # A seeded tie-break prevents order bias while remaining reproducible.
        selected = max(
            ANGLES,
            key=lambda angle: (
                scores[angle],
                _digest([self.seed, total, angle]),
            ),
        )
        return selected, {
            "policy": "audited_novelty_ucb_with_revisit",
            "angle": selected,
            "run_index": index,
            "priority_score": scores[selected],
            "score_evidence": scores,
            "source_kind": "replayed_visual_transition_statistics",
            "achievement_or_capability_claim": False,
        }

    def least_observed_action(self) -> str:
        return min(
            self.actions,
            key=lambda action: (
                self._action_uses[action],
                _digest([self.seed, "rare_action", action]),
            ),
        )

    def observe(self, *, angle: str, run_index: int, trace: Mapping[str, Any],
                receipt: Mapping[str, Any], new_signatures: int) -> dict[str, Any]:
        if angle not in ANGLES or type(run_index) is not int or run_index != len(self.records):
            raise EmulatorCurriculumError("curriculum execution order differs")
        if (
            not isinstance(trace, Mapping) or not isinstance(receipt, Mapping)
            or not isinstance(trace.get("transitions"), list)
            or not isinstance(receipt.get("scrutiny_checks"), Mapping)
            or len(receipt["scrutiny_checks"]) < 10
            or not all(receipt["scrutiny_checks"].values())
            or trace.get("trace_digest") != receipt.get("trace_digest")
        ):
            raise EmulatorCurriculumError("unverified/foreign source cannot update curriculum")
        rows = trace["transitions"]
        if (
            not rows or len(rows) > 128 or receipt.get("actual_steps") != len(rows)
            or type(new_signatures) is not int
            or not 0 <= new_signatures <= len(rows)
        ):
            raise EmulatorCurriculumError("source transition/novelty budget differs")
        actions = []
        for row in rows:
            if row.get("action") not in self._action_uses:
                raise EmulatorCurriculumError("source action differs from approved control space")
            actions.append(row["action"])
        raw_contrasts = receipt.get("counterfactual_probes", [])
        if type(raw_contrasts) is not list or len(raw_contrasts) > 16:
            raise EmulatorCurriculumError("counterfactual evidence budget exceeded")
        frames = [sample.get("actual_frame_sha256") for sample in raw_contrasts]
        if any(type(value) is not str or len(value) != 64 for value in frames):
            raise EmulatorCurriculumError("unverified counterfactual frame")
        diversity = len(set(frames)) / len(frames) if frames else 0.0
        reward = trace.get("return")
        if type(reward) not in (float, int) or not math.isfinite(reward):
            raise EmulatorCurriculumError("source reward must be finite")
        replays = receipt.get("actual_replay_steps")
        if type(replays) is not int or replays < len(rows):
            raise EmulatorCurriculumError("reverse replay step accounting differs")
        record = CurriculumRecord(
            angle=angle,
            run_index=run_index,
            transitions=len(rows),
            new_signatures=new_signatures,
            return_sum=float(reward),
            counterfactual_diversity=diversity,
            actual_replay_steps=replays,
            training_actions=tuple(actions),
            verified=True,
        )
        for action in actions:
            self._action_uses[action] += 1
        self.records.append(record)
        return {
            "record": record.as_dict(),
            "least_observed_action": self.least_observed_action(),
            "verified_curriculum_digest": self.digest,
        }

    @property
    def digest(self) -> str:
        return _digest({
            "schema_version": CURRICULUM_SCHEMA,
            "actions": self.actions,
            "seed": self.seed,
            "records": [item.as_dict() for item in self.records],
        })

    def report(self) -> dict[str, Any]:
        if not self.records:
            raise EmulatorCurriculumError("cannot report unmeasured curriculum")
        by_angle: dict[str, dict[str, Any]] = {}
        for angle in ANGLES:
            runs = self._angle_records(angle)
            by_angle[angle] = {
                "verified_runs": len(runs),
                "source_measured_steps": sum(item.transitions for item in runs),
                "new_visual_signatures": sum(item.new_signatures for item in runs),
                "actual_reverse_replay_steps": sum(item.actual_replay_steps for item in runs),
                "average_counterfactual_frame_diversity": (
                    math.fsum(item.counterfactual_diversity for item in runs) / len(runs)
                    if runs else None
                ),
                "has_full_angle_coverage": bool(runs),
            }
        result = {
            "schema_version": CURRICULUM_SCHEMA,
            "curriculum_digest": self.digest,
            "source_run_count": len(self.records),
            "angle_coverage": sum(bool(self._angle_records(angle)) for angle in ANGLES),
            "angle_coverage_target": len(ANGLES),
            "actions": dict(self._action_uses),
            "by_angle": by_angle,
            "limits": {
                "adaptation_signal": "actual replay-verified visual novelty and control contrast",
                "game_skill_inferred": False,
                "model_neural_parameter_updates": 0,
                "heldout_data_used_to_choose_training_actions": False,
            },
        }
        result["report_digest"] = _digest(result)
        return result
