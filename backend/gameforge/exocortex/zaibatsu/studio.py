from __future__ import annotations
"""
Conglomerate Studio — evaluation room, feature extraction log,
build→eval→consensus loop, and full studio room graph.

Trajectory-aligned: GameForge snowball builds, DNA board directions,
Zaibatsu VOX, and boardroom consensus until features ship.
"""

import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from gameforge.exocortex.zaibatsu.dna_board import DNABoard, TierSet
try:
    from gameforge.rooms.full_room_registry import all_rooms as _registry_all
except Exception:
    def _registry_all():
        return {}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----- Studio room graph (conglomerate game-studio layout) -------------------

STUDIO_ROOMS = {
    # Leadership
    "boardroom": {"division": "Leadership", "role": "executive_consensus"},
    "evaluation_room": {"division": "Leadership", "role": "feature_eval_gate"},
    # Product / design
    "design_room": {"division": "Product", "role": "systems_design"},
    "narrative_room": {"division": "Product", "role": "story_quest"},
    "ux_room": {"division": "Product", "role": "interface_flow"},
    # Engineering
    "code_room": {"division": "Engineering", "role": "implementation"},
    "math_room": {"division": "Engineering", "role": "exocortex_math"},
    "runtime_room": {"division": "Engineering", "role": "agent_runtime"},
    "build_room": {"division": "Engineering", "role": "pipeline_build"},
    # Quality
    "qa_room": {"division": "Quality", "role": "test_regression"},
    "security_room": {"division": "Quality", "role": "zaibatsu_defense"},
    # Live ops / content
    "world_room": {"division": "Content", "role": "world_gen"},
    "asset_room": {"division": "Content", "role": "mesh_sprite_audio"},
    "balance_room": {"division": "Content", "role": "economy_combat"},
    # Player-facing
    "neuro_room": {"division": "Experience", "role": "affect_jeeves"},
    "calendar_room": {"division": "Experience", "role": "schedule_era"},
}


@dataclass
class FeatureRecord:
    feature_id: str
    name: str
    source_room: str
    description: str
    score: float = 0.0  # 0..100 evaluation score
    status: str = "candidate"  # candidate | shortlisted | approved | rejected | shipped
    evidence: List[str] = field(default_factory=list)
    extracted_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalReport:
    report_id: str
    build_id: str
    features: List[Dict[str, Any]] = field(default_factory=list)
    pass_threshold: float = 75.0
    aggregate_score: float = 0.0
    passed: bool = False
    notes: str = ""
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BuildCycle:
    build_id: str
    goal: str
    iteration: int = 1
    max_iterations: int = 8
    status: str = "running"  # running | eval_failed | consensus_pending | passed | exhausted
    eval_reports: List[str] = field(default_factory=list)
    consensus_vote_id: Optional[str] = None
    approved_features: List[str] = field(default_factory=list)
    log: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


class EvaluationRoom:
    """
    Feature extraction + scoring gate.
    Best features are logged; weak ones stay candidates or get rejected.
    """

    FEATURE_PATTERNS = [
        (r"\b(twin|never.?filtered)\b", "Unfiltered twin memory", 88),
        (r"\b(pfc|prefrontal|executive)\b", "PFC executive control", 90),
        (r"\b(judgement|dual.?panel|skeptic)\b", "Dual-panel judgement", 89),
        (r"\b(vox|boardroom|seal)\b", "VOX command network", 85),
        (r"\b(dna.?board|tier.?set|alpha|gamma)\b", "DNA Board branching", 87),
        (r"\b(sword of truth|wizard.?s rule)\b", "Sword of Truth laws", 86),
        (r"\b(reputation|standing|exalted)\b", "Room reputation / standings", 80),
        (r"\b(self.?heal|self.?learn)\b", "Self-heal / self-learn", 84),
        (r"\b(zaibatsu|security|freeze)\b", "Zaibatsu security", 88),
        (r"\b(sympy|lean|certainty)\b", "Certainty math stack", 91),
        (r"\b(homeostasis|salience|ras)\b", "Neuro coherence", 85),
        (r"\b(handoff|dead.?letter|ack)\b", "Enterprise handoffs", 86),
        (r"\b(conglomerate|quota|isolation)\b", "Conglomerate governance", 90),
        (r"\b(mesh|nerf|splat|world.?gen)\b", "3D / world generation", 82),
        (r"\b(agent|room.?handler|coder.?style)\b", "Agent room specialization", 83),
    ]

    def __init__(self):
        self.features: Dict[str, FeatureRecord] = {}
        self.reports: Dict[str, EvalReport] = {}
        self.extraction_log: List[dict] = []

    def extract_from_text(self, text: str, source_room: str = "build_room") -> List[FeatureRecord]:
        """Pull best feature candidates from build notes / trajectory text."""
        found: List[FeatureRecord] = []
        t = text or ""
        for pat, name, base in self.FEATURE_PATTERNS:
            if re.search(pat, t, re.I):
                # de-dupe by name
                existing = next((f for f in self.features.values() if f.name == name), None)
                if existing:
                    existing.evidence.append(t[:240])
                    existing.score = min(100.0, existing.score + 2.0)
                    found.append(existing)
                    continue
                fr = FeatureRecord(
                    feature_id=str(uuid.uuid4())[:10],
                    name=name,
                    source_room=source_room,
                    description=f"Extracted pattern /{pat}/ from {source_room}",
                    score=float(base),
                    evidence=[t[:240]],
                )
                self.features[fr.feature_id] = fr
                found.append(fr)
                self.extraction_log.append(
                    {"ts": _ts(), "feature_id": fr.feature_id, "name": name, "source_room": source_room}
                )
        return found

    def extract_from_status(self, status_blob: Dict[str, Any], source_room: str = "evaluation_room") -> List[FeatureRecord]:
        """Extract from structured exocortex/zaibatsu status."""
        text = str(status_blob)
        return self.extract_from_text(text, source_room=source_room)

    def score_feature(self, feature_id: str, score: float, note: str = "") -> Dict[str, Any]:
        f = self.features.get(feature_id)
        if not f:
            return {"ok": False, "error": "not_found"}
        f.score = max(0.0, min(100.0, score))
        if note:
            f.evidence.append(note)
        if f.score >= 75:
            f.status = "shortlisted"
        elif f.score < 50:
            f.status = "rejected"
        return {"ok": True, "feature": f.to_dict()}

    def evaluate_build(self, build_id: str, feature_ids: Optional[List[str]] = None, threshold: float = 75.0) -> EvalReport:
        ids = feature_ids or [fid for fid, f in self.features.items() if f.status in ("candidate", "shortlisted", "approved")]
        feats = [self.features[i].to_dict() for i in ids if i in self.features]
        if not feats:
            agg = 0.0
        else:
            agg = sum(f["score"] for f in feats) / len(feats)
        passed = agg >= threshold and len(feats) > 0
        # promote shortlisted on pass
        if passed:
            for i in ids:
                if i in self.features and self.features[i].status == "shortlisted":
                    self.features[i].status = "approved"
        report = EvalReport(
            report_id=str(uuid.uuid4())[:10],
            build_id=build_id,
            features=feats,
            pass_threshold=threshold,
            aggregate_score=round(agg, 2),
            passed=passed,
            notes="PASS" if passed else "FAIL — iterate build",
        )
        self.reports[report.report_id] = report
        self.extraction_log.append(
            {"ts": _ts(), "event": "eval_report", "report_id": report.report_id, "passed": passed, "score": agg}
        )
        return report

    def best_features(self, n: int = 10) -> List[Dict[str, Any]]:
        rows = sorted(self.features.values(), key=lambda f: f.score, reverse=True)
        return [f.to_dict() for f in rows[:n]]

    def log_tail(self, n: int = 30) -> List[dict]:
        return self.extraction_log[-n:]


class StudioOrchestrator:
    """
    Repeat: build → evaluate → (fail → rebuild) → boardroom consensus on features.
    Stops only when eval passes AND consensus approves feature set.
    """

    def __init__(self, dna: Optional[DNABoard] = None):
        self.dna = dna or DNABoard()
        self.eval_room = EvaluationRoom()
        self.cycles: Dict[str, BuildCycle] = {}
        self.studio_rooms = dict(STUDIO_ROOMS)
        self.studio_rooms.update({k: {"division": v.get("division","Other"), "role": v.get("role","")} for k,v in _registry_all().items()})
        # register all studio rooms on DNA board
        for rid in self.studio_rooms:
            self.dna.ensure_room(rid)
        self.audit: List[dict] = []

    def _audit(self, event: str, **kw):
        self.audit.append({"ts": _ts(), "event": event, **kw})

    def bootstrap_room_directions(self) -> Dict[str, Any]:
        """
        Conglomerate studio: each connected room gets 3 consecutive directions
        tailored to its role.
        """
        templates = {
            "evaluation_room": [
                ("Extract features", "Scan latest build artifacts for feature candidates"),
                ("Score shortlist", "Apply threshold and promote shortlisted features"),
                ("Publish eval report", "Emit pass/fail to boardroom via VOX"),
            ],
            "build_room": [
                ("Assemble increment", "Integrate approved deltas from last cycle"),
                ("Run pipeline", "Execute build path and capture logs"),
                ("Submit to eval", "Hand package to evaluation_room"),
            ],
            "code_room": [
                ("Implement tickets", "Code features from DNA active tier"),
                ("Unit smoke", "Run local tests"),
                ("PR to build", "Deliver to build_room"),
            ],
            "math_room": [
                ("Certainty pass", "SymPy/Lean/PoW checks on math surfaces"),
                ("Tier logs", "Ensure primary/secondary/tertiary logs"),
                ("Report metrics", "Ship numbers to evaluation_room"),
            ],
            "qa_room": [
                ("Regression pack", "Run suite"),
                ("Gate failures", "File blockers"),
                ("Signoff or reject", "Vote-ready status"),
            ],
            "boardroom": [
                ("Review eval", "Read evaluation_room report"),
                ("Open consensus vote", "Feature set approval"),
                ("Seal decision", "VOX outcome to all rooms"),
            ],
        }
        default = [
            ("Intake brief", "Receive boardroom direction 1"),
            ("Execute core work", "Produce room-specific output"),
            ("Report upward", "Return status for eval/consensus"),
        ]
        issued = {}
        for rid in self.studio_rooms:
            if rid == "boardroom":
                dirs = templates.get(rid, default)
            else:
                dirs = templates.get(rid, default)
            # only issue if no active chain
            track = self.dna.ensure_room(rid)
            pending = [d for d in track.directions if d.get("status") in ("pending", "active")]
            if pending:
                issued[rid] = {"ok": False, "skipped": True, "reason": "active_chain"}
                continue
            issued[rid] = self.dna.issue_directions(rid, dirs)
        self._audit("bootstrap_directions", rooms=len(issued))
        return issued

    def start_cycle(self, goal: str, max_iterations: int = 8) -> BuildCycle:
        c = BuildCycle(
            build_id=str(uuid.uuid4())[:10],
            goal=goal,
            max_iterations=max_iterations,
        )
        self.cycles[c.build_id] = c
        c.log.append({"ts": _ts(), "event": "start", "goal": goal})
        self._audit("start_cycle", build_id=c.build_id, goal=goal)
        return c

    def run_build_iteration(self, build_id: str, build_notes: str, source_room: str = "build_room") -> Dict[str, Any]:
        """One build pass: extract features from notes, evaluate, decide next."""
        c = self.cycles.get(build_id)
        if not c:
            return {"ok": False, "error": "unknown_build"}
        if c.status in ("passed", "exhausted"):
            return {"ok": False, "error": f"cycle_{c.status}"}

        extracted = self.eval_room.extract_from_text(build_notes, source_room=source_room)
        report = self.eval_room.evaluate_build(build_id, threshold=75.0)
        c.eval_reports.append(report.report_id)
        c.log.append(
            {
                "ts": _ts(),
                "event": "iteration",
                "iteration": c.iteration,
                "extracted": len(extracted),
                "eval_passed": report.passed,
                "score": report.aggregate_score,
            }
        )

        if not report.passed:
            c.iteration += 1
            if c.iteration > c.max_iterations:
                c.status = "exhausted"
                return {
                    "ok": True,
                    "build_id": build_id,
                    "status": c.status,
                    "report": report.to_dict(),
                    "next": "stop_exhausted",
                }
            c.status = "eval_failed"
            return {
                "ok": True,
                "build_id": build_id,
                "status": c.status,
                "iteration": c.iteration,
                "report": report.to_dict(),
                "next": "rebuild",
                "message": "Eval failed — repeat build process with improvements",
            }

        # eval passed → need boardroom consensus on features
        c.status = "consensus_pending"
        shortlisted = [f for f in self.eval_room.features.values() if f.status in ("approved", "shortlisted")]
        options = ["approve_feature_set", "reject_iterate"]
        room_ids = ["boardroom", "evaluation_room", "qa_room", "build_room", "code_room"]
        vote = self.dna.open_vote(
            subject=f"Approve features for build {build_id}",
            options=options,
            room_ids=room_ids,
        )
        c.consensus_vote_id = vote.vote_id
        # auto-cast evaluation + qa lean approve if scores high
        self.dna.cast_vote(vote.vote_id, "evaluation_room", "approve_feature_set")
        self.dna.cast_vote(vote.vote_id, "qa_room", "approve_feature_set" if report.aggregate_score >= 80 else "reject_iterate")
        return {
            "ok": True,
            "build_id": build_id,
            "status": c.status,
            "report": report.to_dict(),
            "vote_id": vote.vote_id,
            "features": [f.to_dict() for f in shortlisted],
            "next": "boardroom_consensus",
            "message": "Eval passed — awaiting boardroom consensus vote",
        }

    def cast_consensus(self, build_id: str, room_id: str, option: str) -> Dict[str, Any]:
        c = self.cycles.get(build_id)
        if not c or not c.consensus_vote_id:
            return {"ok": False, "error": "no_consensus_vote"}
        return self.dna.cast_vote(c.consensus_vote_id, room_id, option)

    def seal_consensus(self, build_id: str) -> Dict[str, Any]:
        c = self.cycles.get(build_id)
        if not c or not c.consensus_vote_id:
            return {"ok": False, "error": "no_consensus_vote"}
        result = self.dna.close_vote(c.consensus_vote_id)
        if not result.get("ok"):
            return result
        if result.get("winner") == "approve_feature_set" and result.get("consensus"):
            c.status = "passed"
            approved = [
                f.feature_id
                for f in self.eval_room.features.values()
                if f.status in ("approved", "shortlisted")
            ]
            for fid in approved:
                if fid in self.eval_room.features:
                    self.eval_room.features[fid].status = "shipped"
            c.approved_features = approved
            c.log.append({"ts": _ts(), "event": "passed", "features": approved})
            return {
                "ok": True,
                "status": "passed",
                "consensus": result,
                "shipped_features": [self.eval_room.features[i].to_dict() for i in approved if i in self.eval_room.features],
                "message": "Boardroom consensus achieved — features sealed",
            }
        # rejected — iterate again
        c.iteration += 1
        c.status = "eval_failed" if c.iteration <= c.max_iterations else "exhausted"
        c.consensus_vote_id = None
        c.log.append({"ts": _ts(), "event": "consensus_reject", "iteration": c.iteration})
        return {
            "ok": True,
            "status": c.status,
            "consensus": result,
            "next": "rebuild" if c.status != "exhausted" else "stop_exhausted",
            "message": "Consensus rejected feature set — repeat build process",
        }

    def run_until_passed(
        self,
        goal: str,
        notes_per_iteration: List[str],
        board_votes: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Convenience: feed successive build notes until pass+consensus or exhausted.
        board_votes: optional list of (room_id, option) for boardroom/code/build casts.
        """
        cycle = self.start_cycle(goal)
        history = []
        for notes in notes_per_iteration:
            if cycle.status in ("passed", "exhausted"):
                break
            step = self.run_build_iteration(cycle.build_id, notes)
            history.append(step)
            if step.get("next") == "boardroom_consensus":
                # default boardroom + build + code approve unless overridden
                votes = board_votes or [
                    ("boardroom", "approve_feature_set"),
                    ("build_room", "approve_feature_set"),
                    ("code_room", "approve_feature_set"),
                ]
                for room_id, opt in votes:
                    self.cast_consensus(cycle.build_id, room_id, opt)
                seal = self.seal_consensus(cycle.build_id)
                history.append(seal)
                if seal.get("status") == "passed":
                    break
                # else loop continues with next notes
        return {
            "build_id": cycle.build_id,
            "final_status": cycle.status,
            "iterations": cycle.iteration,
            "history": history,
            "best_features": self.eval_room.best_features(15),
            "extraction_log": self.eval_room.log_tail(40),
            "cycle": cycle.to_dict(),
        }

    def status(self) -> Dict[str, Any]:
        return {
            "studio_rooms": self.studio_rooms,
            "cycles": {k: v.to_dict() for k, v in self.cycles.items()},
            "best_features": self.eval_room.best_features(12),
            "extraction_log_tail": self.eval_room.log_tail(20),
            "dna_progress": self.dna.room_to_room_progress(),
            "audit_tail": self.audit[-15:],
        }
