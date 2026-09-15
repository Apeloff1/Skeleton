"""Skills-as-files context architecture (BACKLOG F-7).

Reload skill / task state from disk on every fresh-context iteration
instead of growing one in-process context forever.

Shape ports the JSON skill-bank idea from ``backend/gameforge/skills/``
(permanent Jeeves bank, per-room bank, MCP→skill saver) into a real
load/reload loop. ``jeeves.assessment.SkillModel`` stays the in-memory
mastery tracker; this module is the file-backed task/context spine.

Extend-only: does not touch Gate/WORM, jeeves CLI, transformer MoD,
organism ``context_loop`` (rot-compaction), or NSOG CLI shims.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from skeleton.kernel.errors import SkeletonError

DEFAULT_ROOT = Path(".skeleton/skills_bank")
_SKILL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_NOTES = 16
_MAX_NOTE_CHARS = 240
_MAX_INSTRUCTION_CHARS = 4000
_MAX_CARD_NOTES = 4


class SkillsFilesError(SkeletonError):
    code = "CTX.SKILLS_FILES"


def _safe_id(value: str, *, label: str = "id") -> str:
    text = (value or "").strip()
    if not _SKILL_ID_RE.match(text):
        raise SkillsFilesError(
            f"invalid {label}",
            context={"value": text[:64]},
        )
    return text


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillsFilesError(
            "failed to read skill/task file",
            context={"path": str(path), "error": type(exc).__name__},
        ) from exc
    if not isinstance(data, dict):
        raise SkillsFilesError(
            "skill/task file must be a JSON object",
            context={"path": str(path)},
        )
    return data


@dataclass
class SkillSpec:
    """Immutable skill definition loaded from a skill file."""

    skill_id: str
    description: str = ""
    source: str = "manual"
    instructions: str = ""
    permanent: bool = True
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SkillSpec":
        skill_id = _safe_id(
            str(data.get("skill_id") or data.get("skill_name") or ""),
            label="skill_id",
        )
        instructions = str(
            data.get("instructions")
            or data.get("description")
            or data.get("body")
            or ""
        )
        reserved = {
            "skill_id",
            "skill_name",
            "description",
            "source",
            "instructions",
            "body",
            "permanent",
            "permanent_for_jeeves",
            "meta",
        }
        meta: Dict[str, Any] = {}
        raw_meta = data.get("meta")
        if isinstance(raw_meta, Mapping):
            meta.update(dict(raw_meta))
        for k, v in data.items():
            if k not in reserved:
                meta[k] = v
        return cls(
            skill_id=skill_id,
            description=str(data.get("description") or "")[:2000],
            source=str(data.get("source") or "manual")[:64],
            instructions=instructions[:_MAX_INSTRUCTION_CHARS],
            permanent=bool(data.get("permanent", data.get("permanent_for_jeeves", True))),
            meta=meta,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "skill_id": self.skill_id,
            "skill_name": self.skill_id,
            "description": self.description,
            "source": self.source,
            "instructions": self.instructions,
            "permanent": self.permanent,
        }
        if self.meta:
            out["meta"] = dict(self.meta)
        return out

    def compact(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "source": self.source,
            "description": self.description[:240],
            "instructions": self.instructions[:800],
            "permanent": self.permanent,
        }


@dataclass
class TaskState:
    """Mutable per-task progress persisted as one JSON file."""

    task_id: str
    skill_id: str
    status: str = "pending"  # pending | running | done | failed
    iteration: int = 0
    cursor: str = ""
    notes: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        self.task_id = _safe_id(self.task_id, label="task_id")
        self.skill_id = _safe_id(self.skill_id, label="skill_id")
        self.status = (self.status or "pending").strip().lower() or "pending"
        self.iteration = max(0, int(self.iteration))
        self.notes = [str(n)[:_MAX_NOTE_CHARS] for n in (self.notes or [])][-_MAX_NOTES:]
        self.payload = dict(self.payload or {})
        self.updated_at = float(self.updated_at or 0.0)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskState":
        return cls(
            task_id=str(data.get("task_id") or ""),
            skill_id=str(data.get("skill_id") or ""),
            status=str(data.get("status") or "pending"),
            iteration=int(data.get("iteration") or 0),
            cursor=str(data.get("cursor") or "")[:500],
            notes=list(data.get("notes") or []),
            payload=dict(data.get("payload") or {}),
            updated_at=float(data.get("updated_at") or 0.0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "skill_id": self.skill_id,
            "status": self.status,
            "iteration": self.iteration,
            "cursor": self.cursor,
            "notes": list(self.notes),
            "payload": dict(self.payload),
            "updated_at": self.updated_at,
        }

    def compact(self, *, note_tail: int = _MAX_CARD_NOTES) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "skill_id": self.skill_id,
            "status": self.status,
            "iteration": self.iteration,
            "cursor": self.cursor[:200],
            "notes_tail": list(self.notes)[-max(0, note_tail) :],
            "payload_keys": sorted(self.payload.keys())[:32],
            "updated_at": self.updated_at,
        }

    def append_note(self, note: str) -> None:
        text = str(note or "").strip()
        if not text:
            return
        self.notes.append(text[:_MAX_NOTE_CHARS])
        if len(self.notes) > _MAX_NOTES:
            self.notes = self.notes[-_MAX_NOTES:]


@dataclass(frozen=True)
class ContextCard:
    """Bounded fresh-context card rebuilt from disk each iteration."""

    iteration: int
    skill: Dict[str, Any]
    task: Dict[str, Any]
    instructions: str
    source_files: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "skills-context-card",
            "iteration": self.iteration,
            "skill": dict(self.skill),
            "task": dict(self.task),
            "instructions": self.instructions,
            "source_files": list(self.source_files),
            "chars": self.chars,
        }

    @property
    def chars(self) -> int:
        return len(self.instructions) + len(json.dumps(self.skill, default=str)) + len(
            json.dumps(self.task, default=str)
        )


# step_fn(card, task_state) -> optional mapping of updates
StepFn = Callable[[ContextCard, TaskState], Optional[Mapping[str, Any]]]


@dataclass
class IterationReport:
    iteration: int
    task_id: str
    skill_id: str
    status: str
    card_chars: int
    reloaded_from_disk: bool
    result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "task_id": self.task_id,
            "skill_id": self.skill_id,
            "status": self.status,
            "card_chars": self.card_chars,
            "reloaded_from_disk": self.reloaded_from_disk,
            "result": dict(self.result),
        }


class SkillBank:
    """Directory-backed skill + task store (gameforge skill-bank sibling)."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_ROOT
        self.skills_dir = self.root / "skills"
        self.tasks_dir = self.root / "tasks"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def skill_path(self, skill_id: str) -> Path:
        return self.skills_dir / f"{_safe_id(skill_id, label='skill_id')}.json"

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{_safe_id(task_id, label='task_id')}.json"

    def upsert_skill(self, skill: SkillSpec) -> Path:
        path = self.skill_path(skill.skill_id)
        _atomic_write_json(path, skill.to_dict())
        return path

    def load_skill(self, skill_id: str) -> SkillSpec:
        path = self.skill_path(skill_id)
        if not path.is_file():
            raise SkillsFilesError(
                "skill file missing",
                context={"skill_id": skill_id, "path": str(path)},
            )
        return SkillSpec.from_dict(_read_json(path))

    def list_skills(self) -> List[str]:
        return sorted(p.stem for p in self.skills_dir.glob("*.json") if p.is_file())

    def save_task(self, task: TaskState, *, now: Optional[float] = None) -> Path:
        task.updated_at = float(now if now is not None else time.time())
        path = self.task_path(task.task_id)
        _atomic_write_json(path, task.to_dict())
        return path

    def load_task(self, task_id: str) -> TaskState:
        path = self.task_path(task_id)
        if not path.is_file():
            raise SkillsFilesError(
                "task file missing",
                context={"task_id": task_id, "path": str(path)},
            )
        return TaskState.from_dict(_read_json(path))

    def list_tasks(self) -> List[str]:
        return sorted(p.stem for p in self.tasks_dir.glob("*.json") if p.is_file())

    def ensure_task(self, task_id: str, skill_id: str) -> TaskState:
        path = self.task_path(task_id)
        if path.is_file():
            return self.load_task(task_id)
        task = TaskState(task_id=task_id, skill_id=skill_id, status="pending")
        self.save_task(task)
        return task

    def import_gameforge_entries(
        self,
        entries: Sequence[Mapping[str, Any]],
        *,
        source_default: str = "gameforge",
    ) -> List[str]:
        """Import skill dicts shaped like backend/gameforge/skills JSON banks."""
        imported: List[str] = []
        for raw in entries:
            if not isinstance(raw, Mapping):
                continue
            data = dict(raw)
            if "source" not in data:
                data["source"] = source_default
            if "skill_id" not in data and "skill_name" in data:
                data["skill_id"] = data["skill_name"]
            if not data.get("instructions") and data.get("description"):
                data["instructions"] = data["description"]
            skill = SkillSpec.from_dict(data)
            self.upsert_skill(skill)
            imported.append(skill.skill_id)
        return imported

    def import_gameforge_bank_file(self, path: Path) -> List[str]:
        """Load a gameforge skill_bank_*.json (skills list or wrapper object)."""
        payload = _read_json(Path(path))
        entries: List[Mapping[str, Any]] = []
        if isinstance(payload.get("skills"), list):
            entries = [e for e in payload["skills"] if isinstance(e, Mapping)]
        elif "skill_name" in payload or "skill_id" in payload:
            entries = [payload]
        elif isinstance(payload.get("skill_bank_per_room"), Mapping):
            room = payload["skill_bank_per_room"]
            for name in room.get("unlocked_skills") or []:
                entries.append(
                    {
                        "skill_id": str(name),
                        "skill_name": str(name),
                        "description": f"Unlocked in room {room.get('room_id')}",
                        "source": "gameforge.room",
                        "permanent": bool(room.get("feeds_into_jeeves_permanent_skill_bank", True)),
                    }
                )
        return self.import_gameforge_entries(entries)


class SkillsContextLoop:
    """Fresh-context iteration loop: disk is source of truth each step.

    Each ``iterate`` call:
      1. drops any previous in-memory card
      2. reloads skill + task JSON from disk
      3. builds a bounded ``ContextCard``
      4. runs ``step_fn(card, task)``
      5. writes updated task state back to disk

    Prior iteration bodies are not accumulated — only a small stats
    counter lives in process memory.
    """

    def __init__(self, bank: SkillBank) -> None:
        self.bank = bank
        self.iterations_run = 0
        self.last_card_chars = 0
        self._last_report: Optional[IterationReport] = None
        # Intentionally NOT a growing transcript of cards / prompts.
        self._working: Optional[ContextCard] = None

    @property
    def last_report(self) -> Optional[IterationReport]:
        return self._last_report

    def build_card(self, skill: SkillSpec, task: TaskState) -> ContextCard:
        skill_path = str(self.bank.skill_path(skill.skill_id))
        task_path = str(self.bank.task_path(task.task_id))
        return ContextCard(
            iteration=int(task.iteration) + 1,
            skill=skill.compact(),
            task=task.compact(),
            instructions=skill.instructions[:_MAX_INSTRUCTION_CHARS],
            source_files=(skill_path, task_path),
        )

    def iterate(
        self,
        task_id: str,
        step_fn: StepFn,
        *,
        skill_id: Optional[str] = None,
    ) -> IterationReport:
        """One fresh-context iteration for ``task_id``."""
        # Drop prior working card — fresh context each iteration.
        self._working = None

        if skill_id is None:
            # Must already exist on disk so we know which skill to bind.
            existing = self.bank.load_task(task_id)
            skill_id = existing.skill_id
        else:
            self.bank.ensure_task(task_id, skill_id)

        skill = self.bank.load_skill(skill_id)
        task = self.bank.load_task(task_id)
        if task.skill_id != skill.skill_id:
            raise SkillsFilesError(
                "task/skill mismatch on disk",
                context={
                    "task_id": task.task_id,
                    "task_skill": task.skill_id,
                    "skill_id": skill.skill_id,
                },
            )

        card = self.build_card(skill, task)
        self._working = card
        self.last_card_chars = card.chars

        task.status = "running"
        updates = step_fn(card, task) or {}
        if not isinstance(updates, Mapping):
            raise SkillsFilesError(
                "step_fn must return a mapping or None",
                context={"type": type(updates).__name__},
            )

        if "status" in updates:
            task.status = str(updates["status"]).strip().lower() or task.status
        if "cursor" in updates:
            task.cursor = str(updates["cursor"])[:500]
        if "note" in updates:
            task.append_note(str(updates["note"]))
        if "notes" in updates and isinstance(updates["notes"], (list, tuple)):
            for note in updates["notes"]:
                task.append_note(str(note))
        if "payload" in updates and isinstance(updates["payload"], Mapping):
            task.payload.update(dict(updates["payload"]))
        if updates.get("done") is True:
            task.status = "done"
        if updates.get("failed") is True:
            task.status = "failed"

        task.iteration = int(task.iteration) + 1
        self.bank.save_task(task)

        # Clear working card after persist — next iterate reloads from disk.
        self._working = None
        self.iterations_run += 1
        report = IterationReport(
            iteration=task.iteration,
            task_id=task.task_id,
            skill_id=task.skill_id,
            status=task.status,
            card_chars=card.chars,
            reloaded_from_disk=True,
            result={k: updates[k] for k in updates if k not in {"payload"}},
        )
        # Keep only the last report in memory (O(1)), never a full history.
        self._last_report = report
        return report

    def run(
        self,
        task_id: str,
        step_fn: StepFn,
        *,
        skill_id: Optional[str] = None,
        max_iterations: int = 8,
    ) -> List[IterationReport]:
        """Run until done/failed or ``max_iterations`` (each step reloads disk)."""
        if max_iterations < 1:
            raise SkillsFilesError(
                "max_iterations must be >= 1",
                context={"max_iterations": max_iterations},
            )
        reports: List[IterationReport] = []
        for _ in range(max_iterations):
            report = self.iterate(task_id, step_fn, skill_id=skill_id)
            reports.append(report)
            skill_id = None  # subsequent iters bind from disk task file
            if report.status in {"done", "failed"}:
                break
        return reports

    def memory_footprint(self) -> Dict[str, Any]:
        """Process-memory stats — proves we do not grow a context transcript."""
        return {
            "iterations_run": self.iterations_run,
            "last_card_chars": self.last_card_chars,
            "working_card_live": self._working is not None,
            "has_last_report": self._last_report is not None,
            "transcript_len": 0,  # explicit: no growing transcript
        }


def mastery_to_skill_file(
    skill_id: str,
    *,
    mastery: float,
    confidence: float,
    attempts: int = 0,
    description: str = "",
) -> SkillSpec:
    """Bridge helper: snapshot in-memory SkillModel fields into a SkillSpec.

    Does not import or mutate ``jeeves.assessment`` — callers pass scalars.
    """
    return SkillSpec(
        skill_id=_safe_id(skill_id, label="skill_id"),
        description=description or f"Mastery snapshot for {skill_id}",
        source="assessment.snapshot",
        instructions=(
            f"Skill `{skill_id}` mastery={float(mastery):.4f} "
            f"confidence={float(confidence):.4f} attempts={int(attempts)}."
        ),
        permanent=True,
        meta={
            "mastery": float(mastery),
            "confidence": float(confidence),
            "attempts": int(attempts),
        },
    )


__all__ = [
    "SkillsFilesError",
    "SkillSpec",
    "TaskState",
    "ContextCard",
    "IterationReport",
    "SkillBank",
    "SkillsContextLoop",
    "StepFn",
    "mastery_to_skill_file",
    "DEFAULT_ROOT",
]
