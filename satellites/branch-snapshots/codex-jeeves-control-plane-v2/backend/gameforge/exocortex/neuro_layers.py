from __future__ import annotations
"""
Missing neuro layers:
  RAS, Cerebellum, ACC, Nucleus Accumbens,
  Load Governor, Semantic Memory, Forgetting, Feed-Forward, Sovereignty.
"""

import hashlib
import math
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import json
import os


# ----- 1. RAS — Attention filter --------------------------------------------

class ReticularActivatingSystem:
    """Drops ambient noise; passes high-priority anchors only."""

    ANCHORS = [
        r"\bproblem\b", r"\bmilestone\b", r"\binsight\b", r"\bdeadline\b",
        r"\bpain\b", r"\bcourt\b", r"\bremember\b", r"\bjeeves\b",
        r"\bschedule\b", r"\bship\b", r"\bdanger\b", r"\bhelp\b",
    ]

    def __init__(self, base_threshold: float = 0.4):
        self.base_threshold = base_threshold
        self.threshold = base_threshold
        self.logs: List[dict] = []

    def raise_threshold(self, delta: float = 0.15):
        self.threshold = min(0.95, self.threshold + delta)

    def reset_threshold(self):
        self.threshold = self.base_threshold

    def filter(self, text: str, salience_score: float = 0.0) -> Dict[str, Any]:
        t = text or ""
        hits = [p for p in self.ANCHORS if re.search(p, t, re.I)]
        score = salience_score
        if hits:
            score = max(score, 0.5 + 0.1 * len(hits))
        if len(t.strip()) < 4:
            score = 0.0
        passed = score >= self.threshold
        ev = {
            "passed": passed,
            "score": round(score, 3),
            "threshold": self.threshold,
            "anchors": hits,
            "action": "pass_to_conscious" if passed else "dump_ambient",
        }
        self.logs.append({"ts": datetime.utcnow().isoformat(), **ev})
        return ev


# ----- 2. Cerebellum — procedural automation --------------------------------

class CerebellumAutomator:
    """Background procedural runs: drop problem → shard → mine → log."""

    def __init__(self, math_hub=None):
        self.math_hub = math_hub
        self.queue: List[Dict[str, Any]] = []
        self.logs: List[dict] = []
        self.auto = True

    def enqueue_pow_sum(self, numbers: List[float], chunk_size: int = 8):
        job = {
            "job_id": str(uuid.uuid4())[:10],
            "type": "pow_sum",
            "numbers": numbers,
            "chunk_size": chunk_size,
            "status": "queued",
        }
        self.queue.append(job)
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "enqueue", **job})
        if self.auto:
            return self.run_next()
        return job

    def run_next(self) -> Dict[str, Any]:
        pending = [j for j in self.queue if j["status"] == "queued"]
        if not pending:
            return {"ok": False, "error": "empty"}
        job = pending[0]
        job["status"] = "running"
        t0 = time.perf_counter()
        try:
            if not self.math_hub:
                raise RuntimeError("math_hub not bound")
            result = self.math_hub.pow_sum(job["numbers"], job["chunk_size"])
            job["status"] = "done"
            job["result"] = result
            job["ms"] = (time.perf_counter() - t0) * 1000
            self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "auto_complete", "job_id": job["job_id"], "ok": result.get("ok")})
            return {"ok": True, "job": job}
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)
            self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "auto_fail", "error": str(e)})
            return {"ok": False, "error": str(e), "job": job}


# ----- 3. ACC — variance / conflict monitor ---------------------------------

class AnteriorCingulateMonitor:
    """Alarm when actual progress diverges from scheduled expectation."""

    def __init__(self, variance_threshold: float = 0.25):
        self.variance_threshold = variance_threshold
        self.alarms: List[dict] = []
        self.logs: List[dict] = []

    def check(self, scheduled_pct: float, actual_pct: float, project_id: str = "") -> Dict[str, Any]:
        # expected progress fraction vs actual
        if scheduled_pct <= 0:
            delta = 0.0
        else:
            delta = (scheduled_pct - actual_pct) / max(scheduled_pct, 1.0)
        fired = delta >= self.variance_threshold
        ev = {
            "fired": fired,
            "project_id": project_id,
            "scheduled_pct": scheduled_pct,
            "actual_pct": actual_pct,
            "delta": round(delta, 3),
            "threshold": self.variance_threshold,
            "actions": [],
        }
        if fired:
            ev["actions"] = [
                "override_schedule_soft",
                "force_cognitive_bias_log",
                "alert_jeeves_debug_roadblock",
            ]
            self.alarms.append(ev)
        self.logs.append({"ts": datetime.utcnow().isoformat(), **ev})
        return ev


# ----- 4. Nucleus Accumbens — token economy ----------------------------------

class NucleusAccumbensTokens:
    """Mints cognitive tokens for hard work under adverse conditions."""

    def __init__(self):
        self.balance: float = 0.0
        self.ledger: List[dict] = []

    def mint(
        self,
        amount: float,
        reason: str,
        *,
        adverse: bool = False,
        weather: str = "",
        noise_db: float = 0.0,
    ) -> Dict[str, Any]:
        bonus = 0.0
        if adverse:
            bonus += amount * 0.25
        if weather in ("rain", "storm", "heat"):
            bonus += amount * 0.15
        if noise_db >= 55:
            bonus += amount * 0.1
        total = amount + bonus
        self.balance += total
        row = {
            "ts": datetime.utcnow().isoformat(),
            "mint": total,
            "base": amount,
            "bonus": bonus,
            "reason": reason,
            "balance": self.balance,
        }
        self.ledger.append(row)
        return row

    def status(self) -> Dict[str, Any]:
        return {"balance": self.balance, "ledger_tail": self.ledger[-10:]}


# ----- 5. Adaptive Cognitive Load Governor ----------------------------------

class CognitiveLoadGovernor:
    """Conservation mode when energy low / noise high."""

    def __init__(self):
        self.mode = "normal"  # normal | conservation | deep_focus
        self.logs: List[dict] = []

    def evaluate(self, energy: float, noise_db: float, valence: float = 0.0) -> Dict[str, Any]:
        prev = self.mode
        if energy < 0.35 or noise_db >= 65 or valence < -0.3:
            self.mode = "conservation"
        elif energy > 0.7 and noise_db < 45 and valence >= 0:
            self.mode = "deep_focus"
        else:
            self.mode = "normal"
        ui = {
            "conservation": {
                "suppress_nonessential_reminders": True,
                "hide_long_grids": True,
                "jeeves_style": "ultra_short_sentences",
                "max_prompts": 1,
            },
            "deep_focus": {
                "suppress_nonessential_reminders": True,
                "hide_long_grids": False,
                "jeeves_style": "precise_extended",
                "max_prompts": 5,
            },
            "normal": {
                "suppress_nonessential_reminders": False,
                "hide_long_grids": False,
                "jeeves_style": "balanced",
                "max_prompts": 3,
            },
        }[self.mode]
        ev = {"mode": self.mode, "prev": prev, "policy": ui, "energy": energy, "noise_db": noise_db}
        self.logs.append({"ts": datetime.utcnow().isoformat(), **ev})
        return ev


# ----- 6. Semantic memory (lightweight vector mesh) -------------------------

def _embed(text: str, dim: int = 64) -> List[float]:
    """Deterministic bag-hash embedding (no external model required)."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    for tok in tokens:
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h // dim) % dim] += 0.5
    # L2 norm
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec]


def _cos(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class SemanticMemoryMesh:
    def __init__(self, user_id: str):
        self.user_id = user_id
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.path = base / "semantic_mesh" / user_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.store: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        f = self.path / "mesh.jsonl"
        if not f.exists():
            return
        with f.open() as fh:
            for line in fh:
                try:
                    self.store.append(json.loads(line))
                except Exception:
                    pass

    def add(self, text: str, meta: Optional[dict] = None) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4())[:12],
            "text": text,
            "vec": _embed(text),
            "meta": meta or {},
            "ts": datetime.utcnow().isoformat(),
        }
        self.store.append(row)
        with (self.path / "mesh.jsonl").open("a") as fh:
            fh.write(json.dumps({k: v for k, v in row.items()}) + "\n")
        return {"id": row["id"], "ok": True}

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        qv = _embed(query)
        scored = []
        for row in self.store:
            s = _cos(qv, row.get("vec") or _embed(row.get("text", "")))
            scored.append((s, row))
        scored.sort(key=lambda x: -x[0])
        return [
            {"score": round(s, 4), "id": r["id"], "text": r["text"][:300], "meta": r.get("meta")}
            for s, r in scored[:k]
        ]


# ----- 7. Forgetting / sensory decimator ------------------------------------

class ForgettingAlgorithm:
    """
    High-importance locked; low-importance compress after retention_days.
    """

    def __init__(self, retention_days: int = 30):
        self.retention_days = retention_days
        self.logs: List[dict] = []

    def classify_importance(self, text: str, tags: Optional[List[str]] = None) -> str:
        tags = tags or []
        t = (text or "").lower()
        if any(x in tags for x in ("milestone", "health", "catch", "era", "court")):
            return "lock"
        if re.search(r"\b(milestone|pain|court|insight|shipped)\b", t):
            return "lock"
        if re.search(r"\b(um+|yeah|noise|weather)\b", t) or len(t) < 20:
            return "ephemeral"
        return "normal"

    def prune(self, records: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or datetime.utcnow()
        kept, compressed, deleted = [], [], []
        for r in records:
            imp = r.get("importance") or self.classify_importance(r.get("text", ""), r.get("tags"))
            ts = r.get("ts") or r.get("created_at")
            try:
                age = (now - datetime.fromisoformat(ts.replace("Z", ""))).days
            except Exception:
                age = 0
            if imp == "lock":
                kept.append(r)
            elif age >= self.retention_days and imp == "ephemeral":
                deleted.append(r.get("id"))
            elif age >= self.retention_days and imp == "normal":
                compressed.append(
                    {
                        "id": r.get("id"),
                        "summary": (r.get("text") or "")[:120],
                        "compressed_from": "normal",
                        "ts": ts,
                    }
                )
            else:
                kept.append(r)
        ev = {
            "kept": len(kept),
            "compressed": len(compressed),
            "deleted": len(deleted),
            "retention_days": self.retention_days,
        }
        self.logs.append({"ts": now.isoformat(), **ev})
        return {"ok": True, **ev, "compressed_records": compressed, "deleted_ids": deleted}


# ----- 8. Feed-forward intervention -----------------------------------------

class FeedForwardLoop:
    """Act before failure using schedule + weather + historical plasticity signals."""

    def __init__(self):
        self.logs: List[dict] = []

    def project(
        self,
        *,
        upcoming_weather: List[str],
        planned_load: int,
        capacity: int,
        plasticity_risk: bool,
        energy: float,
    ) -> Dict[str, Any]:
        stress = sum(1 for w in upcoming_weather if w in ("rain", "storm", "heat"))
        overload = planned_load > capacity
        actions = []
        fire = False
        if overload and (stress >= 1 or energy < 0.45 or plasticity_risk):
            fire = True
            actions.append("preemptively_reschedule_lowest_priority_block")
            actions.append("insert_recovery_block")
        if stress >= 2 and planned_load >= capacity:
            fire = True
            actions.append("cut_math_chunking_load")
        msg = (
            "Feed-forward: adverse conditions + load → preemptive reschedule."
            if fire
            else "Feed-forward: path acceptable."
        )
        ev = {
            "active": fire,
            "message": msg,
            "actions": actions,
            "stress_days": stress,
            "planned_load": planned_load,
            "capacity": capacity,
        }
        self.logs.append({"ts": datetime.utcnow().isoformat(), **ev})
        return ev


# ----- 9. Sovereignty vault -------------------------------------------------

class SovereigntyVault:
    """
    Local-first policy: data paths under GAMEFORGE_DATA_DIR, encryption flag,
    no cloud upload in this layer. Ollama/local model endpoint optional.
    """

    def __init__(self):
        self.data_dir = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.local_llm = os.getenv("GAMEFORGE_LOCAL_LLM_URL", "")  # e.g. http://127.0.0.1:11434
        self.air_gap = os.getenv("GAMEFORGE_AIR_GAP", "1") == "1"
        self.logs: List[dict] = []

    def status(self) -> Dict[str, Any]:
        st = {
            "data_dir": str(self.data_dir),
            "air_gap": self.air_gap,
            "local_llm_url": self.local_llm or None,
            "cloud_upload": False if self.air_gap else "policy_undefined",
            "encryption_at_rest": os.getenv("GAMEFORGE_ENCRYPT", "1") == "1",
        }
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "status", **st})
        return st

    def assert_local_only(self) -> bool:
        return self.air_gap
