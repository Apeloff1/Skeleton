"""Salon — conversation choreography for the Skeleton AI chat.

The turn runtime journals what happened. The stream plane resumes it.
This organ decides how a turn is *felt*: presence, ingress, stance,
body, an impromptu adage, a callback to an earlier motif, and an open
hand back to the person. A reply blob is not a conversation.

Law
- stored_prose = 0 on every card. User text is hashed, never copied
  into the salon ledger.
- Deterministic given (thread_id, turn_index, policy, act, motif set).
- Does not commit transcript state. production_authority is always false.
- Does not replace turn_runtime, streaming, or response_acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Iterable, Mapping, Sequence


SALON_SCHEMA_VERSION = 1
SALON_LAW = "salon-choreography-v1"
SALON_CITATION = "skeleton://ai/assistant/salon"


class SalonError(ValueError):
    """Salon input violated the conversation contract."""


class DiscourseAct(str, Enum):
    GREETING = "greeting"
    FAREWELL = "farewell"
    ASK = "ask"
    ASSERT = "assert"
    REPAIR = "repair"
    CHALLENGE = "challenge"
    ASIDE = "aside"
    CONTINUE = "continue"
    AFFECT = "affect"


class Affect(str, Enum):
    NEUTRAL = "neutral"
    PRECISE = "precise"
    HEATED = "heated"
    PLAYFUL = "playful"
    WEARY = "weary"


class BeatKind(str, Enum):
    PRESENCE = "presence"
    INGRESS = "ingress"
    STANCE = "stance"
    BODY = "body"
    ADAGE = "adage"
    CALLBACK = "callback"
    OPEN_HAND = "open_hand"
    SEAL = "seal"


class PresenceLamp(str, Enum):
    IDLE = "idle"
    HEARING = "hearing"
    COMPOSING = "composing"
    ADAGE = "adage"
    SEALED = "sealed"
    INTERRUPTED = "interrupted"


class Reaction(str, Enum):
    QUIETER = "quieter"
    MORE_PLAY = "more_play"
    PIN = "pin"
    FORK = "fork"
    HOLD = "hold"


_TOKEN = re.compile(r"[a-z0-9]{3,}")
_QUESTION = re.compile(r"\?\s*$")
_GREET = re.compile(r"^(hi|hey|hello|yo|good morning|good evening|hei|hallo)\b")
_BYE = re.compile(r"\b(bye|goodbye|good night|later|that's all|thats all)\b")
_REPAIR = re.compile(r"\b(no,|not that|i meant|wrong|again|retry|redo)\b")
_CHALLENGE = re.compile(r"\b(prove|wrong|disagree|actually|source|cite)\b")
_AFFECT = re.compile(r"\b(tired|frustrated|love this|hate|annoyed|glad)\b")


def _digest(payload: object) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _pointer(text: str) -> str:
    folded = " ".join(text.lower().split())
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(_TOKEN.findall(text.lower()))))


class SalonPolicy:
    """Cadence and adage budget. Reduced motion collapses waits to zero."""

    def __init__(
        self,
        *,
        adage_gap: int = 2,
        max_open_hands: int = 1,
        reduced_motion: bool = False,
        play_bias: float = 0.35,
        allow_adage_on_repair: bool = False,
        cadence_scale: float = 1.0,
    ) -> None:
        if isinstance(adage_gap, bool) or not isinstance(adage_gap, int) or adage_gap < 0:
            raise SalonError("adage_gap must be a non-negative integer")
        if isinstance(max_open_hands, bool) or not isinstance(max_open_hands, int):
            raise SalonError("max_open_hands must be an integer")
        if max_open_hands < 0 or max_open_hands > 2:
            raise SalonError("max_open_hands must be 0, 1, or 2")
        if not isinstance(reduced_motion, bool):
            raise SalonError("reduced_motion must be boolean")
        if isinstance(play_bias, bool) or not isinstance(play_bias, (int, float)):
            raise SalonError("play_bias must be numeric")
        if not 0.0 <= float(play_bias) <= 1.0:
            raise SalonError("play_bias must be in [0, 1]")
        if isinstance(cadence_scale, bool) or not isinstance(cadence_scale, (int, float)):
            raise SalonError("cadence_scale must be numeric")
        if not 0.0 <= float(cadence_scale) <= 3.0:
            raise SalonError("cadence_scale must be in [0, 3]")
        self.adage_gap = adage_gap
        self.max_open_hands = max_open_hands
        self.reduced_motion = reduced_motion
        self.play_bias = float(play_bias)
        self.allow_adage_on_repair = bool(allow_adage_on_repair)
        self.cadence_scale = float(cadence_scale)

    def as_dict(self) -> dict[str, object]:
        return {
            "adage_gap": self.adage_gap,
            "max_open_hands": self.max_open_hands,
            "reduced_motion": self.reduced_motion,
            "play_bias": self.play_bias,
            "allow_adage_on_repair": self.allow_adage_on_repair,
            "cadence_scale": self.cadence_scale,
        }


@dataclass(frozen=True, slots=True)
class Motif:
    motif_id: str
    topic_pointer: str
    act: DiscourseAct
    turn_index: int
    token_hashes: tuple[str, ...] = ()
    pinned: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "motif_id": self.motif_id,
            "topic_pointer": self.topic_pointer,
            "act": self.act.value,
            "turn_index": self.turn_index,
            "token_hashes": list(self.token_hashes),
            "pinned": self.pinned,
        }


@dataclass(frozen=True, slots=True)
class CitationChip:
    chip_id: str
    label: str
    url: str

    def __post_init__(self) -> None:
        if not self.chip_id or not self.label or not self.url:
            raise SalonError("citation chip requires id, label, url")
        if len(self.label) > 80:
            raise SalonError("citation label exceeds 80")

    def as_dict(self) -> dict[str, str]:
        return {"chip_id": self.chip_id, "label": self.label, "url": self.url}


@dataclass(frozen=True, slots=True)
class SalonBeat:
    seq: int
    kind: BeatKind
    text: str
    cadence_ms: int
    interruptible: bool
    lamp: PresenceLamp
    affordances: tuple[str, ...]
    chips: tuple[CitationChip, ...] = ()
    motif_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "kind": self.kind.value,
            "text": self.text,
            "cadence_ms": self.cadence_ms,
            "interruptible": self.interruptible,
            "lamp": self.lamp.value,
            "affordances": list(self.affordances),
            "chips": [chip.as_dict() for chip in self.chips],
            "motif_id": self.motif_id,
            "schema_version": SALON_SCHEMA_VERSION,
            "stored_prose": 0,
        }


@dataclass(frozen=True, slots=True)
class SalonCard:
    kind: str
    hit: bool
    law: str
    citation: str
    stored_prose: int
    thread_pointer: str
    turn_index: int
    act: str
    affect: str
    lamp: str
    beat_count: int
    adage_fired: bool
    callback_motif: str | None
    digest: str
    production_authority: bool = False

    def as_dict(self) -> dict[str, object]:
        if self.stored_prose != 0:
            raise SalonError("salon card stored_prose must be 0")
        if self.production_authority is not False:
            raise SalonError("salon cannot commit transcript state")
        return {
            "kind": self.kind,
            "hit": self.hit,
            "law": self.law,
            "citation": self.citation,
            "stored_prose": 0,
            "thread_pointer": self.thread_pointer,
            "turn_index": self.turn_index,
            "act": self.act,
            "affect": self.affect,
            "lamp": self.lamp,
            "beat_count": self.beat_count,
            "adage_fired": self.adage_fired,
            "callback_motif": self.callback_motif,
            "digest": self.digest,
            "production_authority": False,
        }


@dataclass
class SalonPlan:
    beats: tuple[SalonBeat, ...]
    card: SalonCard
    user_pointer: str
    interrupted_at: int | None = None

    def visible(self) -> tuple[SalonBeat, ...]:
        if self.interrupted_at is None:
            return self.beats
        return tuple(beat for beat in self.beats if beat.seq <= self.interrupted_at)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SALON_SCHEMA_VERSION,
            "beats": [beat.as_dict() for beat in self.visible()],
            "card": self.card.as_dict(),
            "user_pointer": self.user_pointer,
            "interrupted_at": self.interrupted_at,
            "stored_prose": 0,
        }


# House lines. These are generated voice, not user transcript.
_INGRESS = {
    DiscourseAct.GREETING: "Here. The room is open.",
    DiscourseAct.FAREWELL: "I'll close the lamp after this.",
    DiscourseAct.ASK: "Heard. Holding the question before I answer it.",
    DiscourseAct.ASSERT: "Taken. I'll answer the claim, not talk past it.",
    DiscourseAct.REPAIR: "Reset. Previous cut discarded.",
    DiscourseAct.CHALLENGE: "Fair. I'll show the seam, not the flourish.",
    DiscourseAct.ASIDE: "Side door. We can come back.",
    DiscourseAct.CONTINUE: "Still on the same thread.",
    DiscourseAct.AFFECT: "Noted the weather. The work stays.",
}

_STANCE = {
    Affect.NEUTRAL: "Straight answer, then one open hand.",
    Affect.PRECISE: "Tight. Names, cuts, no ornament unless you ask.",
    Affect.HEATED: "Shorter sentences. No lecture.",
    Affect.PLAYFUL: "I'll keep the spine and allow one aside.",
    Affect.WEARY: "Low lamp. Only what moves the work.",
}

_ADAGES = (
    "A chat that only answers is a filing cabinet with better lighting.",
    "The aside is the part that proves someone is in the room.",
    "Cadence is courtesy. Silence between beats is not lag.",
    "Pin the motif. The thread remembers the hash, not the sentence.",
    "If the lamp is heated, the adage waits. Heat is not a stage.",
    "Fork when the room splits. Do not pretend it is still one talk.",
    "An open hand is a question you can refuse. That is the point.",
    "October light: gold on charcoal, never a blank white bubble.",
)

_OPEN = {
    DiscourseAct.GREETING: "What are we actually building in this sitting?",
    DiscourseAct.ASK: "Want the short cut, or the seam underneath?",
    DiscourseAct.ASSERT: "Should I pressure-test that, or take it as given?",
    DiscourseAct.CHALLENGE: "Which claim should I put on the table first?",
    DiscourseAct.CONTINUE: "Same depth, or do we narrow?",
    DiscourseAct.ASIDE: "Park this, or let it become the main thread?",
    DiscourseAct.AFFECT: "Stay on the work, or name the weather first?",
    DiscourseAct.REPAIR: "What should the redo keep?",
    DiscourseAct.FAREWELL: "Leave a pin on the last motif?",
}


def classify_act(text: str) -> DiscourseAct:
    folded = " ".join(text.lower().split())
    if not folded:
        raise SalonError("empty turn")
    if _GREET.match(folded):
        return DiscourseAct.GREETING
    if _BYE.search(folded):
        return DiscourseAct.FAREWELL
    if _REPAIR.search(folded):
        return DiscourseAct.REPAIR
    if _CHALLENGE.search(folded):
        return DiscourseAct.CHALLENGE
    if _AFFECT.search(folded):
        return DiscourseAct.AFFECT
    if folded.startswith("(") or folded.startswith("aside"):
        return DiscourseAct.ASIDE
    if _QUESTION.search(folded) or folded.startswith(("how", "why", "what", "when", "where", "who", "can ", "should ")):
        return DiscourseAct.ASK
    if folded.startswith(("also", "and", "continue", "go on", "more")):
        return DiscourseAct.CONTINUE
    return DiscourseAct.ASSERT


def classify_affect(text: str, act: DiscourseAct) -> Affect:
    folded = text.lower()
    if any(word in folded for word in ("exactly", "precise", "spec", "contract", "invariant")):
        return Affect.PRECISE
    if any(word in folded for word in ("furious", "annoyed", "hate", "useless", "again")):
        return Affect.HEATED
    if any(word in folded for word in ("tired", "later", "weary", "enough")):
        return Affect.WEARY
    if act is DiscourseAct.ASIDE or any(word in folded for word in ("haha", "joke", "play", "witty")):
        return Affect.PLAYFUL
    return Affect.NEUTRAL


def _pick(seed: str, pool: Sequence[str]) -> str:
    if not pool:
        raise SalonError("empty voice pool")
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return pool[digest[0] % len(pool)]


def _cadence(kind: BeatKind, policy: SalonPolicy, affect: Affect) -> int:
    base = {
        BeatKind.PRESENCE: 80,
        BeatKind.INGRESS: 220,
        BeatKind.STANCE: 180,
        BeatKind.BODY: 40,
        BeatKind.ADAGE: 460,
        BeatKind.CALLBACK: 280,
        BeatKind.OPEN_HAND: 240,
        BeatKind.SEAL: 60,
    }[kind]
    if affect is Affect.HEATED:
        base = int(base * 0.6)
    if affect is Affect.WEARY:
        base = int(base * 0.75)
    scaled = int(base * policy.cadence_scale)
    if policy.reduced_motion:
        return 0
    return max(0, scaled)


class SalonSession:
    """One thread's conversation weather. Pointers only."""

    def __init__(
        self,
        thread_id: str,
        *,
        policy: SalonPolicy | None = None,
    ) -> None:
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise SalonError("thread_id required")
        self.thread_id = thread_id.strip()
        self.policy = policy or SalonPolicy()
        self.turn_index = 0
        self.motifs: list[Motif] = []
        self.turns_since_adage = 0
        self.interruptions = 0
        self.pins: set[str] = set()
        self.lamp = PresenceLamp.IDLE
        self._last_plan: SalonPlan | None = None

    def hear_pointer(self, user_text: str) -> str:
        if not isinstance(user_text, str) or not user_text.strip():
            raise SalonError("user turn required")
        return _pointer(user_text)

    def compose(
        self,
        user_text: str,
        *,
        body: str | None = None,
        chips: Iterable[CitationChip] | None = None,
    ) -> SalonPlan:
        act = classify_act(user_text)
        affect = classify_affect(user_text, act)
        if self.policy.play_bias >= 0.8 and affect is Affect.NEUTRAL:
            affect = Affect.PLAYFUL
        pointer = self.hear_pointer(user_text)
        topic = _tokens(user_text)[:6]
        token_hashes = tuple(_pointer(token)[:12] for token in topic)
        motif = Motif(
            motif_id=_digest({"thread": self.thread_id, "topic": topic, "act": act.value})[:16],
            topic_pointer=_digest({"topic": topic}),
            act=act,
            turn_index=self.turn_index,
            token_hashes=token_hashes,
        )
        self.motifs.append(motif)
        chip_tuple = tuple(chips or ())
        for chip in chip_tuple:
            if not isinstance(chip, CitationChip):
                raise SalonError("chips must be CitationChip")

        beats: list[SalonBeat] = []
        seq = 0

        def push(
            kind: BeatKind,
            text: str,
            lamp: PresenceLamp,
            *,
            interruptible: bool = True,
            beat_chips: tuple[CitationChip, ...] = (),
            motif_id: str | None = None,
        ) -> None:
            nonlocal seq
            beats.append(
                SalonBeat(
                    seq=seq,
                    kind=kind,
                    text=text,
                    cadence_ms=_cadence(kind, self.policy, affect),
                    interruptible=interruptible,
                    lamp=lamp,
                    affordances=("quieter", "more_play", "pin", "fork", "hold"),
                    chips=beat_chips,
                    motif_id=motif_id,
                )
            )
            seq += 1

        push(BeatKind.PRESENCE, "lamp:hearing", PresenceLamp.HEARING, interruptible=False)
        push(BeatKind.INGRESS, _INGRESS[act], PresenceLamp.COMPOSING)
        push(BeatKind.STANCE, _STANCE[affect], PresenceLamp.COMPOSING)

        body_text = (body or "").strip()
        if body_text:
            push(
                BeatKind.BODY,
                body_text,
                PresenceLamp.COMPOSING,
                beat_chips=chip_tuple,
            )
        else:
            push(
                BeatKind.BODY,
                "The answer slot is still open. I will not invent the work.",
                PresenceLamp.COMPOSING,
            )

        adage_fired = False
        repair_block = act is DiscourseAct.REPAIR and not self.policy.allow_adage_on_repair
        heat_block = affect is Affect.HEATED
        if (
            not repair_block
            and not heat_block
            and self.turns_since_adage >= self.policy.adage_gap
            and act is not DiscourseAct.FAREWELL
        ):
            line = _pick(
                f"{self.thread_id}:{self.turn_index}:{act.value}",
                _ADAGES,
            )
            push(BeatKind.ADAGE, line, PresenceLamp.ADAGE, motif_id=motif.motif_id)
            adage_fired = True
            self.turns_since_adage = 0
        else:
            self.turns_since_adage += 1

        callback_id = self._callback_target(motif)
        if callback_id is not None:
            push(
                BeatKind.CALLBACK,
                f"Callback to motif {callback_id}. Same grain, earlier cut.",
                PresenceLamp.COMPOSING,
                motif_id=callback_id,
            )

        if self.policy.max_open_hands and act is not DiscourseAct.FAREWELL:
            push(BeatKind.OPEN_HAND, _OPEN[act], PresenceLamp.COMPOSING)

        push(BeatKind.SEAL, "composer:rearm", PresenceLamp.SEALED, interruptible=False)

        card = SalonCard(
            kind="salon.turn",
            hit=True,
            law=SALON_LAW,
            citation=SALON_CITATION,
            stored_prose=0,
            thread_pointer=_pointer(self.thread_id),
            turn_index=self.turn_index,
            act=act.value,
            affect=affect.value,
            lamp=PresenceLamp.SEALED.value,
            beat_count=len(beats),
            adage_fired=adage_fired,
            callback_motif=callback_id,
            digest="",
        )
        card = SalonCard(
            kind=card.kind,
            hit=card.hit,
            law=card.law,
            citation=card.citation,
            stored_prose=0,
            thread_pointer=card.thread_pointer,
            turn_index=card.turn_index,
            act=card.act,
            affect=card.affect,
            lamp=card.lamp,
            beat_count=card.beat_count,
            adage_fired=card.adage_fired,
            callback_motif=card.callback_motif,
            digest=_digest(
                {
                    "beats": [beat.as_dict() for beat in beats],
                    "act": act.value,
                    "affect": affect.value,
                    "turn": self.turn_index,
                }
            ),
        )
        plan = SalonPlan(beats=tuple(beats), card=card, user_pointer=pointer)
        self._last_plan = plan
        self.turn_index += 1
        self.lamp = PresenceLamp.SEALED
        return plan

    def _callback_target(self, current: Motif) -> str | None:
        current_set = set(current.token_hashes)
        for prior in reversed(self.motifs[:-1]):
            if prior.pinned:
                return prior.motif_id
            if prior.topic_pointer == current.topic_pointer and prior.motif_id != current.motif_id:
                return prior.motif_id
            overlap = current_set.intersection(prior.token_hashes)
            if len(overlap) >= 2:
                return prior.motif_id
        return None

    def interrupt(self, at_seq: int) -> SalonPlan:
        if self._last_plan is None:
            raise SalonError("nothing to interrupt")
        if isinstance(at_seq, bool) or not isinstance(at_seq, int) or at_seq < 0:
            raise SalonError("at_seq must be a non-negative integer")
        if at_seq >= len(self._last_plan.beats):
            raise SalonError("interrupt seq past plan")
        beat = self._last_plan.beats[at_seq]
        if not beat.interruptible:
            raise SalonError("beat is not interruptible")
        self._last_plan.interrupted_at = at_seq
        self.interruptions += 1
        self.lamp = PresenceLamp.INTERRUPTED
        return self._last_plan

    def react(self, reaction: Reaction | str) -> SalonPolicy:
        try:
            verb = Reaction(reaction)
        except ValueError as exc:
            raise SalonError("unknown reaction") from exc
        policy = self.policy
        if verb is Reaction.QUIETER:
            self.policy = SalonPolicy(
                adage_gap=min(8, policy.adage_gap + 2),
                max_open_hands=0,
                reduced_motion=policy.reduced_motion,
                play_bias=max(0.0, policy.play_bias - 0.25),
                allow_adage_on_repair=policy.allow_adage_on_repair,
                cadence_scale=max(0.4, policy.cadence_scale * 0.8),
            )
        elif verb is Reaction.MORE_PLAY:
            self.policy = SalonPolicy(
                adage_gap=max(0, policy.adage_gap - 1),
                max_open_hands=min(2, policy.max_open_hands + 1),
                reduced_motion=policy.reduced_motion,
                play_bias=min(1.0, policy.play_bias + 0.25),
                allow_adage_on_repair=policy.allow_adage_on_repair,
                cadence_scale=min(2.0, policy.cadence_scale * 1.1),
            )
        elif verb is Reaction.PIN:
            if self.motifs:
                self.pins.add(self.motifs[-1].motif_id)
                last = self.motifs[-1]
                self.motifs[-1] = Motif(
                    motif_id=last.motif_id,
                    topic_pointer=last.topic_pointer,
                    act=last.act,
                    turn_index=last.turn_index,
                    token_hashes=last.token_hashes,
                    pinned=True,
                )
        elif verb is Reaction.FORK:
            self.thread_id = f"{self.thread_id}#fork-{self.turn_index}"
        elif verb is Reaction.HOLD:
            self.lamp = PresenceLamp.IDLE
        return self.policy

    def ledger(self) -> dict[str, object]:
        return {
            "kind": "salon.ledger",
            "hit": True,
            "law": SALON_LAW,
            "citation": SALON_CITATION,
            "stored_prose": 0,
            "thread_pointer": _pointer(self.thread_id),
            "turn_index": self.turn_index,
            "interruptions": self.interruptions,
            "pins": sorted(self.pins),
            "motifs": [motif.as_dict() for motif in self.motifs],
            "lamp": self.lamp.value,
            "production_authority": False,
        }


def surface_contract() -> dict[str, object]:
    """Client contract for the October 2026 salon surface."""
    return {
        "schema_version": SALON_SCHEMA_VERSION,
        "law": SALON_LAW,
        "stored_prose": 0,
        "composer": {
            "verbs": ["quieter", "more_play", "pin", "fork", "hold"],
            "slash": ["/quiet", "/play", "/pin", "/fork", "/hold"],
            "rearm_on": "seal",
            "max_chars": 8000,
        },
        "presence": [lamp.value for lamp in PresenceLamp],
        "beats": [kind.value for kind in BeatKind],
        "motion": {
            "reduced_motion_collapses_cadence": True,
            "interrupt_cancels_tail": True,
            "focus_returns_to_composer": True,
        },
        "citation_chips": True,
        "production_authority": False,
    }


__all__ = [
    "SALON_CITATION",
    "SALON_LAW",
    "SALON_SCHEMA_VERSION",
    "Affect",
    "BeatKind",
    "CitationChip",
    "DiscourseAct",
    "Motif",
    "PresenceLamp",
    "Reaction",
    "SalonBeat",
    "SalonCard",
    "SalonError",
    "SalonPlan",
    "SalonPolicy",
    "SalonSession",
    "classify_act",
    "classify_affect",
    "surface_contract",
]
