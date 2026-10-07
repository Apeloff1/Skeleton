"""Fresh-context execution over filesystem-backed skills.

F-7 closes the gap between ``skeleton.skills`` (versioned skill manifests and
promotion state) and long-running task execution.  Disk is the source of truth
for every iteration: the skill manifest, skill state, and task state are loaded
again before a bounded context card is built.  No prompt/card transcript is
retained in process memory.

The task file has an optimistic revision counter so a callback cannot silently
clobber a concurrent writer.  Writes are atomic, identifiers are path-safe, and
card/task fields are bounded before persistence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .manifest import SkillManifest, SkillState
from .store import SkillStore

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TERMINAL = {"done", "failed", "cancelled"}
_ALLOWED_STATUS = {"pending", "running", "paused", *_TERMINAL}
_MAX_NOTES = 16
_MAX_NOTE_CHARS = 240
_MAX_CURSOR_CHARS = 500
_MAX_INSTRUCTIONS_CHARS = 4000
_MAX_COLLECTION = 32
_MAX_STRING = 1000
_MAX_PAYLOAD_KEYS = 64
_MAX_CARD_NOTES = 4


class SkillContextError(RuntimeError):
    """Base error for the fresh-context task spine."""


class ConcurrentTaskUpdate(SkillContextError):
    """Raised when task state changed on disk after an iteration loaded it."""


def _safe_id(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    if not _SAFE_ID.fullmatch(text):
        raise SkillContextError(f"invalid {label}: {text[:64]!r}")
    return text


def _clip_text(value: Any, limit: int = _MAX_STRING) -> str:
    return str(value or "")[: max(0, int(limit))]


def _bounded(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-safe, size-bounded representation.

    Task payloads are durable coordination state, not an unbounded transcript.
    Deep or large values are deliberately summarized before persistence.
    """
    if depth >= 4:
        return _clip_text(value, 240)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_STRING]
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for key in sorted(value, key=lambda k: str(k))[:_MAX_PAYLOAD_KEYS]:
            out[_clip_text(key, 128)] = _bounded(value[key], depth=depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_bounded(v, depth=depth + 1) for v in list(value)[:_MAX_COLLECTION]]
    return _clip_text(value)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillContextError(f"task file missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillContextError(f"invalid task file: {path}") from exc
    if not isinstance(value, dict):
        raise SkillContextError(f"task file must contain a JSON object: {path}")
    return value


def _fingerprint(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def _clip_seq(values: Sequence[Any], *, item_chars: int = 240) -> list[str]:
    return [_clip_text(v, item_chars) for v in list(values)[:_MAX_COLLECTION]]


@dataclass
class TaskState:
    """Bounded mutable state for one skill-backed task."""

    task_id: str
    skill_name: str
    status: str = "pending"
    iteration: int = 0
    revision: int = 0
    cursor: str = ""
    notes: list[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        self.task_id = _safe_id(self.task_id, label="task_id")
        self.skill_name = _safe_id(self.skill_name, label="skill_name")
        status = str(self.status or "pending").strip().lower()
        if status not in _ALLOWED_STATUS:
            raise SkillContextError(f"invalid task status: {status!r}")
        self.status = status
        self.iteration = max(0, int(self.iteration))
        self.revision = max(0, int(self.revision))
        self.cursor = _clip_text(self.cursor, _MAX_CURSOR_CHARS)
        self.notes = [
            _clip_text(note, _MAX_NOTE_CHARS)
            for note in list(self.notes or [])[-_MAX_NOTES:]
            if str(note or "").strip()
        ]
        self.payload = dict(_bounded(dict(self.payload or {})))
        self.updated_at = float(self.updated_at or 0.0)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskState":
        return cls(
            task_id=str(data.get("task_id") or ""),
            skill_name=str(data.get("skill_name") or data.get("skill_id") or ""),
            status=str(data.get("status") or "pending"),
            iteration=int(data.get("iteration") or 0),
            revision=int(data.get("revision") or 0),
            cursor=str(data.get("cursor") or ""),
            notes=list(data.get("notes") or []),
            payload=dict(data.get("payload") or {}),
            updated_at=float(data.get("updated_at") or 0.0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "skill_name": self.skill_name,
            "status": self.status,
            "iteration": self.iteration,
            "revision": self.revision,
            "cursor": self.cursor,
            "notes": list(self.notes),
            "payload": dict(_bounded(self.payload)),
            "updated_at": self.updated_at,
        }

    def append_note(self, note: Any) -> None:
        text = _clip_text(note, _MAX_NOTE_CHARS).strip()
        if not text:
            return
        self.notes.append(text)
        self.notes = self.notes[-_MAX_NOTES:]

    def compact(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "skill_name": self.skill_name,
            "status": self.status,
            "iteration": self.iteration,
            "revision": self.revision,
            "cursor": self.cursor[:200],
            "notes_tail": list(self.notes)[-_MAX_CARD_NOTES:],
            "payload": _bounded(self.payload),
            "updated_at": self.updated_at,
        }


class TaskFileStore:
    """Atomic task-state sidecar colocated with a ``SkillStore`` root."""

    def __init__(self, skill_store: SkillStore) -> None:
        self.skill_store = skill_store
        self.root = Path(skill_store.root) / "tasks"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, task_id: str) -> Path:
        return self.root / f"{_safe_id(task_id, label='task_id')}.json"

    def exists(self, task_id: str) -> bool:
        return self.path(task_id).is_file()

    def load(self, task_id: str) -> TaskState:
        return TaskState.from_dict(_read_json(self.path(task_id)))

    def save(self, task: TaskState, *, expected_revision: Optional[int] = None) -> Path:
        path = self.path(task.task_id)
        if expected_revision is not None:
            if not path.is_file():
                raise ConcurrentTaskUpdate(f"task disappeared during iteration: {task.task_id}")
            current = TaskState.from_dict(_read_json(path))
            if current.revision != int(expected_revision):
                raise ConcurrentTaskUpdate(
                    f"task changed during iteration: {task.task_id} "
                    f"expected revision {expected_revision}, found {current.revision}"
                )
        task.revision = max(task.revision, int(expected_revision or 0)) + 1
        task.updated_at = time.time()
        task.payload = dict(_bounded(task.payload))
        _atomic_json(path, task.to_dict())
        return path

    def ensure(self, task_id: str, skill_name: str) -> TaskState:
        task_id = _safe_id(task_id, label="task_id")
        skill_name = _safe_id(skill_name, label="skill_name")
        if self.exists(task_id):
            task = self.load(task_id)
            if task.skill_name != skill_name:
                raise SkillContextError(
                    f"task/skill mismatch: {task_id!r} binds {task.skill_name!r}, not {skill_name!r}"
                )
            return task
        task = TaskState(task_id=task_id, skill_name=skill_name)
        self.save(task)
        return task


@dataclass(frozen=True)
class FreshContextCard:
    """Bounded context rebuilt from files at the start of an iteration."""

    iteration: int
    skill: Dict[str, Any]
    skill_state: Dict[str, Any]
    task: Dict[str, Any]
    instructions: str
    source_files: tuple[str, ...]
    source_fingerprints: tuple[str, ...]

    @property
    def chars(self) -> int:
        return len(json.dumps(self.to_dict(), sort_keys=True, default=str))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "fresh-skill-context",
            "iteration": self.iteration,
            "skill": dict(self.skill),
            "skill_state": dict(self.skill_state),
            "task": dict(self.task),
            "instructions": self.instructions,
            "source_files": list(self.source_files),
            "source_fingerprints": list(self.source_fingerprints),
        }


@dataclass(frozen=True)
class IterationReport:
    iteration: int
    task_id: str
    skill_name: str
    status: str
    task_revision: int
    card_chars: int
    reloaded_from_disk: bool
    source_fingerprints: tuple[str, ...]
    result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "task_id": self.task_id,
            "skill_name": self.skill_name,
            "status": self.status,
            "task_revision": self.task_revision,
            "card_chars": self.card_chars,
            "reloaded_from_disk": self.reloaded_from_disk,
            "source_fingerprints": list(self.source_fingerprints),
            "result": dict(self.result),
        }


StepFn = Callable[[FreshContextCard, TaskState], Optional[Mapping[str, Any]]]


def _manifest_card(manifest: SkillManifest) -> Dict[str, Any]:
    return {
        "name": _safe_id(manifest.name, label="skill_name"),
        "version": _clip_text(manifest.version, 64),
        "capabilities": _clip_seq(manifest.capabilities),
        "preconditions": _clip_seq(manifest.preconditions),
        "invariants": _clip_seq(manifest.invariants),
        "evaluation": _clip_seq(manifest.evaluation),
        "provenance": _clip_text(manifest.provenance, 240),
    }


def _state_card(state: SkillState) -> Dict[str, Any]:
    return {
        "status": _clip_text(state.status, 64),
        "attempts": max(0, int(state.attempts)),
        "successes": max(0, int(state.successes)),
        "regressions": max(0, int(state.regressions)),
        "success_rate": float(state.success_rate),
        "last_trace": _clip_text(state.last_trace, 500),
        "metadata_keys": sorted(str(k)[:128] for k in state.metadata)[:_MAX_COLLECTION],
    }


def _instructions(manifest: SkillManifest) -> str:
    sections = [f"Skill {manifest.name}@{manifest.version}"]
    for title, values in (
        ("Capabilities", manifest.capabilities),
        ("Preconditions", manifest.preconditions),
        ("Invariants", manifest.invariants),
        ("Evaluation", manifest.evaluation),
    ):
        clipped = _clip_seq(values)
        if clipped:
            sections.append(f"{title}: " + "; ".join(clipped))
    if manifest.provenance:
        sections.append("Provenance: " + _clip_text(manifest.provenance, 400))
    return "\n".join(sections)[:_MAX_INSTRUCTIONS_CHARS]


class FreshSkillContextLoop:
    """Run task iterations without accumulating an in-memory context history."""

    def __init__(self, skill_store: SkillStore, task_store: Optional[TaskFileStore] = None) -> None:
        self.skill_store = skill_store
        self.task_store = task_store or TaskFileStore(skill_store)
        self.iterations_run = 0
        self.last_card_chars = 0
        self._working: Optional[FreshContextCard] = None
        self._last_report: Optional[IterationReport] = None

    @property
    def last_report(self) -> Optional[IterationReport]:
        return self._last_report

    def _source_paths(self, skill_name: str, task_id: str) -> tuple[Path, Path, Path]:
        skill_name = _safe_id(skill_name, label="skill_name")
        skill_dir = Path(self.skill_store.root) / skill_name
        return skill_dir / "manifest.json", skill_dir / "state.json", self.task_store.path(task_id)

    def build_card(
        self,
        manifest: SkillManifest,
        state: SkillState,
        task: TaskState,
    ) -> FreshContextCard:
        paths = self._source_paths(manifest.name, task.task_id)
        return FreshContextCard(
            iteration=task.iteration + 1,
            skill=_manifest_card(manifest),
            skill_state=_state_card(state),
            task=task.compact(),
            instructions=_instructions(manifest),
            source_files=tuple(str(p) for p in paths),
            source_fingerprints=tuple(_fingerprint(p) for p in paths),
        )

    @staticmethod
    def _apply_updates(task: TaskState, updates: Mapping[str, Any]) -> None:
        if "status" in updates:
            status = str(updates["status"] or task.status).strip().lower()
            if status not in _ALLOWED_STATUS:
                raise SkillContextError(f"invalid task status: {status!r}")
            task.status = status
        if "cursor" in updates:
            task.cursor = _clip_text(updates["cursor"], _MAX_CURSOR_CHARS)
        if "note" in updates:
            task.append_note(updates["note"])
        notes = updates.get("notes")
        if isinstance(notes, (list, tuple)):
            for note in notes:
                task.append_note(note)
        payload = updates.get("payload")
        if isinstance(payload, Mapping):
            merged = dict(task.payload)
            merged.update(dict(payload))
            task.payload = dict(_bounded(merged))
        if updates.get("done") is True:
            task.status = "done"
        if updates.get("failed") is True:
            task.status = "failed"
        if updates.get("cancelled") is True:
            task.status = "cancelled"

    def iterate(
        self,
        task_id: str,
        step_fn: StepFn,
        *,
        skill_name: Optional[str] = None,
    ) -> IterationReport:
        """Run one iteration after reloading every durable input from disk."""
        self._working = None
        task_id = _safe_id(task_id, label="task_id")

        if skill_name is not None:
            task = self.task_store.ensure(task_id, skill_name)
        else:
            task = self.task_store.load(task_id)
        loaded_revision = task.revision

        manifest, skill_state = self.skill_store.load(task.skill_name)
        if manifest.name != task.skill_name:
            raise SkillContextError(
                f"task/manifest mismatch: {task.skill_name!r} != {manifest.name!r}"
            )

        card = self.build_card(manifest, skill_state, task)
        self._working = card
        self.last_card_chars = card.chars
        task.status = "running" if task.status not in _TERMINAL else task.status

        try:
            raw_updates = step_fn(card, task)
            updates: Mapping[str, Any] = raw_updates or {}
            if not isinstance(updates, Mapping):
                raise SkillContextError(
                    f"step_fn must return a mapping or None, got {type(updates).__name__}"
                )
            self._apply_updates(task, updates)
            task.iteration += 1
            self.task_store.save(task, expected_revision=loaded_revision)
        finally:
            self._working = None

        self.iterations_run += 1
        result = {k: _bounded(v) for k, v in updates.items() if k != "payload"}
        report = IterationReport(
            iteration=task.iteration,
            task_id=task.task_id,
            skill_name=task.skill_name,
            status=task.status,
            task_revision=task.revision,
            card_chars=card.chars,
            reloaded_from_disk=True,
            source_fingerprints=card.source_fingerprints,
            result=result,
        )
        self._last_report = report
        return report

    def run(
        self,
        task_id: str,
        step_fn: StepFn,
        *,
        skill_name: Optional[str] = None,
        max_iterations: int = 8,
    ) -> list[IterationReport]:
        if int(max_iterations) < 1:
            raise SkillContextError("max_iterations must be >= 1")
        reports: list[IterationReport] = []
        bound_skill = skill_name
        for _ in range(int(max_iterations)):
            report = self.iterate(task_id, step_fn, skill_name=bound_skill)
            reports.append(report)
            bound_skill = None
            if report.status in _TERMINAL:
                break
        return reports

    def memory_footprint(self) -> Dict[str, Any]:
        return {
            "iterations_run": self.iterations_run,
            "last_card_chars": self.last_card_chars,
            "working_card_live": self._working is not None,
            "has_last_report": self._last_report is not None,
            "transcript_len": 0,
        }


__all__ = [
    "ConcurrentTaskUpdate",
    "FreshContextCard",
    "FreshSkillContextLoop",
    "IterationReport",
    "SkillContextError",
    "StepFn",
    "TaskFileStore",
    "TaskState",
]
