"""Intake questionnaire — twelve beats that vote an era and nudge the cube.

Answers are closed vocabulary. Each option casts an era ballot and a
sparse axis delta. The winner era stamps the tensor; deltas lerp toward
the voted point so a soulslike-with-arcade-pace is a real blend, not a
label.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

from skeleton.context.tensor import AXES, ContextTensor

BEATS: Tuple[Dict[str, Any], ...] = (
    {"id": "pace", "prompt": "How does time feel?",
     "options": {
         "processional": {"era": "soulslike", "axes": {"tempo": 0.35, "grind": 0.8}},
         "frantic": {"era": "boomer_shooter", "axes": {"tempo": 0.95, "spectacle": 0.8}},
         "cabinet": {"era": "arcade_golden_age", "axes": {"tempo": 0.9, "spectacle": 0.85}},
         "unhurried": {"era": "cozy_wholesome", "axes": {"tempo": 0.25, "intimacy": 0.9}},
     }},
    {"id": "death", "prompt": "What does failure cost?",
     "options": {
         "everything": {"era": "soulslike", "axes": {"risk": 0.9, "grind": 0.85}},
         "the_raid": {"era": "extraction_now", "axes": {"risk": 0.85, "scarcity": 0.85}},
         "a_credit": {"era": "arcade_golden_age", "axes": {"risk": 0.55}},
         "nothing": {"era": "cozy_wholesome", "axes": {"risk": 0.1, "lethality": 0.1}},
     }},
    {"id": "combat", "prompt": "How should a trash mob die?",
     "options": {
         "earned": {"era": "soulslike", "axes": {"lethality": 0.9, "agency": 0.6}},
         "instantly": {"era": "boomer_shooter", "axes": {"lethality": 0.85, "tempo": 0.95}},
         "scarcely": {"era": "horror_survival", "axes": {"scarcity": 0.9, "opacity": 0.85}},
         "politely": {"era": "cozy_wholesome", "axes": {"lethality": 0.1, "intimacy": 0.85}},
     }},
    {"id": "info", "prompt": "How much does the world explain itself?",
     "options": {
         "nothing": {"era": "soulslike", "axes": {"opacity": 0.8, "authorial": 0.8}},
         "tactical": {"era": "extraction_now", "axes": {"opacity": 0.5, "agency": 0.8}},
         "cinematic": {"era": "modern_aaa", "axes": {"spectacle": 0.8, "opacity": 0.3}},
         "footnotes": {"era": "indie_experimental", "axes": {"authorial": 0.95, "opacity": 0.6}},
     }},
    {"id": "loot", "prompt": "Is stuff a prize or a liability?",
     "options": {
         "liability": {"era": "extraction_now", "axes": {"scarcity": 0.85, "risk": 0.8}},
         "build": {"era": "soulslike", "axes": {"grind": 0.75}},
         "score": {"era": "arcade_golden_age", "axes": {"spectacle": 0.7}},
         "gift": {"era": "cozy_wholesome", "axes": {"intimacy": 0.8, "scarcity": 0.15}},
     }},
    {"id": "heat", "prompt": "Does the gun fight the shooter?",
     "options": {
         "yes": {"era": "extraction_now", "axes": {"risk": 0.8, "agency": 0.75}},
         "stamina": {"era": "soulslike", "axes": {"grind": 0.7, "agency": 0.55}},
         "no": {"era": "boomer_shooter", "axes": {"tempo": 0.9, "agency": 0.9}},
         "never": {"era": "cozy_wholesome", "axes": {"risk": 0.1}},
     }},
    {"id": "author", "prompt": "Whose taste is this?",
     "options": {
         "mine": {"era": "indie_experimental", "axes": {"authorial": 0.95, "agency": 0.85}},
         "the_studio": {"era": "modern_aaa", "axes": {"spectacle": 0.75, "authorial": 0.3}},
         "the_cabinet": {"era": "arcade_golden_age", "axes": {"authorial": 0.25, "spectacle": 0.85}},
         "the_dark": {"era": "horror_survival", "axes": {"authorial": 0.7, "opacity": 0.85}},
     }},
    {"id": "social", "prompt": "Alone or extracted together?",
     "options": {
         "solo": {"era": "soulslike", "axes": {"intimacy": 0.4, "agency": 0.7}},
         "squad": {"era": "extraction_now", "axes": {"agency": 0.75, "risk": 0.8}},
         "leaderboard": {"era": "arcade_golden_age", "axes": {"spectacle": 0.8}},
         "kitchen": {"era": "cozy_wholesome", "axes": {"intimacy": 0.95}},
     }},
    {"id": "space", "prompt": "What is the room?",
     "options": {
         "arena": {"era": "boomer_shooter", "axes": {"tempo": 0.9, "spectacle": 0.7}},
         "dungeon": {"era": "soulslike", "axes": {"opacity": 0.65, "grind": 0.7}},
         "facility": {"era": "extraction_now", "axes": {"scarcity": 0.75, "risk": 0.75}},
         "garden": {"era": "cozy_wholesome", "axes": {"intimacy": 0.85, "tempo": 0.3}},
     }},
    {"id": "fail_state", "prompt": "How does a run end badly?",
     "options": {
         "collapse": {"era": "extraction_now", "axes": {"risk": 0.85}},
         "bonfire": {"era": "soulslike", "axes": {"grind": 0.8, "risk": 0.85}},
         "game_over": {"era": "arcade_golden_age", "axes": {"risk": 0.6, "spectacle": 0.7}},
         "it_doesnt": {"era": "cozy_wholesome", "axes": {"risk": 0.05}},
     }},
    {"id": "ai", "prompt": "What should Jeeves be?",
     "options": {
         "tactical": {"era": "extraction_now", "axes": {"agency": 0.8}},
         "silent": {"era": "soulslike", "axes": {"opacity": 0.75, "authorial": 0.8}},
         "hype": {"era": "boomer_shooter", "axes": {"spectacle": 0.8, "tempo": 0.9}},
         "kind": {"era": "cozy_wholesome", "axes": {"intimacy": 0.9}},
     }},
    {"id": "era_explicit", "prompt": "If you already know the dialect?",
     "options": {
         "extraction_now": {"era": "extraction_now", "axes": {}},
         "soulslike": {"era": "soulslike", "axes": {}},
         "boomer_shooter": {"era": "boomer_shooter", "axes": {}},
         "unspecified": {"era": "extraction_now", "axes": {}},
     }},
)


@dataclass
class Intake:
    era: str
    tensor: ContextTensor
    ballots: Dict[str, int]
    vision: str
    answers: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "era": self.era,
            "tensor": self.tensor.to_dict(),
            "ballots": self.ballots,
            "vision": self.vision,
            "answers": dict(self.answers),
        }


def intake(answers: Mapping[str, str]) -> Intake:
    ballots: Dict[str, int] = {}
    axis_acc = {a: [] for a in AXES}  # type: Dict[str, List[float]]
    used = {}
    phrases = []
    for beat in BEATS:
        raw = answers.get(beat["id"])
        if raw not in beat["options"]:
            continue
        opt = beat["options"][raw]
        used[beat["id"]] = raw
        era = opt["era"]
        ballots[era] = ballots.get(era, 0) + 1
        phrases.append(f"{beat['id']}={raw}")
        for axis, val in (opt.get("axes") or {}).items():
            axis_acc[axis].append(float(val))
    if not ballots:
        era = "extraction_now"
    else:
        era = max(ballots, key=lambda e: (ballots[e], e))
    base = ContextTensor.from_era(era)
    values = []
    for i, axis in enumerate(AXES):
        if axis_acc[axis]:
            voted = sum(axis_acc[axis]) / len(axis_acc[axis])
            values.append(base.values[i] * 0.4 + voted * 0.6)
        else:
            values.append(base.values[i])
    tensor = ContextTensor(tuple(values), era=era)
    vision = "intake " + "; ".join(phrases) + f" => {era}"
    return Intake(era=era, tensor=tensor, ballots=ballots, vision=vision, answers=used)


# Aliases kept for callers that imported the Sep-6 stub names.
IntakeResult = Intake


class Questionnaire:
    """Thin interactive wrapper over the twelve-beat intake."""

    QUESTIONS = [{"id": b["id"], "question": b["prompt"], "options": list(b["options"])} for b in BEATS]

    def __init__(self) -> None:
        self.answers: Dict[str, Any] = {}

    def ask(self, question_id: str, answer: Any) -> None:
        self.answers[question_id] = answer

    def complete(self) -> Intake:
        return intake(self.answers)

    def progress(self) -> Dict[str, Any]:
        answered = set(self.answers.keys())
        total = len(self.QUESTIONS)
        return {
            "answered": len(answered),
            "total": total,
            "remaining": [q["id"] for q in self.QUESTIONS if q["id"] not in answered],
            "complete": len(answered) >= total,
        }
