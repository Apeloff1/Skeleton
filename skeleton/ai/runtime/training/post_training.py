"""Bounded post-training, deterministic RL environments and curriculum control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any, Mapping, Sequence


def _canonical(value: object) -> str:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_digest(value:str,*,field:str)->str:
    text=str(value).strip().lower()
    if len(text)!=64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be lowercase sha256")
    return text


def _utc(value:datetime|None=None)->str:
    instant=value or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return instant.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class PostTrainingExperiment:
    experiment_id: str
    base_candidate_digest: str
    dataset_digest: str
    objective: str
    algorithm: str
    configuration: Mapping[str,Any]
    evaluation_suite_digest: str

    def __post_init__(self)->None:
        if not self.experiment_id.strip() or not self.objective.strip() or not self.algorithm.strip():
            raise ValueError("post-training experiment identity must be non-empty")
        for name in ("base_candidate_digest","dataset_digest","evaluation_suite_digest"):
            object.__setattr__(self,name,_require_digest(getattr(self,name),field=name))
        config=dict(self.configuration); _canonical(config); object.__setattr__(self,"configuration",config)

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {
            "experiment_id":self.experiment_id,
            "base_candidate_digest":self.base_candidate_digest,
            "dataset_digest":self.dataset_digest,
            "objective":self.objective,
            "algorithm":self.algorithm,
            "configuration":dict(self.configuration),
            "evaluation_suite_digest":self.evaluation_suite_digest,
            "production_authority":False,
        }


@dataclass(frozen=True, slots=True)
class RLEnvironmentSpec:
    environment_id: str
    version: str
    state_schema_digest: str
    action_schema_digest: str
    reward_logic_digest: str
    sandboxed: bool = True
    external_side_effects_allowed: bool = False

    def __post_init__(self)->None:
        if not self.environment_id.strip() or not self.version.strip():
            raise ValueError("environment identity must be non-empty")
        for name in ("state_schema_digest","action_schema_digest","reward_logic_digest"):
            object.__setattr__(self,name,_require_digest(getattr(self,name),field=name))
        if self.sandboxed is not True:
            raise ValueError("P3 post-training environments must be sandboxed")
        if self.external_side_effects_allowed is not False:
            raise ValueError("P3 post-training environments may not execute external side effects")

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {
            "environment_id":self.environment_id,
            "version":self.version,
            "state_schema_digest":self.state_schema_digest,
            "action_schema_digest":self.action_schema_digest,
            "reward_logic_digest":self.reward_logic_digest,
            "sandboxed":self.sandboxed,
            "external_side_effects_allowed":self.external_side_effects_allowed,
        }


@dataclass(frozen=True, slots=True)
class RLStepReceipt:
    environment_digest: str
    episode_id: str
    step: int
    action: str
    reward: float
    terminal: bool
    state_digest: str
    next_state_digest: str

    def __post_init__(self)->None:
        for name in ("environment_digest","state_digest","next_state_digest"):
            object.__setattr__(self,name,_require_digest(getattr(self,name),field=name))
        if (
            not isinstance(self.episode_id,str)
            or not self.episode_id.strip()
            or not isinstance(self.action,str)
            or not self.action.strip()
        ):
            raise ValueError("RL receipt identity must be non-empty")
        if isinstance(self.step,bool) or not isinstance(self.step,int) or self.step<1:
            raise ValueError("RL step must be a positive integer")
        if (
            isinstance(self.reward,bool)
            or not isinstance(self.reward,(int,float))
            or not math.isfinite(float(self.reward))
        ):
            raise ValueError("RL reward must be a finite number")
        if not isinstance(self.terminal,bool):
            raise ValueError("RL terminal flag must be boolean")

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {
            "environment_digest":self.environment_digest,
            "episode_id":self.episode_id,
            "step":self.step,
            "action":self.action,
            "reward":float(self.reward),
            "terminal":self.terminal,
            "state_digest":self.state_digest,
            "next_state_digest":self.next_state_digest,
        }


class DeterministicRLEnvironment:
    """Small deterministic environment used to prove the bounded RL contract."""

    def __init__(
        self,
        spec:RLEnvironmentSpec,
        *,
        rewards:Mapping[str,float],
        terminal_actions:Sequence[str]=(),
    )->None:
        self.spec=spec
        if not isinstance(spec,RLEnvironmentSpec):
            raise TypeError("spec must be RLEnvironmentSpec")
        if not rewards:
            raise ValueError("rewards must be finite and non-empty")
        normalized_rewards:dict[str,float]={}
        for raw_action,raw_reward in rewards.items():
            action=str(raw_action).strip()
            if not action:
                raise ValueError("reward action ids must be non-empty")
            if (
                isinstance(raw_reward,bool)
                or not isinstance(raw_reward,(int,float))
                or not math.isfinite(float(raw_reward))
            ):
                raise ValueError("rewards must be finite numeric values")
            if action in normalized_rewards:
                raise ValueError("reward action ids must remain unique after normalization")
            normalized_rewards[action]=float(raw_reward)
        self.rewards=normalized_rewards
        self.terminal_actions=frozenset(
            str(item).strip() for item in terminal_actions if str(item).strip()
        )
        if not self.terminal_actions<=set(self.rewards):
            raise ValueError("terminal actions must exist in reward table")
        self._episode_id=""
        self._step=0
        self._state=""
        self._terminal=False

    def reset(self,*,episode_id:str,seed:int)->str:
        if not episode_id.strip() or isinstance(seed,bool) or not isinstance(seed,int):
            raise ValueError("episode identity/seed invalid")
        self._episode_id=episode_id
        self._step=0
        self._terminal=False
        self._state=_digest({"environment":self.spec.digest,"episode":episode_id,"seed":seed,"step":0})
        return self._state

    def step(self,action:str)->RLStepReceipt:
        if not self._episode_id:
            raise RuntimeError("environment must be reset before step")
        if self._terminal:
            raise RuntimeError("episode is terminal; reset required before another step")
        if action not in self.rewards:
            raise ValueError("action outside declared action space")
        previous=self._state
        self._step+=1
        next_state=_digest({
            "environment":self.spec.digest,
            "episode":self._episode_id,
            "previous":previous,
            "action":action,
            "step":self._step,
        })
        receipt=RLStepReceipt(
            environment_digest=self.spec.digest,
            episode_id=self._episode_id,
            step=self._step,
            action=action,
            reward=self.rewards[action],
            terminal=action in self.terminal_actions,
            state_digest=previous,
            next_state_digest=next_state,
        )
        self._state=next_state
        self._terminal=receipt.terminal
        return receipt


@dataclass(frozen=True, slots=True)
class CurriculumStage:
    stage_id: str
    competency: str
    metric: str
    minimum: float
    prerequisites: tuple[str,...]=()

    def __post_init__(self)->None:
        if not self.stage_id.strip() or not self.competency.strip() or not self.metric.strip():
            raise ValueError("curriculum stage fields must be non-empty")
        if not math.isfinite(float(self.minimum)):
            raise ValueError("curriculum minimum must be finite")
        prereqs=tuple(dict.fromkeys(item.strip() for item in self.prerequisites if item.strip()))
        if self.stage_id in prereqs:
            raise ValueError("curriculum stage cannot depend on itself")
        object.__setattr__(self,"prerequisites",prereqs)

    def as_dict(self)->dict[str,object]:
        return {
            "stage_id":self.stage_id,
            "competency":self.competency,
            "metric":self.metric,
            "minimum":float(self.minimum),
            "prerequisites":list(self.prerequisites),
        }


@dataclass(frozen=True, slots=True)
class CurriculumDecision:
    stage_id: str
    status: str
    metric_value: float | None
    reason: str
    completed_before: tuple[str,...]

    def __post_init__(self)->None:
        if not isinstance(self.stage_id,str) or not self.stage_id.strip():
            raise ValueError("curriculum decision stage_id must be non-empty")
        if self.status not in {"advance","hold","blocked","already_complete"}:
            raise ValueError("unsupported curriculum decision")
        if not isinstance(self.reason,str) or not self.reason.strip():
            raise ValueError("curriculum decision reason must be non-empty")
        if self.metric_value is not None:
            if (
                isinstance(self.metric_value,bool)
                or not isinstance(self.metric_value,(int,float))
                or not math.isfinite(float(self.metric_value))
            ):
                raise ValueError("curriculum metric_value must be finite or null")
            object.__setattr__(self,"metric_value",float(self.metric_value))
        completed=tuple(self.completed_before)
        if (
            any(not isinstance(item,str) or not item.strip() for item in completed)
            or len(completed)!=len(set(completed))
        ):
            raise ValueError("completed_before must contain unique non-empty stage ids")
        if self.status=="advance" and self.metric_value is None:
            raise ValueError("advance decision requires metric evidence")
        if self.status in {"blocked","already_complete"} and self.metric_value is not None:
            raise ValueError(f"{self.status} decision cannot carry metric evidence")
        object.__setattr__(self,"completed_before",completed)

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {
            "stage_id":self.stage_id,
            "status":self.status,
            "metric_value":self.metric_value,
            "reason":self.reason,
            "completed_before":list(self.completed_before),
        }


class CurriculumEngine:
    def __init__(self,stages:Sequence[CurriculumStage])->None:
        self.stages={stage.stage_id:stage for stage in stages}
        if not self.stages or len(self.stages)!=len(tuple(stages)):
            raise ValueError("curriculum stages must be unique and non-empty")
        for stage in self.stages.values():
            missing=set(stage.prerequisites)-set(self.stages)
            if missing:
                raise ValueError(f"unknown curriculum prerequisites: {sorted(missing)}")
        visiting=set();visited=set()
        def visit(stage_id:str)->None:
            if stage_id in visited:return
            if stage_id in visiting:raise ValueError("curriculum dependency cycle")
            visiting.add(stage_id)
            for dep in self.stages[stage_id].prerequisites:visit(dep)
            visiting.remove(stage_id);visited.add(stage_id)
        for stage_id in self.stages:visit(stage_id)

    def decide(
        self,
        stage_id:str,
        *,
        metrics:Mapping[str,float],
        completed:Sequence[str],
    )->CurriculumDecision:
        if stage_id not in self.stages:raise KeyError(stage_id)
        stage=self.stages[stage_id]
        complete=tuple(dict.fromkeys(completed))
        if stage_id in complete:
            return CurriculumDecision(stage_id,"already_complete",None,"stage already completed",complete)
        missing=[dep for dep in stage.prerequisites if dep not in complete]
        if missing:
            return CurriculumDecision(stage_id,"blocked",None,"missing prerequisites: "+",".join(missing),complete)
        if stage.metric not in metrics:
            return CurriculumDecision(stage_id,"hold",None,"required metric missing",complete)
        value=float(metrics[stage.metric])
        if not math.isfinite(value):
            return CurriculumDecision(stage_id,"hold",None,"required metric is non-finite",complete)
        if value<stage.minimum:
            return CurriculumDecision(stage_id,"hold",value,"competency threshold not met",complete)
        return CurriculumDecision(stage_id,"advance",value,"competency threshold met",complete)


class PostTrainingLedger:
    """Immutable experiment/environment/curriculum evidence ledger."""

    def __init__(self,path:str|Path=":memory:")->None:
        self._lock=threading.RLock()
        self._db=sqlite3.connect(str(path),check_same_thread=False)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS experiment (
                experiment_id TEXT PRIMARY KEY,
                experiment_digest TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS environment (
                environment_key TEXT PRIMARY KEY,
                environment_digest TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rl_step (
                receipt_digest TEXT PRIMARY KEY,
                environment_digest TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS curriculum_decision (
                decision_digest TEXT PRIMARY KEY,
                stage_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    def register_experiment(self,experiment:PostTrainingExperiment)->str:
        encoded=_canonical(experiment.as_dict())
        with self._lock:
            row=self._db.execute("SELECT experiment_digest,payload FROM experiment WHERE experiment_id=?",(experiment.experiment_id,)).fetchone()
            if row is not None:
                if row[0]!=experiment.digest or row[1]!=encoded:raise ValueError("post-training experiment id is immutable")
                return experiment.digest
            self._db.execute("INSERT INTO experiment(experiment_id,experiment_digest,payload) VALUES (?,?,?)",(experiment.experiment_id,experiment.digest,encoded))
            self._db.commit()
        return experiment.digest

    def register_environment(self,spec:RLEnvironmentSpec)->str:
        key=f"{spec.environment_id}@{spec.version}";encoded=_canonical(spec.as_dict())
        with self._lock:
            row=self._db.execute("SELECT environment_digest,payload FROM environment WHERE environment_key=?",(key,)).fetchone()
            if row is not None:
                if row[0]!=spec.digest or row[1]!=encoded:raise ValueError("RL environment version is immutable")
                return spec.digest
            self._db.execute("INSERT INTO environment(environment_key,environment_digest,payload) VALUES (?,?,?)",(key,spec.digest,encoded));self._db.commit()
        return spec.digest

    def record_step(self,receipt:RLStepReceipt)->str:
        encoded=_canonical(receipt.as_dict())
        with self._lock:
            known=self._db.execute(
                "SELECT environment_key,payload FROM environment "
                "WHERE environment_digest=?",
                (receipt.environment_digest,),
            ).fetchone()
            if known is None:
                raise ValueError("RL environment is not registered")
            try:
                environment_payload=json.loads(known[1])
            except json.JSONDecodeError as exc:
                raise ValueError("stored RL environment payload is corrupted") from exc
            expected_key=(
                f"{environment_payload.get('environment_id','')}@"
                f"{environment_payload.get('version','')}"
            )
            if (
                known[0]!=expected_key
                or _digest(environment_payload)!=receipt.environment_digest
            ):
                raise ValueError("stored RL environment identity mismatch")

            prior_exact=self._db.execute(
                "SELECT payload FROM rl_step WHERE receipt_digest=?",
                (receipt.digest,),
            ).fetchone()
            if prior_exact is not None:
                if prior_exact[0]!=encoded:
                    raise ValueError("RL receipt digest collision")
                return receipt.digest

            rows=self._db.execute(
                "SELECT receipt_digest,payload FROM rl_step "
                "WHERE environment_digest=?",
                (receipt.environment_digest,),
            ).fetchall()
            episode=[]
            for stored_digest,stored_payload in rows:
                try:
                    payload=json.loads(stored_payload)
                except json.JSONDecodeError as exc:
                    raise ValueError("stored RL receipt payload is corrupted") from exc
                if _digest(payload)!=stored_digest:
                    raise ValueError("stored RL receipt digest mismatch")
                if payload.get("environment_digest")!=receipt.environment_digest:
                    raise ValueError("stored RL receipt environment identity mismatch")
                if payload.get("episode_id")==receipt.episode_id:
                    episode.append(payload)
            if not episode:
                if receipt.step!=1:
                    raise ValueError("RL episode must begin at step 1")
            else:
                latest=max(episode,key=lambda item:int(item["step"]))
                if latest.get("terminal") is True:
                    raise ValueError("RL episode is already terminal")
                expected_step=int(latest["step"])+1
                if receipt.step!=expected_step:
                    raise ValueError(
                        f"RL step must be contiguous: expected {expected_step}"
                    )
                if receipt.state_digest!=latest.get("next_state_digest"):
                    raise ValueError("RL state chain does not extend latest receipt")

            self._db.execute(
                "INSERT INTO rl_step(receipt_digest,environment_digest,payload) "
                "VALUES (?,?,?)",
                (receipt.digest,receipt.environment_digest,encoded),
            )
            self._db.commit()
        return receipt.digest

    def record_curriculum(self,decision:CurriculumDecision)->str:
        encoded=_canonical(decision.as_dict())
        with self._lock:
            prior=self._db.execute(
                "SELECT stage_id,payload FROM curriculum_decision "
                "WHERE decision_digest=?",
                (decision.digest,),
            ).fetchone()
            if prior is not None:
                if prior[0]!=decision.stage_id or prior[1]!=encoded:
                    raise ValueError("curriculum decision digest collision")
                return decision.digest
            self._db.execute(
                "INSERT INTO curriculum_decision("
                "decision_digest,stage_id,payload"
                ") VALUES (?,?,?)",
                (decision.digest,decision.stage_id,encoded),
            )
            self._db.commit()
        return decision.digest
