"""Self-learning practice for game creation.

Lessons are generated from closed slots in this module. A review pass repeats
the concepts a learner still misses. Held-out lines are a filter and a
measurement, never practice text. Nothing here promotes a checkpoint.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from skeleton.ai.runtime.inference.english_game_pareto import (
    CURRICULUM as ENGLISH_PARETO_CURRICULUM,
    holdout_documents as english_holdouts,
    pareto_score as _pareto_score,
)
from skeleton.ai.runtime.inference.game_creation_az import (
    CURRICULUM as AZ_CURRICULUM,
    holdout_documents as az_holdouts,
)
from skeleton.ai.runtime.inference.game_pareto_curriculum import (
    CURRICULUM as PARETO_V2_CURRICULUM,
)

PRACTICE_VERSION = "skeleton.game_self_learn.v1"
FINETUNE_SCHEMA = "skeleton.game_self_learn.finetune.v2"
MASTERY_SCHEMA = "skeleton.game_self_learn.mastery.v1"
WINDOW = 40

# Progressive 4-stage game creation curriculum hierarchy:
# Stage 1: Core Loop, Determinism, Fixed Tick, Controls & Scope
# Stage 2: Combat, Gameplay, World Topology, Character Coherence & Art Scale
# Stage 3: Story/Canon Ledger, NPC Systems, Economy, Audio & Interface/A11y
# Stage 4: Simulation Save/Load, Authoring Tooling, Playtest QA & Release Receipt
GAME_CREATION_STAGES: dict[str, tuple[str, ...]] = {
    "stage_1_foundation": (
        "intent",
        "core_loop",
        "controls",
        "game_logic",
        "fixed_tick",
        "mechanics",
        "pareto_scope",
        "logic",
        "tick",
        "scope",
    ),
    "stage_2_world_combat_art": (
        "combat",
        "gameplay",
        "character",
        "character_coherence",
        "clothing_color",
        "items",
        "world",
        "graphics_scale",
        "art_scale",
        "scale",
        "clothing",
        "console_rom",
    ),
    "stage_3_narrative_economy_av": (
        "story",
        "narrative",
        "npc",
        "economy",
        "audio",
        "interface",
        "accessibility",
    ),
    "stage_4_production_qa_ship": (
        "simulation",
        "tools",
        "tooling",
        "playtest",
        "review",
        "ship",
    ),
}

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
_CONSOLES = (
    ("8-bit cartridge", "2bpp planar tile", "16 bytes per 8x8 tile", "4-colour sub-palette"),
    ("handheld DMG cart", "2bpp planar tile", "96 bytes for six tiles", "4-shade monochrome ramp"),
    ("16-bit console cart", "4bpp planar tile", "32 bytes per 8x8 tile", "15-bit BGR555 palette"),
    ("early 3D disc", "CLUT indexed texture", "4KB TMEM micro-cache", "fixed-point vertex snap"),
    ("64-bit console disc", "swizzled 4x4 block texture", "32-byte DMA cache line", "ADPCM stream buffer"),
)


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
    for console_name, tile_fmt, byte_rule, pal_rule in _CONSOLES:
        for role in _ROLES:
            rows.append(
                (
                    "console_rom",
                    f"On an {console_name}, the {role} packs each {tile_fmt} at {byte_rule} and binds the {pal_rule} before linking the ROM bank.",
                )
            )
            rows.append(
                (
                    "console_rom",
                    f"A {console_name} build triggers the {role} to verify the ROM header checksum and OAM scanline sprite budget alongside the {byte_rule} asset table.",
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


def _eval_loss(model: object, documents: Sequence[str]) -> float:
    if hasattr(model, "loss") and callable(model.loss):
        return float(model.loss(tuple(documents)))
    if hasattr(model, "perplexity") and callable(model.perplexity):
        return float(model.perplexity(tuple(documents)))
    raise TypeError("self-learn model must expose loss(documents) or perplexity(documents)")


def concept_losses(model: object) -> dict[str, float]:
    """Measure per-concept loss across the holdout-free practice bank."""
    grouped = practice_by_concept()
    return {concept: _eval_loss(model, lines) for concept, lines in grouped.items()}


def focused_review_documents(
    concept_loss: Mapping[str, float],
    *,
    top_concepts: int = 4,
    rounds: int = 2,
    include_tail: bool = True,
) -> tuple[str, ...]:
    """Emphasize the weakest concepts with higher repetition while retaining tail coverage."""
    if isinstance(top_concepts, bool) or not isinstance(top_concepts, int) or top_concepts < 1:
        raise ValueError("top_concepts must be a positive int")
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
        raise ValueError("rounds must be a positive int")
    grouped = practice_by_concept()
    unknown = [name for name in concept_loss if name not in grouped]
    if unknown:
        raise ValueError(f"unknown concepts: {unknown}")
    ordered = review_order(concept_loss)
    focus = ordered[: min(top_concepts, len(ordered))]
    tail = ordered[min(top_concepts, len(ordered)) :]
    lines: list[str] = []
    for _ in range(rounds):
        for concept in focus:
            lines.extend(grouped[concept])
    if include_tail:
        for concept in tail:
            lines.extend(grouped[concept])
    return tuple(lines)


def self_learn_pass(
    model: object,
    *,
    rounds: int = 1,
    top_concepts: int = 4,
    learning_rate: float = 0.01,
    optimizer: str = "adamw",
    weight_decay: float = 0.01,
    gradient_clip: float = 1.0,
    eval_documents: Sequence[str] | None = None,
) -> dict[str, object]:
    """Execute a closed-loop self-learning review cycle with best-weight retention.

    Evaluates per-concept loss, schedules focused practice on the weakest concepts,
    trains the learner, and retains the pre-pass weights if evaluation loss does not
    improve. Held-out lines may be supplied as `eval_documents` for measurement only
    and are never included in training documents.
    """
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 16:
        raise ValueError("rounds must be an int in [1, 16]")
    if isinstance(top_concepts, bool) or not isinstance(top_concepts, int) or top_concepts < 1:
        raise ValueError("top_concepts must be a positive int")
    before_concepts = concept_losses(model)
    ordered = review_order(before_concepts)
    weakest = ordered[: min(top_concepts, len(ordered))]
    schedule = focused_review_documents(
        before_concepts,
        top_concepts=top_concepts,
        rounds=rounds,
        include_tail=True,
    )
    eval_set = tuple(eval_documents) if eval_documents is not None else practice_documents()[:32]
    if not eval_set:
        raise ValueError("eval_documents must not be empty")
    initial_eval = _eval_loss(model, eval_set)

    # Save state for fail-closed best-weight retention.
    saved_dict = model.to_dict() if hasattr(model, "to_dict") else None
    saved_snap = model.snapshot() if saved_dict is None and hasattr(model, "snapshot") else None

    if hasattr(model, "train") and hasattr(model, "to_dict"):
        model.train(
            schedule,
            epochs=1,
            learning_rate=learning_rate,
            gradient_clip=gradient_clip,
            optimizer=optimizer,
            weight_decay=weight_decay,
        )
    elif hasattr(model, "specialized_calibrate"):
        model.specialized_calibrate(
            schedule,
            epochs=1,
            lr=learning_rate,
            weight_decay=weight_decay,
            holdout=eval_set,
        )
    elif hasattr(model, "fit"):
        model.fit(schedule, lr=learning_rate, schedule="cosine")
    else:
        raise TypeError("unsupported learner model for self_learn_pass")

    candidate_eval = _eval_loss(model, eval_set)
    kept_best = True
    if candidate_eval >= initial_eval:
        kept_best = False
        if saved_dict is not None:
            restored = type(model).from_dict(saved_dict)
            model.embedding = restored.embedding
            model.recurrent = restored.recurrent
            model.hidden_bias = restored.hidden_bias
            model.output = restored.output
            model.output_bias = restored.output_bias
        elif saved_snap is not None:
            restored = type(model).from_snapshot(saved_snap)
            model.E, model.P, model.Wout, model.bout = restored.E, restored.P, restored.Wout, restored.bout
            model.layers, model.n_layers = restored.layers, restored.n_layers
            model.fitted, model.steps = restored.fitted, restored.steps
            if getattr(model, "tied", False) and hasattr(model, "tie"):
                model.tie()
    final_eval = _eval_loss(model, eval_set)
    after_concepts = concept_losses(model)
    return {
        "schema_version": PRACTICE_VERSION,
        "weakest_concepts": weakest,
        "scheduled_documents": len(schedule),
        "initial_eval_loss": initial_eval,
        "candidate_eval_loss": candidate_eval,
        "final_eval_loss": final_eval,
        "improved": final_eval < initial_eval,
        "kept_candidate": kept_best,
        "concept_loss_before": before_concepts,
        "concept_loss_after": after_concepts,
        "promoted": False,
    }


def all_holdout_documents() -> tuple[str, ...]:
    """Return every holdout line across English Pareto, A-to-Z, and Pareto v2 curricula."""
    v2_holdouts = tuple(
        text
        for family in PARETO_V2_CURRICULUM.values()
        for text in family.get("holdout", ())
    )
    return tuple(dict.fromkeys((*english_holdouts(), *az_holdouts(), *v2_holdouts)))


def all_held_windows() -> tuple[str, ...]:
    """Return 40-char sliding windows across all three game-creation holdout banks."""
    windows: list[str] = []
    for text in all_holdout_documents():
        if len(text) <= WINDOW:
            windows.append(text)
            continue
        windows.extend(text[index : index + WINDOW] for index in range(len(text) - WINDOW + 1))
    return tuple(dict.fromkeys(windows))


def leaks_any_holdout(text: str, windows: Sequence[str] | None = None) -> bool:
    """Fail-closed holdout check across all three game-creation curricula."""
    banned = windows if windows is not None else all_held_windows()
    return any(window in text for window in banned)


def pareto_weighted_curriculum(
    *,
    stage: str | None = None,
    min_pareto_score: int = 0,
) -> tuple[dict[str, object], ...]:
    """Synthesize a holdout-safe, Pareto-prioritized game creation curriculum.

    Each entry contains:
      - `source`: `"english_game_pareto"`, `"game_creation_az"`, or `"game_pareto_v2"`
      - `family`: pillar/family name
      - `stage`: stage id in `GAME_CREATION_STAGES`
      - `impact`, `reusable`, `effort`, `risk`: Pareto integers in [1, 5]
      - `pareto_score`: `impact * reusable - effort - risk`
      - `priority_weight`: `(impact * reusable) / (1.0 + 0.5 * (effort + risk))`
      - `repetitions`: integer emphasis count in `{1, 2, 3}` derived from Pareto priority
      - `text`: lesson text verified free of any 40-character holdout window
    """
    if stage is not None and stage not in GAME_CREATION_STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {tuple(GAME_CREATION_STAGES)}")
    family_to_stage: dict[str, str] = {}
    for stage_name, families in GAME_CREATION_STAGES.items():
        for fam in families:
            family_to_stage.setdefault(fam, stage_name)

    windows = all_held_windows()
    sources = (
        ("english_game_pareto", ENGLISH_PARETO_CURRICULUM),
        ("game_creation_az", AZ_CURRICULUM),
        ("game_pareto_v2", PARETO_V2_CURRICULUM),
    )
    entries: list[dict[str, object]] = []
    seen_texts: set[str] = set()
    for source_name, curr in sources:
        for family_name, family_body in curr.items():
            assigned_stage = family_to_stage.get(family_name, "stage_2_world_combat_art")
            if stage is not None and assigned_stage != stage:
                continue
            for row in family_body.get("train", ()):
                impact, reusable, effort, risk, text = row
                if text in seen_texts or leaks_any_holdout(text, windows):
                    continue
                score = _pareto_score(row)
                if score < min_pareto_score:
                    continue
                seen_texts.add(text)
                priority = round((float(impact) * float(reusable)) / (1.0 + 0.5 * float(effort + risk)), 4)
                reps = 3 if score >= 20 else (2 if score >= 14 else 1)
                entries.append({
                    "source": source_name,
                    "family": family_name,
                    "stage": assigned_stage,
                    "impact": int(impact),
                    "reusable": int(reusable),
                    "effort": int(effort),
                    "risk": int(risk),
                    "pareto_score": int(score),
                    "priority_weight": priority,
                    "repetitions": reps,
                    "text": text,
                })
    entries.sort(key=lambda item: (-float(item["priority_weight"]), -int(item["pareto_score"]), str(item["family"])))
    return tuple(entries)


def stage_curriculum_documents(
    stage: str,
    *,
    include_practice: bool = True,
    pareto_repeat: bool = True,
) -> tuple[str, ...]:
    """Return ordered training documents for one progressive game-creation stage."""
    if stage not in GAME_CREATION_STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    rows = pareto_weighted_curriculum(stage=stage)
    docs: list[str] = []
    for item in rows:
        reps = int(item["repetitions"]) if pareto_repeat else 1
        docs.extend([str(item["text"])] * reps)
    if include_practice:
        by_concept = practice_by_concept()
        for family in GAME_CREATION_STAGES[stage]:
            if family in by_concept:
                docs.extend(by_concept[family])
    windows = all_held_windows()
    return tuple(doc for doc in docs if not leaks_any_holdout(doc, windows))


def cross_curriculum_losses(model: object) -> dict[str, dict[str, float]]:
    """Evaluate per-family train and holdout losses across all game-creation curricula."""
    english_train: dict[str, float] = {}
    english_holdout: dict[str, float] = {}
    for name, body in ENGLISH_PARETO_CURRICULUM.items():
        english_train[name] = _eval_loss(model, tuple(r[4] for r in body["train"]))
        english_holdout[name] = _eval_loss(model, tuple(body["holdout"]))

    az_train: dict[str, float] = {}
    az_holdout: dict[str, float] = {}
    for name, body in AZ_CURRICULUM.items():
        az_train[name] = _eval_loss(model, tuple(r[4] for r in body["train"]))
        az_holdout[name] = _eval_loss(model, tuple(body["holdout"]))

    v2_train: dict[str, float] = {}
    v2_holdout: dict[str, float] = {}
    for name, body in PARETO_V2_CURRICULUM.items():
        v2_train[name] = _eval_loss(model, tuple(r[4] for r in body["train"]))
        v2_holdout[name] = _eval_loss(model, tuple(body["holdout"]))

    stage_losses: dict[str, float] = {}
    for stage_name in GAME_CREATION_STAGES:
        stage_docs = stage_curriculum_documents(stage_name, include_practice=False, pareto_repeat=False)
        if stage_docs:
            stage_losses[stage_name] = _eval_loss(model, stage_docs)

    return {
        "english_pareto_train": english_train,
        "english_pareto_holdout": english_holdout,
        "az_train": az_train,
        "az_holdout": az_holdout,
        "pareto_v2_train": v2_train,
        "pareto_v2_holdout": v2_holdout,
        "practice_concepts": concept_losses(model),
        "stages": stage_losses,
    }


def game_creation_mastery_report(model: object) -> dict[str, object]:
    """Compute a comprehensive game-creation mastery report across all pillars and stages."""
    losses = cross_curriculum_losses(model)
    pillar_losses: dict[str, float] = {}
    for group in ("english_pareto_train", "az_train", "pareto_v2_train", "practice_concepts"):
        for k, v in losses[group].items():
            if k in pillar_losses:
                pillar_losses[k] = 0.5 * (pillar_losses[k] + float(v))
            else:
                pillar_losses[k] = float(v)

    ordered_weakest = tuple(sorted(pillar_losses, key=lambda k: (-pillar_losses[k], k)))
    ordered_strongest = tuple(sorted(pillar_losses, key=lambda k: (pillar_losses[k], k)))

    all_holdouts = all_holdout_documents()
    overall_holdout_loss = _eval_loss(model, all_holdouts)
    mean_pillar_loss = sum(pillar_losses.values()) / max(1, len(pillar_losses))
    # Bounded mastery index in (0, 1] inversely proportional to loss.
    mastery_index = round(1.0 / (1.0 + max(0.0, mean_pillar_loss) / 5.0), 4)

    return {
        "schema_version": MASTERY_SCHEMA,
        "pillar_count": len(pillar_losses),
        "mean_pillar_loss": round(mean_pillar_loss, 6),
        "overall_holdout_loss": round(overall_holdout_loss, 6),
        "mastery_index": mastery_index,
        "weakest_pillars": ordered_weakest[:6],
        "strongest_pillars": ordered_strongest[:6],
        "stage_losses": {k: round(v, 6) for k, v in losses["stages"].items()},
        "losses": losses,
        "holdout_isolated": True,
        "promoted": False,
    }


def _save_model_state(model: object) -> tuple[str, object]:
    if hasattr(model, "to_dict") and callable(model.to_dict):
        return ("dict", model.to_dict())
    if hasattr(model, "snapshot") and callable(model.snapshot):
        return ("snapshot", model.snapshot())
    return ("none", None)


def _restore_model_state(model: object, saved: tuple[str, object]) -> None:
    kind, payload = saved
    if kind == "dict" and payload is not None:
        restored = type(model).from_dict(payload)
        model.embedding = restored.embedding
        model.recurrent = restored.recurrent
        model.hidden_bias = restored.hidden_bias
        model.output = restored.output
        model.output_bias = restored.output_bias
    elif kind == "snapshot" and payload is not None:
        restored = type(model).from_snapshot(payload)
        model.E, model.P, model.Wout, model.bout = restored.E, restored.P, restored.Wout, restored.bout
        model.layers, model.n_layers = restored.layers, restored.n_layers
        model.fitted, model.steps = restored.fitted, restored.steps
        if getattr(model, "tied", False) and hasattr(model, "tie"):
            model.tie()


def _train_model_on_docs(
    model: object,
    docs: Sequence[str],
    *,
    epochs: int,
    lr: float,
    optimizer: str,
    weight_decay: float,
    gradient_clip: float,
    holdout: Sequence[str],
) -> None:
    if hasattr(model, "train") and hasattr(model, "to_dict"):
        model.train(
            tuple(docs),
            epochs=epochs,
            learning_rate=lr,
            gradient_clip=gradient_clip,
            optimizer=optimizer,
            weight_decay=weight_decay,
        )
    elif hasattr(model, "specialized_calibrate"):
        model.specialized_calibrate(
            tuple(docs),
            epochs=epochs,
            lr=lr,
            weight_decay=weight_decay,
            holdout=tuple(holdout),
        )
    elif hasattr(model, "fit"):
        for _ in range(max(1, epochs)):
            model.fit(tuple(docs), lr=lr, schedule="cosine")
    else:
        raise TypeError("unsupported learner model for finetune_for_game_creation")


def finetune_for_game_creation(
    model: object,
    *,
    stages: Sequence[str] | None = None,
    epochs_per_stage: int = 1,
    remediation_rounds: int = 2,
    top_weak_concepts: int = 5,
    learning_rate: float = 0.015,
    optimizer: str = "adamw",
    weight_decay: float = 0.01,
    gradient_clip: float = 1.0,
    include_practice: bool = True,
    eval_documents: Sequence[str] | None = None,
) -> dict[str, object]:
    """Multi-stage Pareto-prioritized game creation finetuning pipeline with ratchet rollback.

    Executes:
      1. Progressive stage training across `GAME_CREATION_STAGES` (Foundation ->
         World/Combat/Art -> Narrative/Economy/AV -> Production/QA/Ship), repeating
         high-Pareto lessons more frequently and stepping down the learning rate
         across stages.
      2. Per-stage non-regression ratchet: if a stage worsens the evaluation loss,
         the pre-stage weights are restored and re-attempted with halved learning rate.
      3. Targeted remediation pass (`self_learn_pass`) on the learner's weakest
         game-creation concepts.
      4. Full pre/post mastery report across all three game-creation curricula.
    """
    if isinstance(epochs_per_stage, bool) or not isinstance(epochs_per_stage, int) or not 1 <= epochs_per_stage <= 8:
        raise ValueError("epochs_per_stage must be an int in [1, 8]")
    if isinstance(remediation_rounds, bool) or not isinstance(remediation_rounds, int) or not 1 <= remediation_rounds <= 8:
        raise ValueError("remediation_rounds must be an int in [1, 8]")
    stage_Order = tuple(stages) if stages is not None else tuple(GAME_CREATION_STAGES)
    for st in stage_Order:
        if st not in GAME_CREATION_STAGES:
            raise ValueError(f"unknown stage {st!r}")

    # Default evaluation probe combines holdout-free high-Pareto lessons and practice sample.
    if eval_documents is not None:
        eval_set = tuple(eval_documents)
    else:
        top_pareto_docs = tuple(str(r["text"]) for r in pareto_weighted_curriculum(min_pareto_score=16)[:24])
        eval_set = top_pareto_docs + practice_documents()[:24]
    if not eval_set:
        raise ValueError("eval_documents must not be empty")

    holdout_set = all_holdout_documents()
    initial_eval_loss = _eval_loss(model, eval_set)
    initial_holdout_loss = _eval_loss(model, holdout_set)
    before_mastery = game_creation_mastery_report(model)

    stage_receipts: list[dict[str, object]] = []
    current_best_loss = initial_eval_loss
    total_scheduled_docs = 0

    for idx, stage_name in enumerate(stage_Order):
        stage_docs = stage_curriculum_documents(
            stage_name,
            include_practice=include_practice,
            pareto_repeat=True,
        )
        if not stage_docs:
            continue
        # Progressive cosine-like step-down across stages so later specialization
        # does not overwrite Stage 1 core-loop and fixed-tick foundations.
        stage_lr = float(learning_rate) * (0.88 ** idx)
        saved_state = _save_model_state(model)
        before_stage_loss = current_best_loss

        _train_model_on_docs(
            model,
            stage_docs,
            epochs=epochs_per_stage,
            lr=stage_lr,
            optimizer=optimizer,
            weight_decay=weight_decay,
            gradient_clip=gradient_clip,
            holdout=eval_set,
        )
        after_stage_loss = _eval_loss(model, eval_set)
        retried = False
        kept = True
        if after_stage_loss > before_stage_loss:
            # Ratchet rollback + retry at 0.5x lr on top-Pareto subset of the stage.
            _restore_model_state(model, saved_state)
            retried = True
            core_stage_docs = stage_curriculum_documents(
                stage_name,
                include_practice=False,
                pareto_repeat=False,
            )
            if core_stage_docs:
                _train_model_on_docs(
                    model,
                    core_stage_docs,
                    epochs=1,
                    lr=stage_lr * 0.5,
                    optimizer=optimizer,
                    weight_decay=weight_decay,
                    gradient_clip=gradient_clip,
                    holdout=eval_set,
                )
                retry_loss = _eval_loss(model, eval_set)
                if retry_loss <= before_stage_loss:
                    after_stage_loss = retry_loss
                else:
                    _restore_model_state(model, saved_state)
                    after_stage_loss = before_stage_loss
                    kept = False
            else:
                after_stage_loss = before_stage_loss
                kept = False

        current_best_loss = after_stage_loss
        total_scheduled_docs += len(stage_docs)
        stage_receipts.append({
            "stage": stage_name,
            "documents": len(stage_docs),
            "learning_rate": round(stage_lr, 6),
            "loss_before": round(before_stage_loss, 6),
            "loss_after": round(after_stage_loss, 6),
            "improved": after_stage_loss < before_stage_loss,
            "retried": retried,
            "kept": kept,
        })

    # Stage 5: Targeted self-learning remediation pass on the weakest concepts.
    remediation = self_learn_pass(
        model,
        rounds=remediation_rounds,
        top_concepts=top_weak_concepts,
        learning_rate=float(learning_rate) * 0.65,
        optimizer=optimizer,
        weight_decay=weight_decay,
        gradient_clip=gradient_clip,
        eval_documents=eval_set,
    )
    total_scheduled_docs += int(remediation["scheduled_documents"])

    final_eval_loss = _eval_loss(model, eval_set)
    final_holdout_loss = _eval_loss(model, holdout_set)
    after_mastery = game_creation_mastery_report(model)

    return {
        "schema_version": FINETUNE_SCHEMA,
        "stages_executed": tuple(r["stage"] for r in stage_receipts),
        "stage_receipts": tuple(stage_receipts),
        "remediation": remediation,
        "total_scheduled_documents": total_scheduled_docs,
        "initial_eval_loss": round(initial_eval_loss, 6),
        "final_eval_loss": round(final_eval_loss, 6),
        "initial_holdout_loss": round(initial_holdout_loss, 6),
        "final_holdout_loss": round(final_holdout_loss, 6),
        "eval_improved": final_eval_loss < initial_eval_loss,
        "holdout_improved": final_holdout_loss < initial_holdout_loss,
        "mastery_before": before_mastery["mastery_index"],
        "mastery_after": after_mastery["mastery_index"],
        "weakest_pillars_before": before_mastery["weakest_pillars"],
        "weakest_pillars_after": after_mastery["weakest_pillars"],
        "holdout_isolated": True,
        "promoted": False,
    }


def spaced_repetition_schedule(
    concept_loss: Mapping[str, float],
    *,
    previous_loss: Mapping[str, float] | None = None,
    streaks: Mapping[str, int] | None = None,
    max_repetitions: int = 4,
) -> tuple[dict[str, object], ...]:
    """Compute an Ebbinghaus/SM-2 spaced-repetition schedule across concepts."""
    if not concept_loss:
        raise ValueError("concept_loss must not be empty")
    if isinstance(max_repetitions, bool) or not isinstance(max_repetitions, int) or max_repetitions < 1:
        raise ValueError("max_repetitions must be a positive int")
    mean_loss = sum(float(v) for v in concept_loss.values()) / max(1, len(concept_loss))
    items: list[dict[str, object]] = []
    for concept, raw_loss in concept_loss.items():
        loss = float(raw_loss)
        prev = float(previous_loss[concept]) if (previous_loss and concept in previous_loss) else loss
        velocity = prev - loss
        streak = int(streaks[concept]) if (streaks and concept in streaks) else 0
        easiness = max(1.3, min(3.2, 2.5 - 0.25 * max(0.0, loss - mean_loss) + 0.1 * streak))
        urgency = (loss / max(0.25, mean_loss)) * (1.0 / max(1.0, easiness * 0.5))
        if velocity < 0.0:
            urgency *= 1.25
        if urgency >= 1.35:
            reps = max_repetitions
        elif urgency >= 1.05:
            reps = max(1, max_repetitions - 1)
        elif urgency >= 0.80:
            reps = max(1, max_repetitions - 2)
        else:
            reps = 1
        items.append({
            "concept": concept,
            "loss": round(loss, 6),
            "velocity": round(velocity, 6),
            "streak": streak,
            "easiness": round(easiness, 4),
            "urgency": round(urgency, 6),
            "repetitions": reps,
        })
    items.sort(key=lambda r: (-float(r["urgency"]), -float(r["loss"]), str(r["concept"])))
    return tuple(items)


def automated_repetition_training(
    model: object,
    *,
    cycles: int = 2,
    max_repetitions: int = 3,
    top_focus: int = 5,
    learning_rate: float = 0.02,
    optimizer: str = "adamw",
    weight_decay: float = 0.01,
    gradient_clip: float = 1.0,
    eval_documents: Sequence[str] | None = None,
) -> dict[str, object]:
    """Execute multi-cycle spaced-repetition training with non-regression ratchet rollback."""
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 8:
        raise ValueError("cycles must be an int in [1, 8]")
    grouped = practice_by_concept()
    eval_set = tuple(eval_documents) if eval_documents is not None else practice_documents()[:32]
    if not eval_set:
        raise ValueError("eval_documents must not be empty")

    initial_eval = _eval_loss(model, eval_set)
    current_losses = concept_losses(model)
    prev_losses: dict[str, float] | None = None
    streaks: dict[str, int] = {k: 0 for k in grouped}
    cycle_logs: list[dict[str, object]] = []
    total_docs = 0

    for c_idx in range(cycles):
        schedule_rows = spaced_repetition_schedule(
            current_losses,
            previous_loss=prev_losses,
            streaks=streaks,
            max_repetitions=max_repetitions,
        )
        batch: list[str] = []
        for idx, row in enumerate(schedule_rows):
            concept = str(row["concept"])
            reps = int(row["repetitions"]) if idx < top_focus else 1
            batch.extend(grouped[concept][:16] * reps)

        saved = _save_model_state(model)
        before_cycle_eval = _eval_loss(model, eval_set)
        cycle_lr = float(learning_rate) * (0.90 ** c_idx)
        _train_model_on_docs(
            model,
            batch,
            epochs=1,
            lr=cycle_lr,
            optimizer=optimizer,
            weight_decay=weight_decay,
            gradient_clip=gradient_clip,
            holdout=eval_set,
        )
        after_cycle_eval = _eval_loss(model, eval_set)
        kept = True
        if after_cycle_eval > before_cycle_eval:
            _restore_model_state(model, saved)
            after_cycle_eval = before_cycle_eval
            kept = False

        next_losses = concept_losses(model)
        for k, after_v in next_losses.items():
            if after_v <= current_losses.get(k, after_v):
                streaks[k] = streaks.get(k, 0) + 1
            else:
                streaks[k] = 0
        prev_losses = dict(current_losses)
        current_losses = next_losses
        total_docs += len(batch)
        cycle_logs.append({
            "cycle": c_idx + 1,
            "scheduled_documents": len(batch),
            "top_urgent_concepts": tuple(str(r["concept"]) for r in schedule_rows[:top_focus]),
            "eval_before": round(before_cycle_eval, 6),
            "eval_after": round(after_cycle_eval, 6),
            "kept": kept,
        })

    final_eval = _eval_loss(model, eval_set)
    return {
        "schema_version": "skeleton.game_self_learn.repetition.v1",
        "cycles": cycles,
        "total_scheduled_documents": total_docs,
        "initial_eval_loss": round(initial_eval, 6),
        "final_eval_loss": round(final_eval, 6),
        "improved": final_eval < initial_eval,
        "cycle_logs": tuple(cycle_logs),
        "streaks": streaks,
        "holdout_isolated": True,
        "promoted": False,
    }


def curiosity_frontier_curriculum(
    model: object,
    *,
    top_k_concepts: int = 4,
    candidates_per_concept: int = 8,
) -> dict[str, object]:
    """Active Curiosity-Driven Adversarial Curriculum Generator.

    Probes per-lesson cross-entropy loss across the weakest concepts, ranks
    individual lessons by epistemic surprise (loss excess over concept mean),
    and synthesizes holdout-free cross-concept bridge lessons that link pairs
    of high-surprise concepts (e.g., `console_rom` + `gdscript_gameplay` or
    `frame_budget` + `combat_feel`) for maximum sample-efficiency learning.
    """
    if isinstance(top_k_concepts, bool) or not isinstance(top_k_concepts, int) or top_k_concepts < 1:
        raise ValueError("top_k_concepts must be a positive int")
    grouped = practice_by_concept()
    losses = concept_losses(model)
    ordered = review_order(losses)
    focus_concepts = ordered[: min(top_k_concepts, len(ordered))]
    windows = held_windows()

    surprise_lessons: list[dict[str, object]] = []
    selected_corpus: list[str] = []

    for concept in focus_concepts:
        docs = grouped.get(concept, ())[: max(4, int(candidates_per_concept))]
        c_mean = float(losses.get(concept, 1.0))
        scored_docs: list[tuple[float, str]] = []
        for doc in docs:
            doc_loss = _eval_loss(model, (doc,))
            surprise = max(0.0, doc_loss - c_mean * 0.85)
            scored_docs.append((surprise, doc))
        scored_docs.sort(key=lambda item: (-item[0], item[1]))
        for surprise_val, doc in scored_docs[:4]:
            selected_corpus.append(doc)
            surprise_lessons.append({
                "concept": concept,
                "surprise": round(surprise_val, 6),
                "document": doc,
            })

    bridge_lessons: list[str] = []
    for idx in range(len(focus_concepts)):
        c_a = focus_concepts[idx]
        c_b = focus_concepts[(idx + 1) % len(focus_concepts)]
        doc_a = grouped[c_a][0] if grouped.get(c_a) else ""
        doc_b = grouped[c_b][0] if grouped.get(c_b) else ""
        if doc_a and doc_b:
            bridge = f"[Bridge {c_a}<->{c_b}] {doc_a} Meanwhile, {doc_b[0].lower() + doc_b[1:]}"
            if not leaks_holdout(bridge, windows):
                bridge_lessons.append(bridge)
                selected_corpus.append(bridge)

    return {
        "schema_version": "skeleton.game_self_learn.curiosity.v1",
        "focus_concepts": focus_concepts,
        "surprise_lessons": tuple(surprise_lessons),
        "bridge_lessons": tuple(bridge_lessons),
        "curriculum_documents": tuple(selected_corpus),
        "total_documents": len(selected_corpus),
    }


def run_curiosity_self_play_loop(
    model: object,
    *,
    rounds: int = 2,
    top_k_concepts: int = 4,
    learning_rate: float = 0.02,
    optimizer: str = "adamw",
    eval_documents: Sequence[str] | None = None,
) -> dict[str, object]:
    """Closed-loop curiosity-driven self-play training with non-regression ratchet."""
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 6:
        raise ValueError("rounds must be an int in [1, 6]")
    eval_set = tuple(eval_documents) if eval_documents is not None else practice_documents()[:32]
    initial_loss = _eval_loss(model, eval_set)
    history: list[dict[str, object]] = []

    for r_idx in range(rounds):
        frontier = curiosity_frontier_curriculum(model, top_k_concepts=top_k_concepts)
        docs = tuple(frontier["curriculum_documents"])
        saved = _save_model_state(model)
        before_loss = _eval_loss(model, eval_set)
        _train_model_on_docs(
            model,
            docs,
            epochs=1,
            lr=float(learning_rate) * (0.92 ** r_idx),
            optimizer=optimizer,
            holdout=eval_set,
        )
        after_loss = _eval_loss(model, eval_set)
        kept = True
        if after_loss > before_loss:
            _restore_model_state(model, saved)
            after_loss = before_loss
            kept = False
        history.append({
            "round": r_idx + 1,
            "focus_concepts": frontier["focus_concepts"],
            "bridge_count": len(frontier["bridge_lessons"]),
            "loss_before": round(before_loss, 6),
            "loss_after": round(after_loss, 6),
            "kept": kept,
        })

    final_loss = _eval_loss(model, eval_set)
    return {
        "schema_version": "skeleton.game_self_learn.self_play.v1",
        "rounds": rounds,
        "initial_eval_loss": round(initial_loss, 6),
        "final_eval_loss": round(final_loss, 6),
        "improved": final_loss <= initial_loss,
        "history": tuple(history),
    }
