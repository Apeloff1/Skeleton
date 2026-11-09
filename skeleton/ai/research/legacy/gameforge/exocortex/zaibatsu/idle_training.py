from __future__ import annotations
"""
Idle coherent + synergistic + recursive training on room/twin logs.
SOTA Zaibatsu: trains only when idle; never blocks Emperor path.
"""

import json
import os
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TrainingLesson:
    lesson_id: str
    kind: str  # coherent | synergistic | recursive
    pattern: str
    action: str
    support: int
    rooms: List[str] = field(default_factory=list)
    weight: float = 1.0
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


class IdleTrainingEngine:
    """
    Coherent: patterns stable within a single room over time.
    Synergistic: patterns that co-occur across rooms.
    Recursive: lessons applied to prior lessons → refined rules.
    """

    def __init__(self, user_id: str, learning_engine=None):
        self.user_id = user_id
        self.learning = learning_engine  # SelfLearningEngine optional
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.path = base / "idle_training" / user_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.lessons: List[TrainingLesson] = []
        self.runs: List[dict] = []
        self.idle = True
        self._load()

    def _load(self):
        f = self.path / "lessons.jsonl"
        if not f.exists():
            return
        for line in f.read_text().splitlines()[-3000:]:
            try:
                d = json.loads(line)
                self.lessons.append(
                    TrainingLesson(
                        **{
                            k: d[k]
                            for k in (
                                "lesson_id",
                                "kind",
                                "pattern",
                                "action",
                                "support",
                                "rooms",
                                "weight",
                                "created_at",
                            )
                            if k in d
                        }
                    )
                )
            except Exception:
                pass

    def _persist(self, lesson: TrainingLesson):
        with (self.path / "lessons.jsonl").open("a") as f:
            f.write(json.dumps(lesson.to_dict()) + "\n")
        if self.learning:
            try:
                self.learning.learn(lesson.kind, lesson.pattern, lesson.action, weight=lesson.weight)
            except Exception:
                pass

    def set_idle(self, idle: bool):
        self.idle = idle

    def _tokens(self, text: str) -> List[str]:
        return re.findall(r"[a-z0-9_]{3,}", (text or "").lower())

    def train_coherent(self, entries: List[Dict[str, Any]]) -> List[TrainingLesson]:
        """Within-room repeated events → coherent lessons."""
        by_room: Dict[str, Counter] = {}
        for e in entries:
            rid = e.get("room_id") or "unknown"
            ev = e.get("event") or ""
            by_room.setdefault(rid, Counter())[ev] += 1
        out = []
        for rid, ctr in by_room.items():
            for event, n in ctr.most_common(5):
                if n < 2 or not event:
                    continue
                lesson = TrainingLesson(
                    lesson_id=str(uuid.uuid4())[:10],
                    kind="coherent",
                    pattern=f"room:{rid}:event:{event}",
                    action=f"prefer_workflow_{event}",
                    support=n,
                    rooms=[rid],
                    weight=min(3.0, 0.5 * n),
                )
                self.lessons.append(lesson)
                self._persist(lesson)
                out.append(lesson)
        return out

    def train_synergistic(self, entries: List[Dict[str, Any]]) -> List[TrainingLesson]:
        """Cross-room token co-occurrence → synergistic lessons."""
        room_tokens: Dict[str, Counter] = {}
        for e in entries:
            rid = e.get("room_id") or "unknown"
            blob = (e.get("raw_text") or "") + " " + str(e.get("event") or "")
            room_tokens.setdefault(rid, Counter()).update(self._tokens(blob))
        # find tokens common to >=2 rooms
        token_rooms: Dict[str, set] = {}
        for rid, ctr in room_tokens.items():
            for tok, n in ctr.items():
                if n >= 1:
                    token_rooms.setdefault(tok, set()).add(rid)
        out = []
        for tok, rooms in token_rooms.items():
            if len(rooms) < 2:
                continue
            if tok in ("room", "event", "status", "true", "false"):
                continue
            lesson = TrainingLesson(
                lesson_id=str(uuid.uuid4())[:10],
                kind="synergistic",
                pattern=f"cross_room_token:{tok}",
                action=f"route_shared_concept_{tok}",
                support=len(rooms),
                rooms=sorted(rooms),
                weight=0.75 * len(rooms),
            )
            self.lessons.append(lesson)
            self._persist(lesson)
            out.append(lesson)
        return out[:40]

    def train_recursive(self, depth: int = 2) -> List[TrainingLesson]:
        """
        Lessons about lessons — compress repeated actions into meta-rules.
        """
        out = []
        actions = Counter(L.action for L in self.lessons[-500:])
        kinds = Counter(L.kind for L in self.lessons[-500:])
        for d in range(depth):
            for action, n in actions.most_common(10):
                if n < 2:
                    continue
                lesson = TrainingLesson(
                    lesson_id=str(uuid.uuid4())[:10],
                    kind="recursive",
                    pattern=f"meta_action:{action}:depth{d}",
                    action=f"reinforce_{action}",
                    support=n,
                    rooms=[],
                    weight=1.0 + 0.2 * d + 0.1 * n,
                )
                self.lessons.append(lesson)
                self._persist(lesson)
                out.append(lesson)
            # recurse on kind distribution
            for kind, n in kinds.most_common():
                lesson = TrainingLesson(
                    lesson_id=str(uuid.uuid4())[:10],
                    kind="recursive",
                    pattern=f"meta_kind:{kind}:depth{d}",
                    action=f"schedule_more_{kind}_training",
                    support=n,
                    rooms=[],
                    weight=1.0 + 0.15 * d,
                )
                self.lessons.append(lesson)
                self._persist(lesson)
                out.append(lesson)
        return out

    def idle_train_once(self, entries: List[Dict[str, Any]], *, recursive_depth: int = 2) -> Dict[str, Any]:
        if not self.idle:
            return {"ok": False, "reason": "not_idle"}
        t0 = time.perf_counter()
        coh = self.train_coherent(entries)
        syn = self.train_synergistic(entries)
        rec = self.train_recursive(depth=recursive_depth)
        ms = (time.perf_counter() - t0) * 1000
        run = {
            "ts": _ts(),
            "coherent": len(coh),
            "synergistic": len(syn),
            "recursive": len(rec),
            "entries": len(entries),
            "ms": round(ms, 2),
        }
        self.runs.append(run)
        with (self.path / "runs.jsonl").open("a") as f:
            f.write(json.dumps(run) + "\n")
        return {"ok": True, **run, "lessons_total": len(self.lessons)}

    def suggest(self, context: str, n: int = 8) -> List[Dict[str, Any]]:
        ctx = (context or "").lower()
        hits = []
        for L in self.lessons[-1000:]:
            if any(p in ctx for p in L.pattern.lower().split(":")) or L.pattern.lower() in ctx:
                hits.append(L.to_dict())
        hits.sort(key=lambda d: -d.get("weight", 0))
        return hits[:n]

    def status(self) -> Dict[str, Any]:
        by = Counter(L.kind for L in self.lessons)
        return {
            "idle": self.idle,
            "lessons": len(self.lessons),
            "by_kind": dict(by),
            "runs": len(self.runs),
            "last_run": self.runs[-1] if self.runs else None,
        }
