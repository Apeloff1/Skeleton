"""Strict portable Academy learner and evidence checkpoint codec.

Only explicitly modeled learner state crosses this boundary. No pickles,
provider objects, dynamic imports, model weights or mutable live tasks.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
import json
from math import isfinite
from typing import Any

from skeleton.frontier.payloads import json_snapshot
from skeleton.learning.school.decision_ledger import (
    DecisionDisposition, DecisionLedger, DecisionRecord, EvidenceKind, EvidenceRef,
)
from skeleton.learning.school.memory import LearnerMemory, MemoryKind, MemoryStore
from skeleton.learning.school.policy_calibration import PolicyCalibrator, PolicyStats
from skeleton.learning.school.reflection import (
    ReflectionEntry, ReflectionImportance, ReflectionJournal, ReflectionKind,
)
from skeleton.learning.school.student import SkillState, StudentProfile

SCHEMA = "skeleton.academy.checkpoint.v1"
MAX_CHECKPOINT_BYTES = 4 << 20
MAX_RECORDS = 4096
MAX_ITEMS = 4096


@dataclass
class AcademyState:
    student: StudentProfile
    memory: MemoryStore = field(default_factory=MemoryStore)
    reflections: ReflectionJournal = field(default_factory=ReflectionJournal)
    calibrator: PolicyCalibrator = field(default_factory=PolicyCalibrator)
    ledger: DecisionLedger = field(default_factory=DecisionLedger)


def identity(value: object, maximum: int = 256) -> str:
    if (type(value) is not str or not value or value != value.strip()
            or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("invalid Academy identity")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError("Academy identity byte budget exceeded")
    return value


def _string(value, maximum=16_384, *, empty=True):
    if type(value) is not str or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError("invalid Academy text")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError("Academy text byte budget exceeded")
    return value


def _number(value, low=0.0, high=1.0):
    if type(value) not in (int, float) or not isfinite(value) or not low <= value <= high:
        raise ValueError("invalid Academy numeric field")
    return float(value)


def _count(value):
    if type(value) is not int or not 0 <= value < 1 << 53:
        raise ValueError("invalid Academy counter")
    return value


def _dict(value, keys=None, *, maximum=MAX_ITEMS):
    if type(value) is not dict or len(value) > maximum or (keys is not None and set(value) != set(keys)):
        raise ValueError("invalid Academy object shape")
    return value


def _list(value, maximum=MAX_ITEMS):
    if type(value) not in (tuple, list) or len(value) > maximum:
        raise ValueError("invalid Academy collection")
    return value


def _strings(value, maximum=MAX_ITEMS, *, text_bytes=4096, unique=False):
    result = tuple(_string(x, text_bytes, empty=False) for x in _list(value, maximum))
    if unique and len(result) != len(set(result)):
        raise ValueError("duplicate Academy item")
    return result


def _string_map(value):
    return {identity(k): _string(v) for k, v in _dict(value).items()}


def _project(record, expected):
    if type(record) is not expected:
        raise TypeError("unexpected Academy record type")
    result = {}
    for item in fields(expected):
        value = getattr(record, item.name)
        if type(value) in (MemoryKind, ReflectionKind, ReflectionImportance,
                           EvidenceKind, DecisionDisposition):
            value = value.value
        result[item.name] = value
    return result


def _skill(raw):
    row = _dict(raw, [f.name for f in fields(SkillState)])
    skill = SkillState(
        skill_id=identity(row["skill_id"]), mastery=_number(row["mastery"]),
        confidence=_number(row["confidence"]), attempts=_count(row["attempts"]),
        successes=_count(row["successes"]), last_score=_number(row["last_score"]),
        last_seen_step=_count(row["last_seen_step"]),
        evidence=list(_strings(row["evidence"], 1024)),
    )
    if skill.successes > skill.attempts:
        raise ValueError("learner success count exceeds attempts")
    return skill


def _student(raw):
    row = _dict(raw, [f.name for f in fields(StudentProfile)])
    skills = {}
    for key, value in _dict(row["skills"]).items():
        item = _skill(value)
        if identity(key) != item.skill_id:
            raise ValueError("skill key does not bind identity")
        skills[key] = item
    return StudentProfile(
        student_id=identity(row["student_id"]),
        display_name=_string(row["display_name"], 256, empty=False),
        total_hours=_number(row["total_hours"], 0, 1e9),
        energy=_number(row["energy"]), streak_days=_count(row["streak_days"]),
        goals=list(_strings(row["goals"], 256)),
        interests=set(_strings(row["interests"], 256, unique=True)),
        preferences=_string_map(row["preferences"]),
        skills=skills, facts=_string_map(row["facts"]),
    )


def _student_row(student):
    if type(student) is not StudentProfile:
        raise TypeError("canonical StudentProfile required")
    if type(student.interests) is not set or len(student.interests) > 256:
        raise ValueError("invalid learner interest collection")
    if type(student.skills) is not dict or len(student.skills) > MAX_ITEMS:
        raise ValueError("invalid learner skill collection")
    return {
        "student_id": student.student_id, "display_name": student.display_name,
        "total_hours": student.total_hours, "energy": student.energy,
        "streak_days": student.streak_days, "goals": student.goals,
        "interests": sorted(student.interests), "preferences": student.preferences,
        "skills": {key: _project(value, SkillState) for key, value in student.skills.items()},
        "facts": student.facts,
    }


def _memory(raw):
    row = _dict(raw, [f.name for f in fields(LearnerMemory)])
    return LearnerMemory(
        key=identity(row["key"]), content=_string(row["content"], 16_384, empty=False),
        kind=MemoryKind(row["kind"]), skill_ids=_strings(row["skill_ids"], 128, unique=True),
        importance=_number(row["importance"]), confidence=_number(row["confidence"]),
        access_count=_count(row["access_count"]), age_hours=_number(row["age_hours"], 0, 1e9),
    )


def _reflection(raw):
    row = _dict(raw, [f.name for f in fields(ReflectionEntry)])
    if type(row["pinned"]) is not bool:
        raise ValueError("invalid reflection pin")
    return ReflectionEntry(
        entry_id=identity(row["entry_id"]), kind=ReflectionKind(row["kind"]),
        title=_string(row["title"], 4096, empty=False),
        content=_string(row["content"], 16_384, empty=False),
        importance=ReflectionImportance(row["importance"]),
        skills=_strings(row["skills"], 128, unique=True),
        entities=_strings(row["entities"], 128, unique=True),
        tags=_strings(row["tags"], 128, unique=True),
        lesson_learned=None if row["lesson_learned"] is None else _string(row["lesson_learned"]),
        pinned=row["pinned"],
    )


def _policy(raw):
    row = _dict(raw, ("learning_rate", "stats"))
    learning_rate = _number(row["learning_rate"])
    stats = {}
    for key, value in _dict(row["stats"], maximum=256).items():
        item = _dict(value, ("attempts", "successes", "reward"))
        attempts, successes = _count(item["attempts"]), _count(item["successes"])
        if successes > attempts:
            raise ValueError("policy successes exceed observations")
        stats[identity(key)] = PolicyStats(attempts, successes, _number(item["reward"], -1, 1))
    return PolicyCalibrator(stats=stats, learning_rate=learning_rate)


def _ledger(raw):
    row = _dict(raw, ("head", "identity", "evidence", "records"))
    evidence = {}
    for value in _list(row["evidence"], MAX_RECORDS):
        item = _dict(value, [f.name for f in fields(EvidenceRef)])
        record = EvidenceRef(
            evidence_id=identity(item["evidence_id"], 4096),
            kind=EvidenceKind(item["kind"]),
            subject=_string(item["subject"], 4096, empty=False),
            summary=_string(item["summary"], 4096, empty=False),
            confidence=_number(item["confidence"]),
            source_id=_string(item["source_id"], 4096),
        )
        if record.evidence_id in evidence:
            raise ValueError("duplicate Academy evidence")
        evidence[record.evidence_id] = record
    records = []
    for value in _list(row["records"], MAX_RECORDS):
        item = dict(_dict(value, [f.name for f in fields(DecisionRecord)]))
        item["disposition"] = DecisionDisposition(item["disposition"])
        for key in ("rationale", "evidence", "predecessors", "evidence_digests"):
            item[key] = _strings(item[key], 256)
        item["sequence"] = _count(item["sequence"])
        records.append(DecisionRecord(**item))
    result = DecisionLedger(records=records, evidence=evidence, _head_hash=row["head"])
    result.verify()
    if result.ledger_identity != row["identity"]:
        raise ValueError("Academy ledger identity mismatch")
    return result


def _ledger_row(ledger):
    if type(ledger) is not DecisionLedger:
        raise TypeError("canonical DecisionLedger required")
    with ledger._lock:
        if len(ledger.records) > MAX_RECORDS or len(ledger.evidence) > MAX_RECORDS:
            raise ValueError("Academy ledger checkpoint budget exceeded")
        ledger.verify()
        return {
            "head": ledger.head_hash, "identity": ledger.ledger_identity,
            "evidence": [_project(ledger.evidence[key], EvidenceRef) for key in sorted(ledger.evidence)],
            "records": [_project(record, DecisionRecord) for record in ledger.records],
        }


def _decode(payload):
    row = _dict(payload, ("schema", "student", "memory", "reflections", "policy", "ledger"))
    if row["schema"] != SCHEMA:
        raise ValueError("unsupported Academy checkpoint schema")
    memory = [_memory(item) for item in _list(row["memory"])]
    reflections = [_reflection(item) for item in _list(row["reflections"])]
    if len({item.key for item in memory}) != len(memory):
        raise ValueError("duplicate checkpoint memory identity")
    if len({item.entry_id for item in reflections}) != len(reflections):
        raise ValueError("duplicate checkpoint reflection identity")
    return AcademyState(
        student=_student(row["student"]), memory=MemoryStore(memory),
        reflections=ReflectionJournal(reflections), calibrator=_policy(row["policy"]),
        ledger=_ledger(row["ledger"]),
    )


def encode_state(state: AcademyState) -> bytes:
    if type(state) is not AcademyState or type(state.memory) is not MemoryStore:
        raise TypeError("canonical Academy state required")
    if type(state.reflections) is not ReflectionJournal or type(state.calibrator) is not PolicyCalibrator:
        raise TypeError("canonical Academy control state required")
    state.memory._checked()
    if len(state.reflections.entries) > MAX_ITEMS or len(state.calibrator.stats) > 256:
        raise ValueError("Academy checkpoint collection budget exceeded")
    projection = {
        "schema": SCHEMA, "student": _student_row(state.student),
        "memory": [_project(item, LearnerMemory) for item in state.memory.memories],
        "reflections": [_project(item, ReflectionEntry) for item in state.reflections.entries],
        "policy": {"learning_rate": state.calibrator.learning_rate,
                   "stats": {k: _project(v, PolicyStats) for k, v in state.calibrator.stats.items()}},
        "ledger": _ledger_row(state.ledger),
    }
    detached = json_snapshot(projection, max_bytes=MAX_CHECKPOINT_BYTES)
    # Validate the typed reconstruction before issuing durable bytes.
    _decode(detached)
    raw = json.dumps(detached, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Academy checkpoint exceeds byte budget")
    return raw


def decode_state(raw: bytes) -> AcademyState:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CHECKPOINT_BYTES:
        raise ValueError("invalid Academy checkpoint byte length")
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate Academy JSON key")
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique)
        checked = json_snapshot(value, max_bytes=MAX_CHECKPOINT_BYTES)
        canonical = json.dumps(checked, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode("ascii")
        if raw != canonical:
            raise ValueError("noncanonical Academy checkpoint bytes")
        return _decode(checked)
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid Academy checkpoint") from exc
