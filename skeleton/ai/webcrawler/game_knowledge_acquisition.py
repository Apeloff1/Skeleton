"""Game-development knowledge acquisition built on the real crawler runtime.

Public documentation is *evidence*, never an instruction, executable asset, or
permission to train. The crawler enforces robots, egress, redirects and budgets.
These methods discover and parse source material into exact, attributable spans.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Callable, Iterable
from urllib.parse import urlsplit
import re

from .core import CrawlDocument, CrawlEngine, CrawlPolicy, canonicalize_url
from .dragon_research_discovery import (
    DiscoveryQuery, ResearchHit, ResearchSource, discover_research,
)
from .dragon_mission_quality import segment_passages, scan_untrusted_instructions

_DOMAINS = {
    "platforming": ("jump arc", "coyote time", "jump buffering", "moving platform", "collision"),
    "combat": ("hitbox", "hurtbox", "invulnerability frames", "enemy telegraph", "damage"),
    "puzzle": ("switch state", "puzzle dependency", "feedback", "level design", "state machine"),
    "rpg": ("inventory", "quest state", "dialogue tree", "progression", "economy"),
    "strategy": ("pathfinding", "resource economy", "fog of war", "AI planning", "simulation"),
    "racing": ("vehicle handling", "traction", "drift", "steering", "checkpoint"),
    "survival": ("crafting", "resource decay", "survival loop", "building", "weather"),
    "general": ("game loop", "input handling", "scene graph", "physics timestep", "save system"),
}
_GENRE_ALIASES = {
    "platformer":"platforming", "platforming":"platforming",
    "action":"combat", "combat":"combat",
    "exploration":"general", "adventure":"general",
    "puzzle":"puzzle", "rpg":"rpg", "strategy":"strategy",
    "racing":"racing", "survival":"survival", "general":"general",
}

_ENGINES = {
    "godot": ("GDScript", "CharacterBody2D", "Area2D", "TileMapLayer", "InputMap"),
    "unity": ("C#", "MonoBehaviour", "Rigidbody2D", "FixedUpdate", "ScriptableObject"),
    "unreal": ("Blueprint", "Actor", "UActorComponent", "Enhanced Input", "Gameplay Ability"),
    "phaser": ("Phaser 3", "Arcade Physics", "Scene", "tilemap", "pointer input"),
    "web": ("CanvasRenderingContext2D", "requestAnimationFrame", "WebAudio", "KeyboardEvent"),
}
_MECHANIC_TERMS = {
    "jump": ("jump", "coyote time", "jump buffer", "variable height", "double jump"),
    "movement": ("acceleration", "friction", "velocity", "dash", "sprint"),
    "collision": ("collision", "hitbox", "hurtbox", "trigger", "swept"),
    "camera": ("camera", "follow target", "dead zone", "parallax"),
    "combat": ("attack", "damage", "cooldown", "knockback", "invincibility"),
    "enemy_ai": ("patrol", "chase", "line of sight", "enemy state"),
    "collectible": ("collectible", "pickup", "coin", "power up"),
    "checkpoint": ("checkpoint", "respawn", "save point"),
    "progression": ("unlock", "upgrade", "experience points", "quest"),
    "puzzle": ("puzzle", "switch", "door", "pressure plate"),
    "economy": ("currency", "crafting", "resource sink", "inventory"),
    "accessibility": ("remap", "subtitles", "contrast", "screen reader"),
}
_API = re.compile(
    r"(?<![\w])(?:CharacterBody2D|RigidBody2D|Area2D|TileMapLayer|"
    r"Input\.is_action_(?:pressed|just_pressed)|move_and_slide|"
    r"MonoBehaviour|Rigidbody2D|FixedUpdate|Update|AddForce|"
    r"UActorComponent|AActor|UInputAction|Phaser\.Scene|"
    r"this\.physics\.add|requestAnimationFrame|CanvasRenderingContext2D)"
)
_VALUE = re.compile(
    r"(?<![\w])(-?\d+(?:\.\d+)?)\s*(ms|milliseconds?|seconds?|s|"
    r"fps|frames?|pixels?|px|m/s|units?|degrees?|hz|%)\b", re.I
)
_HEAD = re.compile(
    r"(?m)^(?:#{1,5}\s+|(?:chapter|section)\s+\d+[.: ]|"
    r"(?:movement|physics|input|camera|combat|examples|implementation|"
    r"performance|accessibility)\s*[:\-])[^\n]{2,160}$", re.I
)
_CONCEPT = re.compile(
    r"\b(?:requires?|depends? on|in contrast|trade[- ]off|"
    r"should|must|avoid|because|therefore|recommend(?:ed)?)\b", re.I
)


@dataclass(frozen=True)
class GameSource:
    url: str
    title: str
    topic: str
    origin: str
    discovery_id: str


@dataclass(frozen=True)
class KnowledgePassage:
    source_url: str
    content_hash: str
    start: int
    end: int
    text: str
    domain: str
    tags: tuple[str, ...]
    source_score: float

    @property
    def passage_id(self) -> str:
        return sha256(
            f"{self.content_hash}:{self.start}:{self.end}:{self.domain}".encode()
        ).hexdigest()


@dataclass(frozen=True)
class GameParameter:
    passage_id: str
    value: float
    unit: str
    context: str


@dataclass(frozen=True)
class EngineSymbol:
    passage_id: str
    symbol: str
    engine: str
    context: str


def _validated_document(doc: CrawlDocument) -> None:
    if not isinstance(doc, CrawlDocument):
        raise TypeError("CrawlDocument required")
    if sha256(doc.text.encode("utf-8")).hexdigest() != doc.content_hash:
        raise ValueError("source text/digest mismatch")
    if not CrawlPolicy().admits(doc.canonical_url):
        raise ValueError("disallowed source identity")
    if urlsplit(doc.canonical_url).username is not None:
        raise ValueError("source URL contains credentials")
    if not isinstance(doc.source_score, (int, float)) or not isfinite(doc.source_score):
        raise ValueError("invalid source score")


# 01: Intent-specialized discovery queries, not indiscriminate internet search.
def plan_game_research(genre: str, engine: str, *, max_queries: int = 12
                       ) -> tuple[DiscoveryQuery, ...]:
    if not 1 <= max_queries <= 40:
        raise ValueError("invalid query budget")
    genre, engine = genre.casefold().strip(), engine.casefold().strip()
    genre = _GENRE_ALIASES.get(genre,genre)
    if genre not in _DOMAINS or engine not in _ENGINES:
        raise ValueError("unsupported genre/engine")
    queries = [
        f"{engine} {genre} game mechanics implementation",
        f"{engine} game tutorial project architecture",
        f"{engine} physics input controller best practices",
    ]
    queries += [f"{engine} {term} implementation" for term in _DOMAINS[genre]]
    queries += [f"{engine} {api} examples" for api in _ENGINES[engine][:3]]
    return tuple(DiscoveryQuery(q, sources=(
        ResearchSource.WIKIPEDIA, ResearchSource.CROSSREF,
        ResearchSource.OPENALEX,
    ), limit_per_source=4) for q in dict.fromkeys(queries[:max_queries]))


# 02: Discover candidate material through existing public API adapters.
def discover_game_research(
    genre: str, engine: str, transport: Callable, *,
    authorized: bool, max_results: int = 100,
) -> tuple[GameSource, ...]:
    if not authorized:
        raise PermissionError("research discovery requires authorization")
    if not 1 <= max_results <= 250:
        raise ValueError("discovery budget exceeded")
    found: dict[str, GameSource] = {}
    for query in plan_game_research(genre, engine):
        if len(found) >= max_results:
            break
        receipt = discover_research(query, transport, authorized=True,
                                    max_total=min(100, max_results))
        for hit in receipt.hits:
            if len(found) >= max_results:
                break
            canonical = canonicalize_url(hit.url)
            if CrawlPolicy().admits(canonical):
                found.setdefault(canonical, GameSource(
                    canonical, hit.title, query.terms, hit.source.value,
                    hit.source_record,
                ))
    return tuple(sorted(found.values(), key=lambda s: (s.url, s.topic)))


# 03: Prioritize trusted, topic-relevant URLs over broad crawling.
def prioritize_game_sources(
    sources: Iterable[GameSource], *, genre: str, engine: str,
    max_sources: int = 200,
) -> tuple[GameSource, ...]:
    genre = _GENRE_ALIASES.get(genre.casefold().strip(),genre)
    if genre not in _DOMAINS or engine not in _ENGINES:
        raise ValueError("unsupported genre/engine")
    entries = tuple(sources)
    if len(entries) > max_sources or not 1 <= max_sources <= 1000:
        raise ValueError("game source capacity exceeded")
    interests = set(_DOMAINS[genre] + _ENGINES[engine] + (genre, engine))
    def relevance(item: GameSource) -> tuple[int, str]:
        text = (item.title + " " + item.topic).casefold()
        return -sum(term.casefold() in text for term in interests), item.url
    return tuple(sorted(entries, key=relevance))


# 04: Real frontier integration, respecting the crawler's policy/robots gates.
def queue_game_sources(
    engine: CrawlEngine, sources: Iterable[GameSource], *,
    max_enqueues: int = 200,
) -> tuple[str, ...]:
    if not isinstance(engine, CrawlEngine) or not 1 <= max_enqueues <= 10000:
        raise ValueError("invalid crawler frontier")
    accepted = []
    for candidate in sources:
        if len(accepted) >= max_enqueues:
            break
        if not isinstance(candidate, GameSource):
            raise ValueError("invalid source proposal")
        if engine.enqueue(candidate.url, depth=0, priority=1.0):
            accepted.append(candidate.url)
    return tuple(accepted)


# 05: Fetch admitted pages using existing CrawlEngine.step, not a bypass client.
def acquire_game_documents(
    engine: CrawlEngine, *, now: float,
    max_steps: int = 50,
) -> tuple[CrawlDocument, ...]:
    if not isinstance(engine, CrawlEngine) or not 1 <= max_steps <= 10000:
        raise ValueError("invalid acquisition execution")
    if not isfinite(now) or now < 0:
        raise ValueError("invalid acquisition clock")
    accepted = []
    for _ in range(max_steps):
        if engine.budget.exhausted:
            break
        doc = engine.step(now=now)
        if doc is not None:
            _validated_document(doc)
            accepted.append(doc)
    return tuple(accepted)


# 06: Parse durable text sections with exact character locations.
def extract_game_sections(
    doc: CrawlDocument, *, max_sections: int = 100,
) -> tuple[KnowledgePassage, ...]:
    _validated_document(doc)
    if not 1 <= max_sections <= 1000:
        raise ValueError("invalid section budget")
    starts = [0] + [m.start() for m in _HEAD.finditer(doc.text)]
    starts = sorted(set(starts))
    parts = []
    for start, end in zip(starts, starts[1:] + [len(doc.text)]):
        while start < end and doc.text[start].isspace():
            start += 1
        if start == end:
            continue
        if end-start > 1600:
            slices = segment_passages(doc.text[start:end], max_chars=1000, overlap=0,
                                      max_segments=200)
            ranges = [(start+s.start, start+s.end) for s in slices]
        else:
            ranges = [(start, end)]
        for a, b in ranges:
            if len(parts) >= max_sections:
                return tuple(parts)
            chunk = doc.text[a:b]
            terms = {key for key, words in _MECHANIC_TERMS.items()
                     if any(w in chunk.casefold() for w in words)}
            parts.append(KnowledgePassage(
                doc.canonical_url, doc.content_hash, a, b, chunk,
                "game_development", tuple(sorted(terms)), doc.source_score,
            ))
    return tuple(parts)


# 07: Identify game systems anchored in actual source passages.
def extract_game_mechanics(
    passages: Iterable[KnowledgePassage], *, max_hits: int = 500,
) -> tuple[KnowledgePassage, ...]:
    if not 1 <= max_hits <= 10000:
        raise ValueError("invalid mechanic capacity")
    result = []
    for passage in passages:
        if passage.tags:
            result.append(passage)
        if len(result) >= max_hits:
            break
    return tuple(result)


# 08: Engine API vocabulary extraction for retrieval, not copying source code.
def extract_engine_symbols(
    passages: Iterable[KnowledgePassage], *, max_hits: int = 1000,
) -> tuple[EngineSymbol, ...]:
    if not 1 <= max_hits <= 10000:
        raise ValueError("invalid API extraction capacity")
    found = {}
    for passage in passages:
        for match in _API.finditer(passage.text):
            name = match.group()
            engine = (
                "godot" if name in {"CharacterBody2D","RigidBody2D","Area2D",
                                   "TileMapLayer","move_and_slide"} or name.startswith("Input.") else
                "unity" if name in {"MonoBehaviour","Rigidbody2D","FixedUpdate",
                                    "Update","AddForce"} else
                "unreal" if name.startswith(("UActor","AActor","UInput")) else
                "phaser" if name.startswith(("Phaser","this.physics")) else "web"
            )
            found[(passage.passage_id, name)] = EngineSymbol(
                passage.passage_id, name, engine,
                passage.text[max(0,match.start()-80):match.end()+80],
            )
            if len(found) >= max_hits:
                return tuple(found.values())
    return tuple(found.values())


# 09: Recover concrete timings/distances without guessing game units.
def extract_game_parameters(
    passages: Iterable[KnowledgePassage], *, max_hits: int = 1000,
) -> tuple[GameParameter, ...]:
    if not 1 <= max_hits <= 10000:
        raise ValueError("invalid tuning extraction budget")
    result = []
    for passage in passages:
        for match in _VALUE.finditer(passage.text):
            result.append(GameParameter(
                passage.passage_id, float(match.group(1)), match.group(2).lower(),
                passage.text[max(0,match.start()-90):match.end()+90],
            ))
            if len(result) >= max_hits:
                return tuple(result)
    return tuple(result)


# 10: Extract causal implementation guidance with exact source context.
def extract_design_guidance(
    passages: Iterable[KnowledgePassage], *, max_hits: int = 500,
) -> tuple[KnowledgePassage, ...]:
    if not 1 <= max_hits <= 10000:
        raise ValueError("invalid design-guidance budget")
    matched = []
    for item in passages:
        if _CONCEPT.search(item.text) and item.tags:
            matched.append(item)
        if len(matched) >= max_hits:
            break
    return tuple(matched)


# Engine documentation sources curated from official publisher documentation.
# These are *discovery seeds*, NOT a crawler bypass or a training license.
# Current pages and permissions are rechecked by the existing CrawlEngine.
_OFFICIAL_ENGINE_DOCS: dict[str, tuple[tuple[str,str],...]] = {
    "godot": (
        ("CharacterBody2D movement",
         "https://docs.godotengine.org/en/stable/tutorials/2d/2d_movement.html"),
        ("CharacterBody2D physics",
         "https://docs.godotengine.org/en/stable/tutorials/physics/using_character_body_2d.html"),
        ("2D platformer tutorial",
         "https://docs.godotengine.org/en/stable/getting_started/first_2d_game/index.html"),
    ),
    "unity": (
        ("Rigidbody 2D physics",
         "https://docs.unity.com/en-us/engine/7000.0/manual/unity2d/2d-physics/rigidbody-2d"),
        ("Rigidbody2D API",
         "https://docs.unity.com/en-us/engine/7000.0/script-reference/unityengine/rigidbody2d"),
    ),
    "unreal": (
        ("Enhanced Input mapping",
         "https://dev.epicgames.com/documentation/unreal-engine/enhanced-input-in-unreal-engine"),
    ),
    "phaser": (
        ("Official Phaser 3 examples",
         "https://phaser.io/examples/v3/"),
        ("Phaser 3 platformer tutorial",
         "https://phaser.io/tutorials/making-your-first-phaser-3-game"),
    ),
    "web": (
        ("Canvas API",
         "https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API"),
        ("requestAnimationFrame",
         "https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame"),
        ("Web Audio API",
         "https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API"),
    ),
}


def official_game_documentation(
    engine: str, *, policy: CrawlPolicy = CrawlPolicy(),
) -> tuple[GameSource,...]:
    """Return relevant known primary-documentation seeds, not copied content."""
    if engine not in _OFFICIAL_ENGINE_DOCS:
        raise ValueError("unsupported engine documentation family")
    entries=[]
    for title,url in _OFFICIAL_ENGINE_DOCS[engine]:
        canonical=canonicalize_url(url)
        if not policy.admits(canonical):
            continue
        entries.append(GameSource(
            canonical,title,engine+" original development documentation",
            "official_vendor_docs",
            sha256(canonical.encode("utf-8")).hexdigest(),
        ))
    return tuple(entries)


def enqueue_official_game_docs(
    crawler: CrawlEngine, *, engine: str,
) -> tuple[str,...]:
    """Feed actual official documentation to existing robots-aware frontier."""
    return queue_game_sources(
        crawler,official_game_documentation(engine,policy=crawler.policy),
        max_enqueues=40,
    )
