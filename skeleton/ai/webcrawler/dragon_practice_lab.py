"""Dragon Practice Lab: approved knowledge -> bounded playable game exercises.

A voluntary sidecar inside the existing crawler/game-builder plane. A successful
crawl is NOT evidence of knowledge mastery. Only an eligible canonical promotion
decision plus human review may enqueue a lesson. The lab generates real, original
self-contained HTML prototypes using the existing Dragon playable renderer.
No provider calls, network IO, hidden threads, background polling or autonomous
resource consumption occur here. The host scheduler must explicitly invoke work.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
import sqlite3

from .dragon_game_forge import GameDesignConstraint, GameMechanicDesign, GamePrototypeSpec
from .dragon_game_mechanics import Mechanic
from .dragon_knowledge_promotion import PromotionDecision
from .dragon_playable_prototype import render_playable_prototype


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _fingerprint(text: str) -> bool:
    return isinstance(text, str) and len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _owner(text: str) -> None:
    if not isinstance(text, str) or not 1 <= len(text) <= 128:
        raise ValueError("invalid practice owner")


def _time(now: float) -> None:
    if not isinstance(now, (int, float)) or not isfinite(now) or now < 0:
        raise ValueError("invalid practice clock")


PRACTICE_MECHANICS = frozenset((
    Mechanic.MOVEMENT, Mechanic.PLATFORMING, Mechanic.PHYSICS,
    Mechanic.EXPLORATION, Mechanic.LEVEL_DESIGN,
))
# The existing renderer has implementations for these mechanics. Other observed
# mechanics remain lessons, not falsely completed game features.
PRACTICE_KINDS = ("movement_lab", "jump_lab", "exploration_lab", "physics_lab")


@dataclass(frozen=True)
class PracticePolicy:
    max_demos_per_lesson: int = 4
    max_demos_per_day: int = 12
    max_demos_per_batch: int = 4
    max_artifact_bytes: int = 160_000
    max_lessons_per_owner: int = 1000


@dataclass(frozen=True)
class ApprovedLesson:
    owner: str
    title: str
    promotion: PromotionDecision
    review_fingerprint: str
    observed_mechanics: tuple[Mechanic, ...]
    # Explicit approval to create practice games, independent of research consent.
    practice_consent: bool


@dataclass(frozen=True)
class PracticeAttempt:
    attempt_id: str
    lesson_id: str
    owner: str
    kind: str
    state: str
    artifact_digest: str
    supported: tuple[str, ...]
    deferred: tuple[str, ...]
    created_at: float
    review_digest: str = ""
    error_code: str = ""


@dataclass(frozen=True)
class PracticeProgress:
    owner: str
    level: int
    xp: int
    next_level_xp: int
    verified_lessons: int
    demos_built: int
    demos_reviewed: int
    demo_attempts: int
    failed_attempts: int
    skills: dict[str, int]
    unlocked: tuple[str, ...]
    # This projection is for the UI; no ledger mutation or fabricated learning.
    schema: str = "skeleton.ai.dragon.practice_progress.v1"


def _policy(policy: PracticePolicy) -> None:
    if not (1 <= policy.max_demos_per_lesson <= 12
            and 1 <= policy.max_demos_per_day <= 100
            and 1 <= policy.max_demos_per_batch <= policy.max_demos_per_day
            and 10_000 <= policy.max_artifact_bytes <= 2_000_000
            and 1 <= policy.max_lessons_per_owner <= 100_000):
        raise ValueError("invalid practice budget")


def _validate_lesson(item: ApprovedLesson) -> None:
    _owner(item.owner)
    if not item.practice_consent:
        raise PermissionError("practice generation requires separate opt-in")
    if not isinstance(item.title, str) or not 2 <= len(item.title.strip()) <= 100:
        raise ValueError("invalid lesson title")
    if not isinstance(item.promotion, PromotionDecision):
        raise ValueError("canonical promotion receipt required")
    decision = item.promotion
    if (not decision.eligible or bool(decision.reasons)
            or not decision.claim_id or len(decision.claim_id) > 256
            or not _fingerprint(decision.evidence_digest)):
        raise PermissionError("only promoted and traceable knowledge may enter practice")
    if not _fingerprint(item.review_fingerprint):
        raise PermissionError("a human review receipt is required")
    if not (1 <= len(item.observed_mechanics) <= 16
            and all(isinstance(m, Mechanic) for m in item.observed_mechanics)
            and len(set(item.observed_mechanics)) == len(item.observed_mechanics)):
        raise ValueError("lesson mechanics must be explicit and unique")


def _choose_mechanics(observed: tuple[Mechanic, ...], kind: str) -> tuple[Mechanic, ...]:
    supported = tuple(sorted((m for m in observed if m in PRACTICE_MECHANICS), key=lambda m: m.value))
    fixed: dict[str, tuple[Mechanic, ...]] = {
        "movement_lab": (Mechanic.MOVEMENT, Mechanic.EXPLORATION),
        "jump_lab": (Mechanic.MOVEMENT, Mechanic.PLATFORMING),
        "exploration_lab": (Mechanic.MOVEMENT, Mechanic.EXPLORATION, Mechanic.LEVEL_DESIGN),
        "physics_lab": (Mechanic.MOVEMENT, Mechanic.PLATFORMING, Mechanic.PHYSICS),
    }
    if kind not in fixed:
        raise ValueError("unsupported game practice kind")
    # A permitted mechanic is drawn from verified lesson observations; movement
    # is a necessary scaffold, not a claim the dragon learned movement.
    selected = tuple(m for m in fixed[kind] if m is Mechanic.MOVEMENT or m in supported)
    return selected or (Mechanic.MOVEMENT,)


def _build_spec(lesson_id: str, title: str, kind: str, observed: tuple[Mechanic, ...],
                ordinal: int) -> GamePrototypeSpec:
    mechanics = _choose_mechanics(observed, kind)
    guides = {
        Mechanic.MOVEMENT: ("Navigate the little world", "Move with A/D or arrows", "Move the sprite", "Movement feedback"),
        Mechanic.PLATFORMING: ("Reach a higher platform", "Jump with Space", "Resolve grounded jumping", "Takeoff and landing"),
        Mechanic.PHYSICS: ("Explore a gravity sandbox", "Jump and fall", "Resolve simple collisions", "Visible gravity"),
        Mechanic.EXPLORATION: ("Find the hidden goal", "Explore the map", "Reveal the goal", "Discovery feedback"),
        Mechanic.LEVEL_DESIGN: ("Read space and pacing", "Traverse platforms", "Follow level geometry", "Readable routes"),
    }
    features = tuple(GameMechanicDesign(m, *guides[m], "Inspect and playtest before promotion")
                     for m in mechanics)
    constraint = GameDesignConstraint(
        genre="original microgame", target_platform="offline HTML",
        accessibility=("keyboard input", "status text"),
        originality_notes=("original geometric assets only", "no copied level layouts"),
        max_complexity=6,
    )
    candidate = _hash([lesson_id, kind, ordinal, [m.value for m in mechanics]])
    return GamePrototypeSpec(candidate, f"{title[:65]} — {kind.replace('_', ' ').title()}",
                             "Practice one mechanic safely. This prototype is an experiment.",
                             features, constraint, lesson_id, True)


class DragonPracticeLab:
    """Owner-scoped durable queue and artifacts; all commands require authorization.

    No daemon is started by constructing this object. The explicit
    run_batch() action enforces per-day caps and per-lesson attempt budgets.
    Failed attempts remain visible and do not award skill XP.
    """

    def __init__(self, db: sqlite3.Connection, policy: PracticePolicy = PracticePolicy()):
        _policy(policy)
        self.db = db
        self.policy = policy
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_practice_lessons(
            owner TEXT NOT NULL, lesson_id TEXT NOT NULL, claim_id TEXT NOT NULL,
            title TEXT NOT NULL, evidence_digest TEXT NOT NULL, review_digest TEXT NOT NULL,
            mechanics_json TEXT NOT NULL, created_at REAL NOT NULL, consent INTEGER NOT NULL,
            PRIMARY KEY(owner,lesson_id), UNIQUE(owner,claim_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_practice_attempts(
            owner TEXT NOT NULL, attempt_id TEXT NOT NULL, lesson_id TEXT NOT NULL,
            kind TEXT NOT NULL, ordinal INTEGER NOT NULL, state TEXT NOT NULL,
            artifact_digest TEXT NOT NULL, artifact_html TEXT NOT NULL,
            supported_json TEXT NOT NULL, deferred_json TEXT NOT NULL,
            created_at REAL NOT NULL, review_digest TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(owner,attempt_id), UNIQUE(owner,lesson_id,ordinal))""")
        db.execute("""CREATE INDEX IF NOT EXISTS dragon_practice_attempt_day
            ON dragon_practice_attempts(owner,created_at)""")
        db.commit()

    def offer(self, lesson: ApprovedLesson, *, authorized: bool, now: float) -> str:
        if not authorized:
            raise PermissionError("practice queue requires authorization")
        _time(now)
        _validate_lesson(lesson)
        decision = lesson.promotion
        # One source claim may improve over time, but may not mint infinite XP
        # through rereads, review receipts, or cosmetic mechanic permutations.
        identity = _hash([lesson.owner, decision.claim_id])
        # Serialize competing offers before the existence check.
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            existing = self.db.execute("""SELECT lesson_id FROM dragon_practice_lessons
                WHERE owner=? AND claim_id=?""", (lesson.owner, decision.claim_id)).fetchone()
            if existing:
                # A new, fully validated approval can re-enable a revoked
                # lesson without inventing another lesson or granting XP.
                self.db.execute("""UPDATE dragon_practice_lessons
                    SET consent=1,title=?,evidence_digest=?,review_digest=?,mechanics_json=?
                    WHERE owner=? AND claim_id=?""",
                    (lesson.title.strip(),decision.evidence_digest,
                     lesson.review_fingerprint,
                     json.dumps([m.value for m in lesson.observed_mechanics]),
                     lesson.owner,decision.claim_id))
                return existing[0]
            count = self.db.execute("SELECT COUNT(*) FROM dragon_practice_lessons WHERE owner=?",
                                    (lesson.owner,)).fetchone()[0]
            if count >= self.policy.max_lessons_per_owner:
                raise ValueError("practice lesson capacity exceeded")
            self.db.execute("""INSERT INTO dragon_practice_lessons VALUES(?,?,?,?,?,?,?,?,?)""",
                            (lesson.owner, identity, decision.claim_id, lesson.title.strip(),
                             decision.evidence_digest, lesson.review_fingerprint,
                             json.dumps([m.value for m in lesson.observed_mechanics]), now, 1))
        return identity

    def revoke(self, owner: str, *, authorized: bool) -> None:
        """Immediately stop new practice; retain existing audit records."""
        _owner(owner)
        if not authorized:
            raise PermissionError("practice revocation requires authorization")
        with self.db:
            self.db.execute("UPDATE dragon_practice_lessons SET consent=0 WHERE owner=?",
                            (owner,))

    def run_batch(self, owner: str, *, authorized: bool, consent: bool, now: float,
                  max_demos: int = 2) -> tuple[PracticeAttempt, ...]:
        """Run bounded, synchronous attempts. Caller controls further scheduling."""
        _owner(owner)
        _time(now)
        if not authorized or not consent:
            raise PermissionError("each practice batch requires current authorization and consent")
        if not isinstance(max_demos, int) or not 1 <= max_demos <= self.policy.max_demos_per_batch:
            raise ValueError("invalid requested practice batch")
        results: list[PracticeAttempt] = []
        day_start = int(now // 86400) * 86400
        for _ in range(max_demos):
            # The budget check and insert are one write-reserved transaction:
            # concurrent workers cannot both consume the final quota slot.
            self.db.execute("BEGIN IMMEDIATE")
            with self.db:
                daily = self.db.execute("""SELECT COUNT(*) FROM dragon_practice_attempts
                    WHERE owner=? AND created_at>=? AND created_at<?""",
                    (owner, day_start, day_start + 86400)).fetchone()[0]
                has_native=self.db.execute("""SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='dragon_native_game_attempts'""").fetchone()
                if has_native:
                    daily+=self.db.execute("""SELECT COUNT(*) FROM dragon_native_game_attempts
                        WHERE owner=? AND created_at>=? AND created_at<?""",
                        (owner,day_start,day_start + 86400)).fetchone()[0]
                if daily >= self.policy.max_demos_per_day:
                    break
                candidates = self.db.execute("""SELECT l.lesson_id,l.title,l.mechanics_json,
                    COUNT(a.attempt_id) AS attempts
                    FROM dragon_practice_lessons l
                    LEFT JOIN dragon_practice_attempts a
                    ON a.owner=l.owner AND a.lesson_id=l.lesson_id
                    WHERE l.owner=? AND l.consent=1
                    GROUP BY l.lesson_id,l.title,l.mechanics_json
                    HAVING COUNT(a.attempt_id)<?
                    ORDER BY attempts,l.created_at,l.lesson_id LIMIT 1""",
                    (owner,self.policy.max_demos_per_lesson)).fetchone()
                if not candidates:
                    break
                lesson_id,title,mechanics_json,ordinal = candidates
                kind = PRACTICE_KINDS[ordinal % len(PRACTICE_KINDS)]
                attempt_id = _hash([owner,lesson_id,ordinal,kind])
                state,artifact_digest,artifact_html,error_code = "built","","",""
                supported: tuple[str,...] = ()
                deferred: tuple[str,...] = ()
                try:
                    spec = _build_spec(lesson_id,title,kind,
                        tuple(Mechanic(m) for m in json.loads(mechanics_json)),ordinal)
                    playable = render_playable_prototype(spec,authorized=True)
                    if (len(playable.html.encode("utf-8")) > self.policy.max_artifact_bytes
                            or not playable.html.startswith("<!doctype html>")
                            or "connect-src 'none'" not in playable.html):
                        raise ValueError("invalid or oversized offline prototype")
                    artifact_html=playable.html
                    artifact_digest=playable.content_digest
                    supported=playable.supported_mechanics
                    deferred=playable.deferred_mechanics
                except (ValueError,TypeError,KeyError):
                    state,error_code="failed","prototype_build_rejected"
                self.db.execute("""INSERT INTO dragon_practice_attempts
                    (owner,attempt_id,lesson_id,kind,ordinal,state,artifact_digest,artifact_html,
                     supported_json,deferred_json,created_at,review_digest,error_code)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,'',?)""",
                    (owner,attempt_id,lesson_id,kind,ordinal,state,artifact_digest,artifact_html,
                     json.dumps(supported),json.dumps(deferred),now,error_code))
                results.append(PracticeAttempt(attempt_id,lesson_id,owner,kind,state,
                    artifact_digest,supported,deferred,now,"",error_code))
        return tuple(results)

    def artifact(self, owner: str, attempt_id: str, *, authorized: bool) -> str:
        _owner(owner)
        if not authorized:
            raise PermissionError("practice artifact requires authorization")
        row=self.db.execute("""SELECT state,artifact_digest,artifact_html
            FROM dragon_practice_attempts WHERE owner=? AND attempt_id=?""",
            (owner,attempt_id)).fetchone()
        if row is None or row[0] not in ("built","reviewed"):
            raise LookupError("practice artifact unavailable")
        if sha256(row[2].encode()).hexdigest()!=row[1]:
            raise ValueError("practice artifact integrity mismatch")
        return row[2]

    def review(self, owner: str, attempt_id: str, *, authorized: bool,
               playtested: bool, playtest_digest: str, accepted: bool) -> bool:
        _owner(owner)
        if not authorized:
            raise PermissionError("practice review requires authorization")
        if not isinstance(playtested,bool) or not isinstance(accepted,bool):
            raise ValueError("invalid review decision")
        if not _fingerprint(playtest_digest):
            raise ValueError("external playtest evidence digest required")
        with self.db:
            row=self.db.execute("""SELECT state,artifact_digest FROM dragon_practice_attempts
                WHERE owner=? AND attempt_id=?""",(owner,attempt_id)).fetchone()
            if row is None or row[0]!="built":
                return False
            verdict="reviewed" if playtested and accepted else "rejected"
            digest=_hash([owner,attempt_id,row[1],playtest_digest,playtested,accepted])
            updated=self.db.execute("""UPDATE dragon_practice_attempts
                SET state=?,review_digest=? WHERE owner=? AND attempt_id=? AND state='built'""",
                (verdict,digest,owner,attempt_id))
            return updated.rowcount==1

    def attempts(self, owner: str, *, authorized: bool,
                 limit: int = 50) -> tuple[PracticeAttempt,...]:
        _owner(owner)
        if not authorized:
            raise PermissionError("practice history requires authorization")
        if not 1 <= limit <= 500:
            raise ValueError("invalid practice history limit")
        rows=self.db.execute("""SELECT attempt_id,lesson_id,kind,state,artifact_digest,
            supported_json,deferred_json,created_at,review_digest,error_code
            FROM dragon_practice_attempts WHERE owner=? ORDER BY created_at DESC,attempt_id
            LIMIT ?""",(owner,limit)).fetchall()
        return tuple(PracticeAttempt(r[0],r[1],owner,r[2],r[3],r[4],
                     tuple(json.loads(r[5])),tuple(json.loads(r[6])),r[7],r[8],r[9]) for r in rows)

    def progress(self, owner: str, *, authorized: bool) -> PracticeProgress:
        _owner(owner)
        if not authorized:
            raise PermissionError("companion progression requires authorization")
        lessons=self.db.execute("""SELECT COUNT(*) FROM dragon_practice_lessons
            WHERE owner=?""",(owner,)).fetchone()[0]
        demos=self.db.execute("""SELECT state,COUNT(*) FROM dragon_practice_attempts
            WHERE owner=? GROUP BY state""",(owner,)).fetchall()
        counts=dict(demos)
        built=counts.get("built",0)+counts.get("reviewed",0)+counts.get("rejected",0)
        reviewed=counts.get("reviewed",0)
        attempts=sum(counts.values())
        # Only approved lessons and externally evidenced, human-reviewed
        # demonstrations contribute to durable capability XP.
        xp=lessons*30+reviewed*55
        level=1
        while xp >= 75*level*(level+1)//2:
            level+=1
        skills={
            "research":min(100,lessons*4),
            "game_design":min(100,reviewed*8),
            "prototyping":min(100,reviewed*8),
            "verification":min(100,reviewed*6),
        }
        unlocked=tuple(name for threshold,name in (
            (1,"little_explorer"),(2,"apprentice_forge"),
            (4,"glasses_scholar"),(7,"winged_builder"),
            (10,"star_cartographer"),(15,"master_game_dragon"))
            if level>=threshold)
        return PracticeProgress(owner,level,xp,75*level*(level+1)//2,
            lessons,built,reviewed,attempts,counts.get("failed",0),skills,unlocked)
