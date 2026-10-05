"""Durable native training control, checkpointing and elastic recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any, Mapping, Sequence

from .data import DatasetRegistry


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_digest(value: str, *, field: str) -> str:
    text=str(value).strip().lower()
    if len(text)!=64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be lowercase sha256")
    return text


def _utc(value: datetime | None = None) -> str:
    instant=value or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return instant.astimezone(timezone.utc).isoformat()


def _require_utc_timestamp(value: str, *, field: str) -> str:
    text=str(value).strip()
    try:
        instant=datetime.fromisoformat(text.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return instant.astimezone(timezone.utc).isoformat()


_ALLOWED_RUN_STATES={"registered","running","failed","recovering","completed"}


@dataclass(frozen=True, slots=True)
class TrainingRunManifest:
    run_id: str
    dataset_digest: str
    base_model_digest: str
    code_digest: str
    environment_digest: str
    hyperparameters: Mapping[str, Any]
    seed: int
    world_size: int = 1
    parallelism: str = "single"
    collective_timeout_seconds: float = 60.0
    resource_budget: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must be non-empty")
        for name in ("dataset_digest","base_model_digest","code_digest","environment_digest"):
            object.__setattr__(self,name,_require_digest(getattr(self,name),field=name))
        if isinstance(self.seed,bool) or not isinstance(self.seed,int):
            raise ValueError("seed must be an integer")
        if isinstance(self.world_size,bool) or not isinstance(self.world_size,int) or not 1<=self.world_size<=65536:
            raise ValueError("world_size must be in [1, 65536]")
        if self.parallelism not in {"single","data_parallel","model_parallel","hybrid"}:
            raise ValueError("unsupported parallelism")
        if (
            isinstance(self.collective_timeout_seconds,bool)
            or not isinstance(self.collective_timeout_seconds,(int,float))
            or not math.isfinite(float(self.collective_timeout_seconds))
            or self.collective_timeout_seconds<=0
        ):
            raise ValueError("collective_timeout_seconds must be a positive finite number")
        hyper=dict(self.hyperparameters)
        _canonical(hyper)
        object.__setattr__(self,"hyperparameters",hyper)
        if any(
            isinstance(v,bool) or not isinstance(v,(int,float))
            for v in self.resource_budget.values()
        ):
            raise ValueError("resource_budget values must be numeric, not boolean")
        budget={str(k):float(v) for k,v in self.resource_budget.items()}
        if any(not math.isfinite(v) or v<0 for v in budget.values()):
            raise ValueError("resource_budget values must be finite and non-negative")
        object.__setattr__(self,"resource_budget",budget)

    @property
    def digest(self) -> str:
        return _digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload={
            "run_id":self.run_id,
            "dataset_digest":self.dataset_digest,
            "base_model_digest":self.base_model_digest,
            "code_digest":self.code_digest,
            "environment_digest":self.environment_digest,
            "hyperparameters":dict(self.hyperparameters),
            "seed":self.seed,
            "world_size":self.world_size,
            "parallelism":self.parallelism,
            "collective_timeout_seconds":float(self.collective_timeout_seconds),
            "resource_budget":dict(sorted(self.resource_budget.items())),
        }
        if include_digest:
            payload["manifest_digest"]=self.digest
        return payload

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"TrainingRunManifest":
        manifest=cls(
            run_id=str(payload["run_id"]),
            dataset_digest=str(payload["dataset_digest"]),
            base_model_digest=str(payload["base_model_digest"]),
            code_digest=str(payload["code_digest"]),
            environment_digest=str(payload["environment_digest"]),
            hyperparameters=dict(payload.get("hyperparameters",{})),
            seed=payload["seed"],
            world_size=payload.get("world_size",1),
            parallelism=str(payload.get("parallelism","single")),
            collective_timeout_seconds=payload.get("collective_timeout_seconds",60.0),
            resource_budget=dict(payload.get("resource_budget",{})),
        )
        claimed=payload.get("manifest_digest")
        if claimed is not None and str(claimed)!=manifest.digest:
            raise ValueError("training manifest digest mismatch")
        return manifest


@dataclass(frozen=True, slots=True)
class WorkerLease:
    run_id: str
    worker_id: str
    epoch: int
    issued_at: str

    def __post_init__(self)->None:
        if not self.run_id.strip() or not self.worker_id.strip():
            raise ValueError("worker lease ids must be non-empty")
        if isinstance(self.epoch,bool) or not isinstance(self.epoch,int) or self.epoch<0:
            raise ValueError("worker epoch must be non-negative")
        object.__setattr__(
            self,
            "issued_at",
            _require_utc_timestamp(self.issued_at,field="issued_at"),
        )

    @property
    def token(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {"run_id":self.run_id,"worker_id":self.worker_id,"epoch":self.epoch,"issued_at":self.issued_at}


@dataclass(frozen=True, slots=True)
class TrainingCheckpoint:
    run_id: str
    manifest_digest: str
    step: int
    model_digest: str
    optimizer_digest: str
    rng_digest: str
    data_cursor_digest: str
    worker_epoch: int
    created_at: str

    def __post_init__(self)->None:
        if not self.run_id.strip():
            raise ValueError("checkpoint run_id must be non-empty")
        for name in ("manifest_digest","model_digest","optimizer_digest","rng_digest","data_cursor_digest"):
            object.__setattr__(self,name,_require_digest(getattr(self,name),field=name))
        if isinstance(self.step,bool) or not isinstance(self.step,int) or self.step<0:
            raise ValueError("checkpoint step must be non-negative")
        if isinstance(self.worker_epoch,bool) or not isinstance(self.worker_epoch,int) or self.worker_epoch<0:
            raise ValueError("worker_epoch must be non-negative")
        object.__setattr__(
            self,
            "created_at",
            _require_utc_timestamp(self.created_at,field="created_at"),
        )

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {
            "run_id":self.run_id,
            "manifest_digest":self.manifest_digest,
            "step":self.step,
            "model_digest":self.model_digest,
            "optimizer_digest":self.optimizer_digest,
            "rng_digest":self.rng_digest,
            "data_cursor_digest":self.data_cursor_digest,
            "worker_epoch":self.worker_epoch,
            "created_at":self.created_at,
        }

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"TrainingCheckpoint":
        return cls(
            run_id=str(payload["run_id"]),
            manifest_digest=str(payload["manifest_digest"]),
            step=payload["step"],
            model_digest=str(payload["model_digest"]),
            optimizer_digest=str(payload["optimizer_digest"]),
            rng_digest=str(payload["rng_digest"]),
            data_cursor_digest=str(payload["data_cursor_digest"]),
            worker_epoch=payload["worker_epoch"],
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class TrainingTelemetry:
    run_id: str
    step: int
    metrics: Mapping[str,float]
    emitted_at: str

    def __post_init__(self)->None:
        if not self.run_id.strip():
            raise ValueError("telemetry run_id must be non-empty")
        if isinstance(self.step,bool) or not isinstance(self.step,int) or self.step<0:
            raise ValueError("telemetry step must be non-negative")
        values={str(k):float(v) for k,v in self.metrics.items()}
        if not values:
            raise ValueError("telemetry metrics must be non-empty")
        if any(not math.isfinite(v) for v in values.values()):
            raise ValueError("telemetry rejects non-finite values")
        object.__setattr__(
            self,
            "emitted_at",
            _require_utc_timestamp(self.emitted_at,field="emitted_at"),
        )
        object.__setattr__(self,"metrics",values)

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {"run_id":self.run_id,"step":self.step,"metrics":dict(sorted(self.metrics.items())),"emitted_at":self.emitted_at}


class TrainingStateError(RuntimeError):
    pass


class TrainingRepository:
    """SQLite authority for manifests, worker fences, checkpoints and telemetry."""

    def __init__(self,path:str|Path=":memory:")->None:
        self.path=str(path)
        self._lock=threading.RLock()
        self._db=sqlite3.connect(self.path,check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS training_run (
                run_id TEXT PRIMARY KEY,
                manifest_digest TEXT NOT NULL UNIQUE,
                manifest_json TEXT NOT NULL,
                state TEXT NOT NULL,
                worker_epoch INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS worker_lease (
                run_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                lease_json TEXT NOT NULL,
                PRIMARY KEY(run_id, worker_id),
                FOREIGN KEY(run_id) REFERENCES training_run(run_id)
            );
            CREATE TABLE IF NOT EXISTS training_checkpoint (
                checkpoint_digest TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step INTEGER NOT NULL,
                checkpoint_json TEXT NOT NULL,
                UNIQUE(run_id, step),
                FOREIGN KEY(run_id) REFERENCES training_run(run_id)
            );
            CREATE TABLE IF NOT EXISTS training_telemetry (
                telemetry_digest TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step INTEGER NOT NULL,
                telemetry_json TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES training_run(run_id)
            );
            """
        )
        self._db.commit()

    def register_run(self,manifest:TrainingRunManifest,datasets:DatasetRegistry,*,created_at:datetime|None=None)->str:
        if not isinstance(manifest,TrainingRunManifest):
            raise TypeError("manifest must be TrainingRunManifest")
        datasets.require_training_ready(manifest.dataset_digest)
        encoded=_canonical(manifest.as_dict())
        with self._lock:
            row=self._db.execute("SELECT manifest_digest,manifest_json FROM training_run WHERE run_id=?",(manifest.run_id,)).fetchone()
            if row is not None:
                if row[0]!=manifest.digest or row[1]!=encoded:
                    raise TrainingStateError("run_id is already bound to a different immutable manifest")
                return manifest.digest
            self._db.execute(
                "INSERT INTO training_run(run_id,manifest_digest,manifest_json,state,worker_epoch,created_at) VALUES (?,?,?,?,?,?)",
                (manifest.run_id,manifest.digest,encoded,"registered",0,_utc(created_at)),
            )
            self._db.commit()
        return manifest.digest

    def manifest(self,run_id:str)->TrainingRunManifest:
        row=self._db.execute(
            "SELECT manifest_digest,manifest_json FROM training_run WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        manifest=TrainingRunManifest.from_dict(json.loads(row[1]))
        if manifest.run_id!=run_id or manifest.digest!=str(row[0]):
            raise TrainingStateError("stored training manifest identity mismatch")
        return manifest

    def state(self,run_id:str)->str:
        row=self._db.execute("SELECT state FROM training_run WHERE run_id=?",(run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        state=str(row[0])
        if state not in _ALLOWED_RUN_STATES:
            raise TrainingStateError("stored training run state is invalid")
        return state

    def _epoch(self,run_id:str)->int:
        row=self._db.execute("SELECT worker_epoch FROM training_run WHERE run_id=?",(run_id,)).fetchone()
        if row is None: raise KeyError(run_id)
        return int(row[0])

    def start(self,run_id:str)->None:
        with self._lock:
            state=self.state(run_id)
            if state not in {"registered","recovering"}:
                raise TrainingStateError(f"cannot start run from {state}")
            self._db.execute("UPDATE training_run SET state='running' WHERE run_id=?",(run_id,))
            self._db.commit()

    def lease_worker(self,run_id:str,worker_id:str,*,issued_at:datetime|None=None)->WorkerLease:
        if self.state(run_id)!="running":
            raise TrainingStateError("worker lease requires running state")
        lease=WorkerLease(run_id=run_id,worker_id=worker_id,epoch=self._epoch(run_id),issued_at=_utc(issued_at))
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO worker_lease(run_id,worker_id,epoch,lease_json) VALUES (?,?,?,?)",
                (run_id,worker_id,lease.epoch,_canonical(lease.as_dict())),
            )
            self._db.commit()
        return lease

    def assert_worker_current(self,lease:WorkerLease)->None:
        if self.state(lease.run_id)!="running":
            raise TrainingStateError("run is not running")
        current=self._epoch(lease.run_id)
        if lease.epoch!=current:
            raise TrainingStateError("stale worker epoch rejected")
        row=self._db.execute(
            "SELECT epoch,lease_json FROM worker_lease "
            "WHERE run_id=? AND worker_id=?",
            (lease.run_id,lease.worker_id),
        ).fetchone()
        if (
            row is None
            or int(row[0])!=lease.epoch
            or row[1]!=_canonical(lease.as_dict())
        ):
            raise TrainingStateError("worker lease is not current")

    def checkpoint(self,checkpoint:TrainingCheckpoint,lease:WorkerLease)->str:
        if checkpoint.run_id!=lease.run_id:
            raise TrainingStateError("checkpoint/lease run mismatch")
        self.assert_worker_current(lease)
        manifest=self.manifest(checkpoint.run_id)
        if checkpoint.manifest_digest!=manifest.digest:
            raise TrainingStateError("checkpoint manifest identity drift")
        if checkpoint.worker_epoch!=lease.epoch:
            raise TrainingStateError("checkpoint worker epoch drift")
        with self._lock:
            row=self._db.execute(
                "SELECT MAX(step) FROM training_checkpoint WHERE run_id=?",
                (checkpoint.run_id,),
            ).fetchone()
            latest=-1 if row is None or row[0] is None else int(row[0])
            if checkpoint.step<=latest:
                raise TrainingStateError("checkpoint step must be strictly monotonic")
            self._db.execute(
                "INSERT INTO training_checkpoint(checkpoint_digest,run_id,step,checkpoint_json) VALUES (?,?,?,?)",
                (checkpoint.digest,checkpoint.run_id,checkpoint.step,_canonical(checkpoint.as_dict())),
            )
            self._db.commit()
        return checkpoint.digest

    def latest_checkpoint(self,run_id:str)->TrainingCheckpoint|None:
        row=self._db.execute(
            "SELECT checkpoint_digest,run_id,step,checkpoint_json "
            "FROM training_checkpoint WHERE run_id=? ORDER BY step DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        checkpoint=TrainingCheckpoint.from_dict(json.loads(row[3]))
        if (
            checkpoint.digest!=str(row[0])
            or checkpoint.run_id!=str(row[1])
            or checkpoint.step!=int(row[2])
            or checkpoint.run_id!=run_id
        ):
            raise TrainingStateError("stored checkpoint identity mismatch")
        return checkpoint

    def record_telemetry(self,event:TrainingTelemetry)->str:
        if self.state(event.run_id)!="running":
            raise TrainingStateError("telemetry requires running state")
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO training_telemetry(telemetry_digest,run_id,step,telemetry_json) VALUES (?,?,?,?)",
                (event.digest,event.run_id,event.step,_canonical(event.as_dict())),
            )
            self._db.commit()
        return event.digest

    def recover(self,run_id:str)->TrainingCheckpoint:
        with self._lock:
            state=self.state(run_id)
            if state not in {"running","failed","recovering"}:
                raise TrainingStateError(f"cannot recover run from {state}")
            checkpoint=self.latest_checkpoint(run_id)
            if checkpoint is None:
                raise TrainingStateError("run has no durable checkpoint")
            next_epoch=self._epoch(run_id)+1
            self._db.execute(
                "UPDATE training_run SET state='recovering',worker_epoch=? WHERE run_id=?",
                (next_epoch,run_id),
            )
            self._db.execute("DELETE FROM worker_lease WHERE run_id=?",(run_id,))
            self._db.commit()
        return checkpoint

    def fail(self,run_id:str)->None:
        with self._lock:
            if self.state(run_id)!="running":
                raise TrainingStateError("only running runs may fail")
            self._db.execute("UPDATE training_run SET state='failed' WHERE run_id=?",(run_id,))
            self._db.commit()

    def complete(self,run_id:str)->TrainingCheckpoint:
        with self._lock:
            if self.state(run_id)!="running":
                raise TrainingStateError("only running runs may complete")
            checkpoint=self.latest_checkpoint(run_id)
            if checkpoint is None:
                raise TrainingStateError("completion requires a durable checkpoint")
            self._db.execute("UPDATE training_run SET state='completed' WHERE run_id=?",(run_id,))
            self._db.commit()
        return checkpoint

    def close(self)->None:
        self._db.close()
