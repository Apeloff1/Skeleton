"""Self-learning practice for game creation.

Lessons are generated from closed slots in this module. A review pass repeats
the concepts a learner still misses. Held-out lines are a filter and a
measurement, never practice text. Nothing here promotes a checkpoint.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from skeleton.ai.runtime.inference.english_game_pareto import holdout_documents as english_holdouts
from skeleton.ai.runtime.inference.game_creation_az import holdout_documents as az_holdouts

PRACTICE_VERSION = "skeleton.game_self_learn.v1"
WINDOW = 40

# Closed slots. Each sentence is original prose built from these lists.
_ROLES = ("designer", "programmer", "animator", "writer", "composer", "tester")
_FIELDS = (
    "health",
    "position",
    "inventory",
    "tick index",
    "random stream",
    "item kind",
    "eye colour",
    "cloth colour",
)
_RATES = ("sixty", "thirty", "twenty", "fifteen")
_TIERS = ("65536", "32768", "16384", "8192", "4096", "2048", "1024", "512")
_COLOURS = ("copper", "gold", "field", "dusk", "harbor", "hearth")
_KINDS = ("lantern", "satchel", "map", "key", "charm")
_CLOTHS = ("linen", "wool", "silk", "canvas", "felt")
_WEARS = ("fresh", "worn", "mended", "faded", "weathered")
_PHASES = ("approach", "threat", "choice", "resolution", "rest")
_PLACES = ("winter court", "harbor lane", "hearth hall", "field gate", "dusk stair")
_REGIONS = ("hand", "torso", "head", "back")
_FAILURES = ("missed tell", "late press", "empty resource", "blocked route")


def held_windows() -> tuple[str, ...]:
    windows: list[str] = []
    for text in (*english_holdouts(), *az_holdouts()):
        if len(text) <= WINDOW:
            windows.append(text)
            continue
        windows.extend(text[index : index + WINDOW] for index in range(len(text) - WINDOW + 1))
    return tuple(dict.fromkeys(windows))


def leaks_holdout(text: str, windows: Sequence[str] | None = None) -> bool:
    banned = windows if windows is not None else held_windows()
    return any(window in text for window in banned)


def _lessons() -> list[tuple[str, str]]:
    """Return (concept, text) practice lines. Concepts feed the review queue."""
    rows: list[tuple[str, str]] = []
    for role in _ROLES:
        for field in _FIELDS:
            rows.append(
                (
                    "logic",
                    f"One {role} owns {field}. Another {role} may request a change only by sending an event the owner applies.",
                )
            )
            rows.append(
                (
                    "logic",
                    f"The authoritative record stores {field}. Cosmetic animation may lag, and it must not become a second writer of {field}.",
                )
            )
    for rate in _RATES:
        for other in _RATES:
            if rate == other:
                continue
            rows.append(
                (
                    "tick",
                    f"When the picture rate moves between {rate} and {other}, the fixed tick still advances movement, cooldowns, and spawn tables.",
                )
            )
            rows.append(
                (
                    "tick",
                    f"A replay written at a {rate} display and rebuilt at a {other} display matches positions when both consume the same per-tick inputs and seed.",
                )
            )
    for source, target in zip(_TIERS, _TIERS[1:]):
        rows.append(
            (
                "scale",
                f"Authoring may name a {source} tier and a {target} tier. The plan stores the divisor and does not allocate the larger bitmap.",
            )
        )
        rows.append(
            (
                "scale",
                f"Nearest growth of a {target} raster repeats pixels and adds no colours. A box step from {source} may mix a channel and stays an authoring choice.",
            )
        )
    for colour in _COLOURS:
        for kind in _KINDS:
            rows.append(
                (
                    "items",
                    f"A {colour} {kind} changes the item colour token. The body region, the use rule, and the rest of the sheet stay on their previous tokens.",
                )
            )
        for cloth in _CLOTHS:
            rows.append(
                (
                    "clothing",
                    f"A {colour} trim on {cloth} marks a repair. The primary cloth token stays {cloth} even when the micro pattern shows the repair.",
                )
            )
    for wear in _WEARS:
        for cloth in _CLOTHS:
            rows.append(
                (
                    "clothing",
                    f"{wear.capitalize()} {cloth} edits the micro pattern only. Skin, eyes, and hair tokens are unchanged by that wear mark.",
                )
            )
    for place in _PLACES:
        rows.append(
            (
                "character",
                f"A scene at the {place} may add a scarf accessory. Skin, eyes, and hair change only when the canon ledger records a cause.",
            )
        )
        rows.append(
            (
                "world",
                f"The {place} needs a landmark a player can name, a risk, and a route back. An empty bitmap is not yet that place.",
            )
        )
    for phase in _PHASES:
        rows.append(
            (
                "gameplay",
                f"A readable encounter keeps the {phase} beat long enough to see. Adding another phase waits until this beat has a counter.",
            )
        )
        rows.append(
            (
                "gameplay",
                f"Players who miss the {phase} beat need a longer tell or a clearer camera. Raising a health total is a later, separate choice.",
            )
        )
    for role in _ROLES:
        rows.append(
            (
                "tools",
                f"The {role} exports through a registry row that names source, hash, and target limits. A second run from the same inputs must match or explain the difference.",
            )
        )
        rows.append(
            (
                "ship",
                f"The {role} does not call a loose folder a release. The receipt names one artifact hash, the commands, and the frame budget on the slow target.",
            )
        )
    for rate in _RATES:
        rows.append(
            (
                "audio",
                f"Music tempo is a quarter note from beats per minute. A picture running at {rate} frames does not skip the accent the simulation already marked.",
            )
        )
        rows.append(
            (
                "interface",
                f"At a {rate} frame display the next verb, the limiting resource, and the failure stay readable. Colour is never the only channel.",
            )
        )
    # Wider adjacent practice: production, save, and scope, still original.
    for field in _FIELDS:
        rows.append(
            (
                "simulation",
                f"A save taken while {field} is mid-update stores the rule value and the tick index. Loading restores that value before any decorative frame is shown.",
            )
        )
        rows.append(
            (
                "scope",
                f"A feature that does not change {field}, the repeated verb, or a fair retry waits. The scope line records the wait in writing.",
            )
        )
    for kind in _KINDS:
        for region in _REGIONS:
            rows.append(
                (
                    "items",
                    f"Attaching a {kind} to the {region} writes the body region and the item kind. Hair style and eye colour are not fields that attachment may edit.",
                )
            )
    for place in _PLACES:
        for failure in _FAILURES:
            rows.append(
                (
                    "playtest",
                    f"A failed attempt at the {place} caused by a {failure} names that cause. The next task repairs the read or the rule, then retries from a legal state.",
                )
            )
        for phase in _PHASES:
            rows.append(
                (
                    "gameplay",
                    f"At the {place}, the {phase} beat stays visible before the next demand. Two beats with counters outrank a third beat with no rest.",
                )
            )
    for source in _TIERS:
        for rate in _RATES:
            rows.append(
                (
                    "scale",
                    f"A {source} tier plan at a {rate} frame display still allocates no full-tier bitmap. The frame budget measures input, simulation, and the draw separately.",
                )
            )
    for role in _ROLES:
        for failure in _FAILURES:
            rows.append(
                (
                    "logic",
                    f"The {role} logs a {failure} against the rule id. Rejecting the edit leaves the previous authoritative state in place for the retry.",
                )
            )
    for colour in _COLOURS:
        for region in _REGIONS:
            rows.append(
                (
                    "character",
                    f"A {colour} mark on the {region} is an item or cloth token. It does not rename skin tone, eye colour, or hair style.",
                )
            )
    for wear in _WEARS:
        for kind in _KINDS:
            rows.append(
                (
                    "items",
                    f"A {wear} {kind} keeps its item kind. Wear edits the micro pattern of the prop and leaves the character sheet factors beside it.",
                )
            )
    for role in _ROLES:
        for place in _PLACES:
            rows.append(
                (
                    "world",
                    f"The {role} can walk the {place} once and name its landmark. If the landmark cannot be named, the layout is not ready for a second route.",
                )
            )
    return rows


def practice_documents() -> tuple[str, ...]:
    """Unique practice lines with no 40-character holdout window inside them."""
    windows = held_windows()
    seen: set[str] = set()
    kept: list[str] = []
    for _concept, text in _lessons():
        if text in seen or len(text) < 40 or leaks_holdout(text, windows):
            continue
        seen.add(text)
        kept.append(text)
    if len(kept) < 200:
        raise RuntimeError("self-learn practice collapsed below 200 lessons")
    return tuple(kept)


def practice_by_concept() -> dict[str, tuple[str, ...]]:
    windows = held_windows()
    grouped: dict[str, list[str]] = {}
    seen: set[str] = set()
    for concept, text in _lessons():
        if text in seen or len(text) < 40 or leaks_holdout(text, windows):
            continue
        seen.add(text)
        grouped.setdefault(concept, []).append(text)
    return {concept: tuple(lines) for concept, lines in grouped.items()}


def review_order(concept_loss: Mapping[str, float]) -> tuple[str, ...]:
    """Concepts the learner is worst at come first. Higher loss is reviewed sooner."""
    if not concept_loss:
        raise ValueError("concept_loss must not be empty")
    return tuple(sorted(concept_loss, key=lambda name: (-float(concept_loss[name]), name)))


def review_documents(concept_loss: Mapping[str, float], *, rounds: int = 2) -> tuple[str, ...]:
    """Repeat weak concepts. This is the self-learning pass, still holdout-free."""
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
        raise ValueError("rounds must be a positive int")
    grouped = practice_by_concept()
    unknown = [name for name in concept_loss if name not in grouped]
    if unknown:
        raise ValueError(f"unknown concepts: {unknown}")
    ordered = review_order(concept_loss)
    lines: list[str] = []
    for _ in range(rounds):
        for concept in ordered:
            lines.extend(grouped[concept])
    return tuple(lines)
