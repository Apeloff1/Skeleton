"""Embodied, finite apprenticeship and peer learning for original-world citizens.

A mentor cannot teach a job they have never practiced. Two actual residents
must meet, spend stamina and shared food, and complete three separate lessons
before the apprentice earns a recognized profession. Lessons cannot be
multiplied by reloading, duplicate contracts, offscreen claims or idle rounds.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_product_agents import (
    Person, PhysicalSociety, validate_society,
)
from .original_world_product_terrain import TerrainState, validate_terrain

SCHEMA = "original-npc-earned-apprenticeship.v1"
PROFESSIONS = ("forager", "forester", "mason", "healer", "engineer", "scout")
REQUIRED_LESSONS = 3
MAX_APPRENTICESHIPS = 16


@dataclass(frozen=True)
class Apprenticeship:
    number: int
    mentor: int
    apprentice: int
    profession: str
    started_day: int
    lessons: int = 0
    status: str = "active"
    proof_days: tuple[int, ...] = ()


@dataclass(frozen=True)
class TeachingLedger:
    records: tuple[Apprenticeship, ...] = ()
    next_id: int = 0
    food_spent: int = 0
    completed: int = 0
    head: str = "0" * 64


def _hash(data: object) -> str:
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def validate_teaching(
    training: TeachingLedger, people: PhysicalSociety, world: TerrainState,
) -> None:
    validate_society(people, world)
    if not isinstance(training, TeachingLedger) or len(training.records) > MAX_APPRENTICESHIPS:
        raise FoundationError("invalid bounded NPC apprenticeship institution")
    if (type(training.next_id) is not int or
            not 0 <= training.next_id <= MAX_APPRENTICESHIPS):
        raise FoundationError("invalid persistent training identity")
    if (type(training.food_spent) is not int
            or type(training.completed) is not int
            or not 0 <= training.food_spent <= MAX_APPRENTICESHIPS * REQUIRED_LESSONS
            or not 0 <= training.completed <= MAX_APPRENTICESHIPS):
        raise FoundationError("counterfeit apprenticeship resource receipt")
    ids, learners = set(), set()
    completed = 0
    for lesson in training.records:
        if (not isinstance(lesson, Apprenticeship) or lesson.profession not in PROFESSIONS
                or lesson.status not in ("active", "completed", "cancelled")):
            raise FoundationError("invalid original NPC professional mentorship")
        for ident in (lesson.mentor, lesson.apprentice):
            if type(ident) is not int or not 0 <= ident < len(people.inhabitants):
                raise FoundationError("apprenticeship references missing physical person")
        if lesson.mentor == lesson.apprentice:
            raise FoundationError("NPC cannot sign own learned expertise as mentor")
        if (type(lesson.number) is not int or not 0 <= lesson.number < training.next_id
                or lesson.number in ids or type(lesson.started_day) is not int
                or not 0 <= lesson.started_day <= people.tick):
            raise FoundationError("duplicated or future apprenticeship identity")
        ids.add(lesson.number)
        if (type(lesson.lessons) is not int or
                not 0 <= lesson.lessons <= REQUIRED_LESSONS
                or not isinstance(lesson.proof_days, tuple)
                or len(lesson.proof_days) != lesson.lessons):
            raise FoundationError("apprenticeship days cannot exceed verified lessons")
        if (list(lesson.proof_days) != sorted(set(lesson.proof_days))
                or any(type(d) is not int or
                       not lesson.started_day < d <= people.tick
                       for d in lesson.proof_days)):
            raise FoundationError("mentorship duplicates or invents physical world days")
        if lesson.status == "completed":
            completed += 1
            if lesson.lessons != REQUIRED_LESSONS:
                raise FoundationError("profession certified without earned lessons")
        elif lesson.status == "active":
            if lesson.lessons >= REQUIRED_LESSONS or lesson.apprentice in learners:
                raise FoundationError("multiple conflicting active NPC apprenticeships")
            learners.add(lesson.apprentice)
    if completed != training.completed:
        raise FoundationError("professional credentials not backed by completed mentorship")
    if training.food_spent < sum(o.lessons for o in training.records):
        raise FoundationError("training generated skill without meal budget")
    if (not isinstance(training.head, str) or len(training.head) != 64
            or any(c not in "0123456789abcdef" for c in training.head)):
        raise FoundationError("invalid mentoring chain head")


def _seal(before: TeachingLedger, after: TeachingLedger, event: str) -> TeachingLedger:
    return replace(after, head=_hash({
        "schema": SCHEMA, "prior": before.head,
        "old": asdict(before), "new": asdict(after), "event": event,
    }))


def enroll(
    training: TeachingLedger, people: PhysicalSociety, world: TerrainState,
    *, mentor: int, student: int,
) -> TeachingLedger:
    validate_teaching(training, people, world)
    if (type(mentor) is not int or type(student) is not int
            or not 0 <= mentor < len(people.inhabitants)
            or not 0 <= student < len(people.inhabitants)
            or mentor == student):
        raise FoundationError("two separate existing citizens must consent to mentorship")
    teacher, trainee = people.inhabitants[mentor], people.inhabitants[student]
    if (teacher.profession not in PROFESSIONS
            or teacher.experience < 3 or teacher.health <= 0 or trainee.health <= 0):
        raise FoundationError("mentor needs three physically earned work experiences")
    if (abs(teacher.x-trainee.x)+abs(teacher.y-trainee.y) > 1
            or abs(teacher.x)+abs(teacher.y) > 1
            or abs(trainee.x)+abs(trainee.y) > 1):
        raise FoundationError("professional training requires local in-person agreement")
    if trainee.profession == teacher.profession:
        raise FoundationError("citizen already holds the target profession")
    if any(x.status == "active" and x.apprentice == student for x in training.records):
        raise FoundationError("existing training commitment must be finished first")
    if len(training.records) >= MAX_APPRENTICESHIPS:
        raise FoundationError("bounded apprenticeship register exhausted")
    item = Apprenticeship(training.next_id, mentor, student,
                          teacher.profession, people.tick)
    result = _seal(training, replace(
        training, records=training.records + (item,),
        next_id=training.next_id + 1,
    ), "enroll")
    validate_teaching(result, people, world)
    return result


def cancel_enrollment(
    training: TeachingLedger, people: PhysicalSociety,
    world: TerrainState, certificate_id: int,
) -> TeachingLedger:
    validate_teaching(training, people, world)
    active = next((x for x in training.records if x.number == certificate_id
                   and x.status == "active"), None)
    if active is None:
        raise FoundationError("cannot cancel nonexistent or graduated apprenticeship")
    next_state = replace(
        training, records=tuple(
            replace(x, status="cancelled") if x.number == certificate_id else x
            for x in training.records),
    )
    result = _seal(training, next_state, "cancel")
    validate_teaching(result, people, world)
    return result


def settle_training(
    training: TeachingLedger, people: PhysicalSociety, world: TerrainState,
) -> tuple[TeachingLedger, PhysicalSociety, TerrainState, tuple[str, ...]]:
    validate_teaching(training, people, world)
    residents = list(people.inhabitants)
    registry = list(training.records)
    food_spent, total_done = training.food_spent, training.completed
    physical = world
    reports = []
    for i, contract in enumerate(registry):
        if contract.status != "active":
            continue
        mentor, apprentice = residents[contract.mentor], residents[contract.apprentice]
        if (mentor.health <= 0 or apprentice.health <= 0
                or mentor.energy < 2 or apprentice.energy < 2
                or mentor.hunger >= 14 or apprentice.hunger >= 14):
            continue
        if ((mentor.x, mentor.y) != (apprentice.x, apprentice.y)
                or abs(mentor.x) + abs(mentor.y) > 1
                or physical.provisions <= 0):
            continue
        # One lesson per physical day, consumes food and stamina from both.
        # Mentors must retain expertise in the profession being taught.
        if mentor.profession != contract.profession or mentor.experience < 3:
            continue
        if people.tick in contract.proof_days:
            continue
        physical = replace(physical, provisions=physical.provisions - 1)
        mentor = replace(mentor, energy=mentor.energy - 2)
        apprentice = replace(
            apprentice, energy=apprentice.energy - 2,
            experience=min(1000, apprentice.experience + 2),
            relationships=min(20, apprentice.relationships + 1),
        )
        days = contract.proof_days + (people.tick,)
        count = contract.lessons + 1
        finished = count == REQUIRED_LESSONS
        if finished:
            apprentice = replace(apprentice, profession=contract.profession)
            total_done += 1
        residents[mentor.id] = mentor
        residents[apprentice.id] = apprentice
        registry[i] = replace(
            contract, lessons=count, proof_days=days,
            status="completed" if finished else "active",
        )
        food_spent += 1
        reports.append(
            f"Real lesson {count}/{REQUIRED_LESSONS} for citizen {apprentice.id} "
            f"with mentor {mentor.id}; shared food and stamina spent"
            + ("; profession earned" if finished else ""),
        )
    after_people = replace(people, inhabitants=tuple(residents))
    changed = replace(training, records=tuple(registry),
                      food_spent=food_spent, completed=total_done)
    sealed = _seal(training, changed, "lesson-clock-" + str(people.tick))
    validate_teaching(sealed, after_people, physical)
    return sealed, after_people, physical, tuple(reports)


def training_save(training: TeachingLedger) -> dict:
    payload = asdict(training)
    return {"schema": SCHEMA, "payload": payload, "checksum": _hash(payload)}


def training_restore(data: dict, people: PhysicalSociety, world: TerrainState) -> TeachingLedger:
    try:
        if (not isinstance(data, dict) or set(data) != {
            "schema", "payload", "checksum"} or data["schema"] != SCHEMA
                or data["checksum"] != _hash(data["payload"])):
            raise FoundationError("invalid NPC skill teaching archive")
        raw = data["payload"]
        if set(raw) != set(TeachingLedger.__dataclass_fields__):
            raise FoundationError("unexpected teaching ledger")
        contracts = tuple(Apprenticeship(
            **{**rec, "proof_days": tuple(rec["proof_days"])}
        ) for rec in raw["records"])
        result = TeachingLedger(**{**raw, "records": contracts})
        validate_teaching(result, people, world)
        return result
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise FoundationError("invalid mentoring archive") from exc


def training_report(training: TeachingLedger) -> dict:
    return {
        "schema": SCHEMA,
        "recorded_apprenticeships": [asdict(x) for x in training.records],
        "graduates": training.completed,
        "actual_training_food_spent": training.food_spent,
        "earned_lesson_days": sum(x.lessons for x in training.records),
    }
