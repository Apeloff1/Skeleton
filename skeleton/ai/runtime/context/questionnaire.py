"""Intake questionnaire — twelve beats that vote an era and nudge the cube.

Answers are closed vocabulary. Each option casts an era ballot and a
sparse axis delta. The winner era stamps the tensor; deltas lerp toward
the voted point so a soulslike-with-arcade-pace is a real blend, not a
label.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    # Creative-brief facets (genre/theme/perspective/combat/progression).
    # Defaulted so positional and keyword construction stay compatible.
    genre: str = ""
    theme: str = ""
    perspective: str = ""
    setting: str = ""
    brief: Dict[str, str] = field(default_factory=dict)
    brief_ballots: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "era": self.era,
            "tensor": self.tensor.to_dict(),
            "ballots": self.ballots,
            "vision": self.vision,
            "answers": dict(self.answers),
        }
        if self.brief:
            out.update({
                "genre": self.genre,
                "theme": self.theme,
                "perspective": self.perspective,
                "setting": self.setting,
                "brief": dict(self.brief),
                "brief_ballots": dict(self.brief_ballots),
            })
        return out


def intake(answers: Mapping[str, str]) -> Intake:
    """Vote an era from the twelve beats; fall back to the creative brief.

    Beat answers (``pace``, ``death``, ...) are authoritative. When none are
    present but creative-brief facets are (``genre``, ``theme``,
    ``perspective``, ``combat``, ``progression``), the brief votes a
    canonical era instead of silently collapsing to ``extraction_now``.
    Brief facets are always carried on the result for downstream titling,
    NPC seeding and animation.
    """
    if not isinstance(answers, Mapping):
        raise TypeError("intake answers must be a mapping")
    brief = normalise_brief(answers)
    has_beats = any(answers.get(b["id"]) in b["options"] for b in BEATS)
    if brief and not has_beats:
        return _brief_intake(brief)
    result = _beat_intake(answers)
    if brief:
        result.genre = brief.get("genre", "")
        result.theme = brief.get("theme", "")
        result.perspective = brief.get("perspective", "")
        result.setting = BRIEF_SETTINGS.get(result.theme, "")
        result.brief = dict(brief)
    return result


def _beat_intake(answers: Mapping[str, str]) -> Intake:
    ballots: Dict[str, int] = {}
    axis_acc: Dict[str, List[float]] = {a: [] for a in AXES}
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


# ---------------------------------------------------------------------------
# Creative brief — the five-facet questionnaire used by ``GameForge.run``.
# ---------------------------------------------------------------------------

BRIEF_FACETS: Tuple[str, ...] = ("genre", "theme", "perspective", "combat", "progression")
BRIEF_MAX_CHARS = 48

# Facet weight: genre is the strongest dialect signal, perspective the weakest.
BRIEF_WEIGHTS: Dict[str, float] = {
    "genre": 2.0,
    "theme": 1.0,
    "combat": 1.0,
    "progression": 1.0,
    "perspective": 0.5,
}

# Every target below must be a canonical era id (see forge.eras.list_eras);
# ``test_questionnaire_brief`` pins that invariant.
BRIEF_ERA_VOTES: Dict[str, Dict[str, str]] = {
    "genre": {
        "action-adventure": "modern_aaa", "action": "modern_aaa", "adventure": "modern_aaa",
        "rpg": "crpg", "crpg": "crpg", "jrpg": "jrpg", "arpg": "soulslike",
        "soulslike": "soulslike", "strategy": "grand_strategy", "rts": "grand_strategy",
        "tactics": "tactics_grid", "platformer": "metroidvania", "metroidvania": "metroidvania",
        "simulation": "city_builder", "city-builder": "city_builder", "shooter": "boomer_shooter",
        "fps": "boomer_shooter", "horror": "horror_survival", "survival": "extraction_now",
        "extraction": "extraction_now", "roguelike": "roguelike", "roguelite": "roguelike",
        "stealth": "stealth", "immersive-sim": "immersive_sim", "fighting": "fighting_game",
        "puzzle": "indie_experimental", "deckbuilder": "deckbuilder", "card": "deckbuilder",
        "battle-royale": "battle_royale", "mmo": "mmorpg", "mmorpg": "mmorpg",
        "visual-novel": "visual_novel", "narrative": "walking_sim", "cozy": "cozy_wholesome",
        "arcade": "arcade_golden_age", "bullet-heaven": "bullet_heaven",
    },
    "theme": {
        "sci-fi": "extraction_now", "fantasy": "crpg", "dark-fantasy": "soulslike",
        "modern": "modern_aaa", "post-apocalyptic": "extraction_now", "cyberpunk": "immersive_sim",
        "horror": "horror_survival", "cozy": "cozy_wholesome", "retro": "arcade_golden_age",
        "historical": "grand_strategy", "anime": "jrpg", "noir": "stealth",
    },
    "combat": {
        "tactical": "extraction_now", "real-time": "modern_aaa", "turn-based": "tactics_grid",
        "none": "walking_sim", "puzzle-based": "indie_experimental", "melee": "soulslike",
        "fast": "boomer_shooter", "stealth": "stealth", "card-based": "deckbuilder",
    },
    "progression": {
        "skill-tree": "crpg", "level-based": "jrpg", "equipment": "extraction_now",
        "narrative": "visual_novel", "open-ended": "immersive_sim", "permadeath": "roguelike",
        "metroidvania": "metroidvania", "score": "arcade_golden_age",
    },
    "perspective": {
        "first-person": "immersive_sim", "third-person": "modern_aaa", "top-down": "roguelike",
        "isometric": "crpg", "side-scrolling": "metroidvania", "2d": "metroidvania",
    },
}

# Narrative setting label per theme (descriptive, never used as an era id).
BRIEF_SETTINGS: Dict[str, str] = {
    "sci-fi": "far_future", "fantasy": "medieval_fantasy", "dark-fantasy": "gothic_fantasy",
    "modern": "contemporary", "post-apocalyptic": "wasteland", "cyberpunk": "neon_dystopia",
    "horror": "dread", "cozy": "hearth", "retro": "arcade_cabinet", "historical": "period",
    "anime": "stylised", "noir": "rain_city",
}

BRIEF_DEFAULTS: Dict[str, str] = {
    "genre": "action-adventure",
    "theme": "sci-fi",
    "perspective": "third-person",
    "combat": "tactical",
    "progression": "skill-tree",
}


def _norm_token(value: Any) -> str:
    text = str(value).strip().lower()
    text = "".join(ch if ch.isalnum() else "-" for ch in text)
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")[:BRIEF_MAX_CHARS]


def normalise_brief(answers: Mapping[str, Any]) -> Dict[str, str]:
    """Return the non-empty, normalised creative-brief facets in ``answers``.

    Values are lower-cased, non-alphanumerics collapse to ``-`` and length is
    bounded, so free text cannot inject structure into the vision string.
    """
    out: Dict[str, str] = {}
    beat_options = {b["id"]: b["options"] for b in BEATS}
    for facet in BRIEF_FACETS:
        raw = answers.get(facet)
        if raw is None or isinstance(raw, (dict, list, tuple, set)):
            continue
        if raw in beat_options.get(facet, ()):
            # ``combat`` is also a beat id: a closed-vocabulary beat answer
            # ("earned", "instantly", ...) belongs to the beat vote, not the brief.
            continue
        token = _norm_token(raw)
        if token:
            out[facet] = token
    return out


def brief_ballots(brief: Mapping[str, str]) -> Dict[str, float]:
    """Weighted era ballots cast by the known facet values in ``brief``."""
    ballots: Dict[str, float] = {}
    for facet in BRIEF_FACETS:
        value = brief.get(facet)
        era = BRIEF_ERA_VOTES[facet].get(value or "")
        if era:
            ballots[era] = ballots.get(era, 0.0) + BRIEF_WEIGHTS[facet]
    return ballots


def _brief_vision(brief: Mapping[str, str]) -> str:
    def human(facet: str) -> str:
        value = brief.get(facet, BRIEF_DEFAULTS[facet])
        # Genre/theme keep their hyphenated dialect ("action-adventure",
        # "sci-fi"); mechanical facets read as prose ("turn based").
        return value if facet in {"genre", "theme"} else value.replace("-", " ")

    def article(word: str) -> str:
        return "An" if word[:1] in "aeiou" else "A"

    lead = human("perspective")
    return (
        f"{article(lead)} {lead} {human('genre')} game set in a {human('theme')} universe "
        f"with {human('combat')} combat and {human('progression')} progression."
    )


def _brief_intake(brief: Mapping[str, str]) -> Intake:
    ballots = brief_ballots(brief)
    if ballots:
        # Highest weight wins; ties break on the genre's own vote, then name.
        genre_era = BRIEF_ERA_VOTES["genre"].get(brief.get("genre", ""), "")
        era = max(ballots, key=lambda e: (ballots[e], e == genre_era, e))
    else:
        era = "extraction_now"
    base = ContextTensor.from_era(era)
    runners = sorted((e for e in ballots if e != era), key=lambda e: (-ballots[e], e))
    tensor = base
    if runners:
        # Blend toward the runner-up in proportion to its share of the vote,
        # so an rpg-with-tactics-combat is a real blend rather than a label.
        share = ballots[runners[0]] / (ballots[era] + ballots[runners[0]])
        blended = base.lerp(ContextTensor.from_era(runners[0]), min(0.45, share * 0.6))
        tensor = ContextTensor(tuple(blended.values), era=era)
    theme = brief.get("theme", "")
    return Intake(
        era=era,
        tensor=tensor,
        ballots={e: int(round(v * 2)) for e, v in ballots.items()},
        vision=_brief_vision(brief),
        answers=dict(brief),
        genre=brief.get("genre", BRIEF_DEFAULTS["genre"]),
        theme=theme,
        perspective=brief.get("perspective", ""),
        setting=BRIEF_SETTINGS.get(theme, ""),
        brief=dict(brief),
        brief_ballots=dict(ballots),
    )


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
