"""Deterministic local post-training, RL, curriculum and verifier programs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping, Sequence

from .native import (
    DatasetManifest,
    DatasetRecord,
    NativeTrainingConfig,
    NativeTrainingControlPlane,
    NativeTrainingResult,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class PreferencePair:
    pair_id: str
    prompt: str
    chosen: str
    rejected: str
    source_ref: str
    license_id: str = "CC0-1.0"

    def __post_init__(self) -> None:
        for name in ("pair_id","prompt","chosen","rejected","source_ref","license_id"):
            if not str(getattr(self,name)).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.chosen.strip()==self.rejected.strip():
            raise ValueError("chosen and rejected must differ")


class PreferenceWeightedPostTrainer:
    """Convert preference evidence into a lineage-preserving weighted corpus."""

    def __init__(self, control: NativeTrainingControlPlane | None = None) -> None:
        self.control=control or NativeTrainingControlPlane()

    def build_dataset(
        self,
        base: DatasetManifest,
        preferences: Sequence[PreferencePair],
        *,
        chosen_weight: int = 3,
    ) -> DatasetManifest:
        if not 1 <= chosen_weight <= 32:
            raise ValueError("chosen_weight must be in [1, 32]")
        records=list(base.records)
        for pair in preferences:
            parent_ref="preference:"+pair.pair_id
            unit=(pair.prompt.strip()+" "+pair.chosen.strip()).strip()
            records.append(
                DatasetRecord(
                    record_id=f"pref-{pair.pair_id}-chosen-weight-{chosen_weight}",
                    text=" ".join(unit for _ in range(chosen_weight)),
                    source_ref=pair.source_ref,
                    license_id=pair.license_id,
                    usage_grant="train_eval",
                    synthetic_parent_refs=(parent_ref,),
                )
            )
        return DatasetManifest(
            dataset_id=base.dataset_id+"-post",
            version=base.version+"+preferences",
            records=tuple(records),
            purpose="local-model-post-training",
        )

    def train(
        self,
        base: DatasetManifest,
        preferences: Sequence[PreferencePair],
        config: NativeTrainingConfig,
        *,
        chosen_weight: int = 3,
    ) -> NativeTrainingResult:
        dataset=self.build_dataset(base,preferences,chosen_weight=chosen_weight)
        return self.control.train(dataset,config,holdout=dataset)


@dataclass(frozen=True, slots=True)
class RLTransition:
    state: str
    action: str
    next_state: str
    reward: float
    terminal: bool = False


class DeterministicRLEnvironment:
    """Finite table environment with explicit reset and transition identity."""

    def __init__(
        self,
        *,
        environment_id: str,
        initial_state: str,
        transitions: Sequence[RLTransition],
    ) -> None:
        if not environment_id.strip() or not initial_state.strip():
            raise ValueError("environment identity must be non-empty")
        table: dict[tuple[str,str],RLTransition]={}
        for transition in transitions:
            key=(transition.state,transition.action)
            if key in table:
                raise ValueError(f"duplicate RL transition: {key}")
            table[key]=transition
        if not table:
            raise ValueError("RL environment requires transitions")
        self.environment_id=environment_id
        self.initial_state=initial_state
        self._table=table
        self._state=initial_state
        self._episode_steps=0

    @property
    def state(self) -> str:
        return self._state

    def reset(self) -> str:
        self._state=self.initial_state
        self._episode_steps=0
        return self._state

    def step(self, action: str) -> RLTransition:
        try:
            transition=self._table[(self._state,action)]
        except KeyError as exc:
            raise ValueError(f"invalid action {action!r} from state {self._state!r}") from exc
        self._state=transition.next_state
        self._episode_steps+=1
        return transition

    def rollout(self, actions: Sequence[str]) -> tuple[RLTransition,...]:
        self.reset()
        observed=[]
        for action in actions:
            transition=self.step(action)
            observed.append(transition)
            if transition.terminal:
                break
        return tuple(observed)

    @property
    def digest(self) -> str:
        rows=[
            {
                "state":t.state,"action":t.action,"next_state":t.next_state,
                "reward":t.reward,"terminal":t.terminal,
            }
            for _,t in sorted(self._table.items())
        ]
        return _digest({"environment_id":self.environment_id,"initial_state":self.initial_state,"transitions":rows})


@dataclass(frozen=True, slots=True)
class CurriculumStage:
    stage_id: str
    minimum_score: float
    capability_ref: str

    def __post_init__(self) -> None:
        if not self.stage_id.strip() or not self.capability_ref.strip():
            raise ValueError("curriculum stage identity must be non-empty")
        if not 0.0 <= self.minimum_score <= 1.0:
            raise ValueError("minimum_score must be in [0, 1]")


class CurriculumEngine:
    def __init__(self, stages: Sequence[CurriculumStage]) -> None:
        if not stages:
            raise ValueError("curriculum requires stages")
        if len({stage.stage_id for stage in stages}) != len(stages):
            raise ValueError("curriculum stage ids must be unique")
        self.stages=tuple(stages)

    def unlocked(self, scores: Mapping[str,float]) -> tuple[str,...]:
        unlocked=[]
        for stage in self.stages:
            score=float(scores.get(stage.capability_ref,0.0))
            if score >= stage.minimum_score:
                unlocked.append(stage.stage_id)
            else:
                break
        return tuple(unlocked)

    def next_stage(self, scores: Mapping[str,float]) -> CurriculumStage | None:
        unlocked=set(self.unlocked(scores))
        return next((stage for stage in self.stages if stage.stage_id not in unlocked),None)


@dataclass(frozen=True, slots=True)
class VerifierCalibration:
    threshold: float
    accuracy: float
    false_positive_rate: float
    sample_count: int
    calibration_digest: str


class VerifierProgram:
    """Calibrate a scalar verifier threshold from independent labeled evidence."""

    def __init__(self, verifier_id: str) -> None:
        if not verifier_id.strip():
            raise ValueError("verifier_id must be non-empty")
        self.verifier_id=verifier_id

    def calibrate(
        self,
        samples: Sequence[tuple[float,bool]],
    ) -> VerifierCalibration:
        if len(samples)<2 or not any(label for _,label in samples) or not any(not label for _,label in samples):
            raise ValueError("calibration requires positive and negative samples")
        candidates=sorted({0.0,1.0,*[float(score) for score,_ in samples]})
        best=None
        for threshold in candidates:
            tp=tn=fp=fn=0
            for score,label in samples:
                predicted=float(score)>=threshold
                if predicted and label: tp+=1
                elif predicted and not label: fp+=1
                elif not predicted and not label: tn+=1
                else: fn+=1
            accuracy=(tp+tn)/len(samples)
            fpr=0.0 if fp+tn==0 else fp/(fp+tn)
            key=(accuracy,-fpr,threshold)
            if best is None or key>best[0]:
                best=(key,threshold,accuracy,fpr)
        assert best is not None
        _,threshold,accuracy,fpr=best
        digest=_digest({
            "verifier_id":self.verifier_id,
            "samples":[[float(score),bool(label)] for score,label in samples],
            "threshold":threshold,
        })
        return VerifierCalibration(
            threshold=threshold,
            accuracy=accuracy,
            false_positive_rate=fpr,
            sample_count=len(samples),
            calibration_digest=digest,
        )

    @staticmethod
    def verify(score: float, calibration: VerifierCalibration) -> bool:
        return float(score)>=calibration.threshold
