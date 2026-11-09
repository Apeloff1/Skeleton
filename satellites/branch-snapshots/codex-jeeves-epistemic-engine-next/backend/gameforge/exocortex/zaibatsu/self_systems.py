from __future__ import annotations
"""
Self-learning + self-healing for the exocortex.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Lesson:
    lesson_id: str
    source: str
    pattern: str
    action: str
    weight: float = 1.0
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


class SelfLearningEngine:
    """
    Records outcome patterns and proposes bias updates (not silent weight hacks on user).
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.path = base / "self_learning" / user_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.lessons: List[Lesson] = []
        self._load()

    def _load(self):
        f = self.path / "lessons.jsonl"
        if not f.exists():
            return
        for line in f.read_text().splitlines()[-2000:]:
            try:
                d = json.loads(line)
                self.lessons.append(Lesson(**{k: d[k] for k in ("lesson_id", "source", "pattern", "action", "weight", "created_at") if k in d}))
            except Exception:
                pass

    def learn(self, source: str, pattern: str, action: str, weight: float = 1.0) -> Lesson:
        import uuid
        lesson = Lesson(
            lesson_id=str(uuid.uuid4())[:10],
            source=source,
            pattern=pattern,
            action=action,
            weight=weight,
        )
        self.lessons.append(lesson)
        with (self.path / "lessons.jsonl").open("a") as fh:
            fh.write(json.dumps(lesson.to_dict()) + "\n")
        return lesson

    def suggest(self, context: str) -> List[Dict[str, Any]]:
        ctx = (context or "").lower()
        hits = []
        for L in self.lessons[-500:]:
            if L.pattern.lower() in ctx or any(w in ctx for w in L.pattern.lower().split()[:3]):
                hits.append(L.to_dict())
        return hits[-10:]

    def status(self) -> Dict[str, Any]:
        return {"lessons": len(self.lessons), "path": str(self.path)}


class SelfHealingEngine:
    """
    Detect degraded subsystems and apply recovery actions.
    """

    def __init__(self):
        self.incidents: List[dict] = []
        self.healed: List[dict] = []

    def diagnose(self, probes: Dict[str, Any]) -> List[dict]:
        issues = []
        if probes.get("frozen"):
            issues.append({"issue": "security_frozen", "severity": "critical", "heal": "await_emperor_unfreeze"})
        if probes.get("handoff_dead_letter", 0) > 0:
            issues.append({"issue": "handoff_dead_letter", "severity": "high", "heal": "requeue_dead_letter"})
        if probes.get("quota_blocked"):
            issues.append({"issue": "quota_blocked", "severity": "medium", "heal": "shed_load_conservation"})
        if probes.get("ras_threshold", 0) > 0.9:
            issues.append({"issue": "ras_oversensitive", "severity": "low", "heal": "reset_ras_threshold"})
        self.incidents.extend({"ts": _ts(), **i} for i in issues)
        return issues

    def heal(self, issue: str, actuators: Dict[str, Any]) -> Dict[str, Any]:
        """
        actuators may include callables or state objects.
        """
        result = {"issue": issue, "ok": False, "action": None}
        if issue == "ras_oversensitive" and "ras" in actuators:
            actuators["ras"].reset_threshold()
            result.update(ok=True, action="ras_reset")
        elif issue == "quota_blocked" and "governor" in actuators:
            actuators["governor"].mode = "conservation"
            result.update(ok=True, action="conservation_mode")
        elif issue == "handoff_dead_letter" and "handoffs" in actuators:
            # mark observation only — dead letters need explicit replay
            result.update(ok=True, action="dead_letter_flagged_for_replay")
        elif issue == "security_frozen":
            result.update(ok=False, action="requires_emperor_seal")
        self.healed.append({"ts": _ts(), **result})
        return result

    def auto_heal(self, probes: Dict[str, Any], actuators: Dict[str, Any]) -> List[dict]:
        out = []
        for iss in self.diagnose(probes):
            out.append(self.heal(iss["issue"], actuators))
        return out
