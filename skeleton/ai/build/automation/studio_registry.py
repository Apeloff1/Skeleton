"""Deterministic 1,000-role virtual studio for unattended game-building work."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable, Sequence

STUDIO_SIZE = 1000

_DIVISIONS: tuple[tuple[str, str], ...] = (
    ("frontier_architecture", "invent and integrate model/game-building architecture"),
    ("game_design", "turn goals into playable systems, loops, pacing, and constraints"),
    ("gameplay_systems", "build reusable mechanics, abilities, interaction, and rules"),
    ("procedural_generation", "build controllable generators for worlds, levels, quests, and assets"),
    ("agent_ai", "build embodied agents, planners, NPC intelligence, and multi-agent behavior"),
    ("world_simulation", "build persistent worlds, economies, ecology, causality, and simulation"),
    ("physics", "build robust movement, collision, vehicles, destruction, and physical interaction"),
    ("animation", "build animation graphs, motion synthesis, IK, retargeting, and character motion"),
    ("graphics", "build rendering, lighting, materials, VFX, geometry, and visual pipelines"),
    ("audio", "build adaptive audio, speech, music, ambience, and sound-system tooling"),
    ("tools_pipeline", "build editor automation, asset pipelines, import/export, and authoring tools"),
    ("engine_runtime", "build runtime architecture, ECS, streaming, save/load, and platform systems"),
    ("networking", "build multiplayer replication, prediction, authority, sessions, and resilience"),
    ("qa_verification", "design adversarial tests, game-play evaluation, fuzzing, and regression gates"),
    ("security_supply_chain", "protect secrets, dependencies, sandboxing, provenance, and release trust"),
    ("performance", "profile and optimize latency, memory, throughput, startup, and frame-time"),
    ("data_evaluation", "build benchmarks, telemetry, datasets, scoring, and experiment analysis"),
    ("research_synthesis", "translate research and competitor capabilities into testable engineering bets"),
    ("developer_experience", "improve APIs, debugging, documentation, observability, and local workflows"),
    ("release_operations", "keep branches, CI, packaging, compatibility, and delivery reliable"),
)

_TRACKS: tuple[str, ...] = (
    "systems",
    "algorithms",
    "integration",
    "evaluation",
    "reliability",
    "tooling",
    "performance",
    "usability",
    "experimentation",
    "hardening",
)

_MODES: tuple[str, ...] = (
    "scout",
    "builder",
    "reviewer",
    "tester",
    "integrator",
)


@dataclass(frozen=True, slots=True)
class StudioBot:
    """One stable virtual worker identity.

    Identities are deterministic so logs remain comparable across runs. The
    registry intentionally represents 1,000 roles without launching 1,000
    concurrent processes; the scheduler activates bounded cohorts.
    """

    bot_id: str
    ordinal: int
    division: str
    track: str
    mode: str
    mission: str
    write_capable: bool
    review_level: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_studio() -> tuple[StudioBot, ...]:
    """Return exactly 1,000 stable, specialized workers."""

    bots: list[StudioBot] = []
    ordinal = 0
    for division, mission in _DIVISIONS:
        for track in _TRACKS:
            for mode in _MODES:
                ordinal += 1
                bots.append(
                    StudioBot(
                        bot_id=f"studio-{ordinal:04d}",
                        ordinal=ordinal,
                        division=division,
                        track=track,
                        mode=mode,
                        mission=mission,
                        write_capable=mode in {"builder", "integrator"},
                        review_level={"scout": 1, "builder": 1, "tester": 2, "integrator": 2, "reviewer": 3}[mode],
                    )
                )
    if len(bots) != STUDIO_SIZE:
        raise AssertionError(f"studio registry must contain {STUDIO_SIZE} bots, got {len(bots)}")
    return tuple(bots)


STUDIO: tuple[StudioBot, ...] = build_studio()


def registry_fingerprint(bots: Sequence[StudioBot] = STUDIO) -> str:
    """Stable digest used in audit logs to prove which roster was scheduled."""

    payload = json.dumps(
        [bot.to_dict() for bot in bots],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def select_cohort(
    seed: str,
    *,
    size: int = 15,
    divisions: Iterable[str] = (),
    bots: Sequence[StudioBot] = STUDIO,
) -> tuple[StudioBot, ...]:
    """Select a deterministic, diverse cohort without unbounded concurrency."""

    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("seed must be a non-empty string")
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 50:
        raise ValueError("size must be between 1 and 50")

    requested = {value.strip() for value in divisions if isinstance(value, str) and value.strip()}
    candidates = [bot for bot in bots if not requested or bot.division in requested]
    if len(candidates) < size:
        raise ValueError("not enough bots match requested divisions")

    def score(bot: StudioBot) -> bytes:
        material = f"{seed}\x1f{bot.bot_id}\x1f{bot.division}\x1f{bot.track}\x1f{bot.mode}"
        return hashlib.sha256(material.encode("utf-8")).digest()

    ranked = sorted(candidates, key=score)

    selected: list[StudioBot] = []
    seen_divisions: set[str] = set()
    for bot in ranked:
        if bot.division in seen_divisions:
            continue
        selected.append(bot)
        seen_divisions.add(bot.division)
        if len(selected) == size:
            return tuple(selected)

    selected_ids = {bot.bot_id for bot in selected}
    for bot in ranked:
        if bot.bot_id in selected_ids:
            continue
        selected.append(bot)
        if len(selected) == size:
            break
    return tuple(selected)


def find_specialist(
    division: str,
    *,
    mode: str,
    seed: str,
    bots: Sequence[StudioBot] = STUDIO,
) -> StudioBot:
    """Return one deterministic specialist for a division/mode pair."""

    matches = [bot for bot in bots if bot.division == division and bot.mode == mode]
    if not matches:
        raise ValueError(f"no {mode!r} specialist in division {division!r}")
    return min(
        matches,
        key=lambda bot: hashlib.sha256(f"{seed}\x1f{bot.bot_id}".encode("utf-8")).digest(),
    )
