"""Original English Pareto lessons for game logic, scale, and character coherence.

The lines are authored for this tree. They are not excerpts from commercial
games, manuals, or soundtracks. A byte-level loss on these lines is not a
gameplay-quality score, and nothing here promotes a checkpoint into service.

The graphic ladder is described in prose so this module can load on a tree
that does not carry the scale-ladder implementation.
"""
from __future__ import annotations

from typing import Any

CURRICULUM_VERSION = "skeleton.english_game_pareto.v1"
TRAIN_SCHEMA = "skeleton.english_game_pareto.train.v1"
PROBE_SCHEMA = "skeleton.application.english_game_first_install_probe.v1"

# (impact, reusable_across_games, implementation_effort, risk, text)
Lesson = tuple[int, int, int, int, str]

CURRICULUM: dict[str, dict[str, Any]] = {
    "game_logic": {
        "share": 16,
        "train": [
            (5, 5, 1, 1, "Keep one authoritative state record for the match. Input, rules, and combat resolve in that record, then animation reads it. Two systems must not both own health, position, or inventory."),
            (5, 4, 2, 1, "Buffer player input at the edge of the tick. The simulation consumes the buffer in order, clears it, and can replay the same buffer to the same state."),
            (4, 5, 2, 1, "Define win, loss, and the retry. A failure names the cause the player could have read, restores a legal state, and leaves the core verb available on the next attempt."),
            (4, 4, 2, 2, "Separate cosmetic reaction from rule outcome. Hit pause, camera shake, and footfalls may drop on a slow machine. Damage, knockback, and score may not."),
            (4, 4, 3, 1, "Write each rule as a precondition, a state edit, and a postcondition. If the postcondition fails, reject the edit and log the rule id instead of clamping silently."),
            (3, 4, 2, 1, "Give every interactive object one owner id, one collision layer, and one interaction verb. A second verb must name the first and the state flag that enables it."),
        ],
        "holdout": [
            "When two scripts both subtract health, pick a single writer, route the other through an event, and replay the last fixed tick to prove the total matches the rule.",
            "A puzzle saved during an animation stores the rule state rather than a decorative frame, and the loaded collision pose must agree with that state.",
        ],
    },
    "fixed_tick": {
        "share": 12,
        "train": [
            (5, 5, 1, 1, "Step the simulation at a fixed interval. Render may interpolate between ticks. A long frame runs several ticks or slows down, and it does not take one giant timestep."),
            (5, 4, 2, 1, "Cap the number of catch-up ticks per frame so a stall cannot spiral. Leftover time stays in the accumulator for the next frame."),
            (4, 5, 2, 1, "Physics, cooldowns, and spawn tables read the fixed interval. They do not read the display frame time."),
            (4, 4, 2, 1, "Record the tick index in the save. Loading resumes at that tick with the same random stream position."),
            (4, 3, 2, 2, "Animation frames are samples of state. Cancelling a swing on a given tick leaves the hurtbox off, even if the picture still shows the old pose for one interpolated frame."),
            (3, 4, 3, 2, "Peers exchange inputs for a tick and simulate that tick only after the input set is complete. Guessed motion is presentation until the agreed inputs arrive."),
        ],
        "holdout": [
            "If the display rate falls from sixty to twenty, travel distance per simulated second stays put because the tick, not the picture rate, advances movement.",
            "A replay stores the seed and the per-tick input words. Rebuilding the match from that file must match positions at the sampled ticks.",
        ],
    },
    "graphics_scale": {
        "share": 14,
        "train": [
            (5, 5, 1, 1, "Declare art tiers by exact halving from 65536 down through 32768, 16384, 8192, 4096, 2048, 1024, 512, 256, 128, 64, 32, 16, and 8. A plan names the tiers and allocates no 65536 buffer."),
            (5, 5, 2, 1, "Downscale 32768 to 16384 with divisor 2. The same integer-box rule drops 16384 to 8192. A chained halving walks the ladder one step at a time."),
            (5, 4, 2, 1, "Nearest upscale repeats source pixels and adds no new colors. Integer box downscale averages each block per channel and may create a mixed value. Keep those contracts distinct."),
            (4, 4, 2, 1, "A single pixel pass uses divisor 2, 4, 8, or 16 and only on an image that already fits the bounded pixel budget. Larger tiers stay as plans until a crop is chosen."),
            (4, 5, 2, 1, "Scale a character sheet by its variables first. Skin, eye, hair, cloth, and item names stay put when the raster gets coarser. The digest covers the variables, not the pixel count."),
            (3, 4, 2, 1, "Do not call box downscale neural super-resolution, and do not call a tier plan native hardware certification. It is a graphic scale ladder for authoring."),
        ],
        "holdout": [
            "Choosing a 32k source and a 16k target is a divisor of 2 on the ladder, and the planner returns that divisor without building either bitmap.",
            "Use nearest upscale when the palette must stay intact. Use a box average only when a mixed channel value is an accepted authoring choice.",
        ],
    },
    "character_coherence": {
        "share": 14,
        "train": [
            (5, 5, 1, 1, "Write the character once: skin tone, eye colour, hair colour, hair style, brow, lips, and body region. Every portrait and doll copies that sheet."),
            (5, 4, 2, 1, "A scale change may merge spatial chunks. The merge keeps every factor. Eye colour does not vanish because the raster got smaller."),
            (4, 5, 2, 1, "Hold a canon ledger of promises, scars, and tools. A later scene may not change eye colour or hair style unless the ledger records the cause."),
            (4, 4, 2, 1, "Name colours from a closed list. An unknown colour name fails the sheet instead of inventing a channel value during layout."),
            (4, 4, 2, 2, "Place hair, eyes, skin, clothing, and items in stable regions so a coarser grid still reads the same face. Priority keeps the eye when a block would otherwise collapse into hair."),
            (3, 4, 2, 1, "Coherence is the hash of the variables. Two grids of the same sheet match. Two sheets that differ by eye colour do not."),
        ],
        "holdout": [
            "If a winter scene adds a scarf, record the accessory on the sheet and leave skin, eyes, and hair untouched unless the scene states a reason.",
            "A close portrait and a distant sprite of the same person use one sheet. The distant sprite may use fewer pixels and must not rename the eye colour.",
        ],
    },
    "clothing_color": {
        "share": 12,
        "train": [
            (5, 5, 1, 1, "Clothing has a primary colour, a secondary colour, and a trim colour, plus a cloth name such as linen, wool, silk, canvas, or felt."),
            (5, 4, 2, 1, "Wear is fresh, worn, mended, faded, or weathered. Wear changes the micro pattern. It does not reassign the cloth or the wearer's skin."),
            (4, 4, 2, 1, "Leather is none, strap, belt, glove, or boot. Metal is none, buckle, ring, clasp, or pin. Each stays a named factor beside the cloth colours."),
            (4, 4, 2, 1, "Pattern is plain, stripe, check, hem, or speck, painted with named colours already on the sheet. A pattern may not introduce an unnamed dye."),
            (4, 3, 2, 1, "Palette names such as field, dusk, harbor, and hearth group an outfit. Swapping palette recolors within the closed names and keeps the garment pattern."),
            (3, 4, 2, 1, "Outline is its own named colour. A downscale may blend pixels, but the sheet still stores the outline name so the next raster can redraw it."),
        ],
        "holdout": [
            "A mended hem uses the trim colour for the repair mark and keeps the primary cloth colour on the rest of the garment.",
            "Faded wear may darken an edge toward the outline colour in the micro pattern while the stored primary colour stays the same token.",
        ],
    },
    "items": {
        "share": 10,
        "train": [
            (5, 5, 1, 1, "An item has a kind and a colour. Kinds include none, satchel, lantern, map, key, and charm. The kind is data, not a one-off sprite name."),
            (5, 4, 2, 1, "The same item kind on two characters can differ by item colour and still share collision and use rules."),
            (4, 4, 2, 1, "Attach an item to a body region. A lantern on the hand and a satchel on the torso do not overwrite hair or eye factors."),
            (4, 4, 2, 1, "Accessory is none, scarf, band, cloak-pin, or bead. It layers on clothing and remains when the item kind is none."),
            (4, 3, 2, 1, "Inventory rules reference item kind. The picture reads item colour. Losing the picture still leaves the kind in the state record."),
            (3, 4, 2, 2, "A key changes a door flag. The door check reads the kind, not the pixels, so a downscaled icon cannot lose the key."),
        ],
        "holdout": [
            "Swapping a copper lantern for a gold lantern changes item colour only. The hand region, the light rule, and the rest of the character sheet stay.",
            "A charm on the torso combines an accessory with an item kind. Clearing the charm clears those two fields and leaves eye colour and cloth alone.",
        ],
    },
    "pareto_scope": {
        "share": 12,
        "train": [
            (5, 5, 1, 1, "Spend the first build on the verb the player repeats, the feedback that makes that verb readable, and one recoverable failure. Cut the rest at the vertical slice."),
            (5, 4, 1, 1, "Rank a lesson by impact and reuse, then by effort and risk. A high-impact rule that many games share outranks a costly special case."),
            (4, 4, 2, 1, "One enemy role that can be read beats three roles that overlap. Add the second role after the first has a telegraph, a counter, and a rest."),
            (4, 4, 2, 1, "A portrait sheet with stable colours beats a gallery of unrelated faces. Lock skin, eyes, hair, and cloth before adding crowd variety."),
            (4, 3, 2, 1, "Tune the fixed tick and the input buffer before adding juice. Juice that hides a missed input is a lower-value change."),
            (3, 5, 1, 1, "Keep a scope cut line in writing. If a feature does not change the core verb, the readable failure, or the character sheet, it waits."),
        ],
        "holdout": [
            "The vertical slice is done when the core verb, its feedback, and one fair failure can be played from a fresh start without the deferred feature list.",
            "A new biome is lower priority than a broken retry. Repair the retry, then decide whether the biome changes a real decision.",
        ],
    },
    "gameplay": {
        "share": 10,
        "train": [
            (5, 5, 1, 1, "Telegraph a hazard on a tick the player can still answer. The answer is a verb already taught, with a recovery if the answer is late."),
            (5, 4, 2, 1, "Difficulty changes timings and counts inside the same rules. It does not silently change hitbox size without a readable tell."),
            (4, 4, 2, 1, "A combat beat has approach, threat, player choice, resolution, and a rest. Skipping the rest makes the next tell illegible."),
            (4, 4, 2, 1, "Traversal teaches a verb in a safe space, then mixes it with one hazard, then combines it with a second verb the player already owns."),
            (4, 3, 2, 1, "Rewards change a decision. A prize that opens a route or a build choice outranks a prize that only increments a number."),
            (3, 4, 2, 1, "The same seed and inputs reproduce the encounter. A designer tunes the data, not a one-off outcome that cannot be replayed."),
        ],
        "holdout": [
            "If players fail before they can see the tell, lengthen the telegraph or move the camera. Do not start by raising health.",
            "A boss with two readable phases is enough for the slice. A third phase waits until both earlier phases have a fair counter.",
        ],
    },
}


def pareto_score(lesson: Lesson) -> int:
    impact, reusable, effort, risk, _text = lesson
    return impact * reusable - effort - risk


def validate_curriculum() -> dict[str, int]:
    """Fail closed on duplicate lines, leaked holdouts, or a share that is not 100."""
    if sum(int(family["share"]) for family in CURRICULUM.values()) != 100:
        raise ValueError("family shares must sum to 100")
    train_texts: list[str] = []
    holdouts: list[str] = []
    for name, family in CURRICULUM.items():
        train = family["train"]
        held = family["holdout"]
        if len(train) < 5 or len(held) < 1:
            raise ValueError(f"{name} is missing train or holdout lessons")
        for row in train:
            if len(row) != 5:
                raise ValueError(f"{name} lesson shape is wrong")
            impact, reusable, effort, risk, text = row
            for score in (impact, reusable, effort, risk):
                if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                    raise ValueError(f"{name} score out of range")
            if not isinstance(text, str) or len(text) < 40:
                raise ValueError(f"{name} lesson text is too thin")
            train_texts.append(text)
        for text in held:
            if not isinstance(text, str) or len(text) < 40:
                raise ValueError(f"{name} holdout is too thin")
            holdouts.append(text)
    if len(train_texts) != len(set(train_texts)):
        raise ValueError("duplicate train lesson")
    if len(holdouts) != len(set(holdouts)):
        raise ValueError("duplicate holdout")
    train_blob = "\n".join(train_texts)
    for text in holdouts:
        if text in train_blob:
            raise ValueError("holdout leaked into train text")
    return {
        "families": len(CURRICULUM),
        "train": len(train_texts),
        "holdout": len(holdouts),
    }


def train_documents(*, family: str | None = None) -> tuple[str, ...]:
    validate_curriculum()
    if family is None:
        names = tuple(CURRICULUM)
    else:
        if family not in CURRICULUM:
            raise KeyError(family)
        names = (family,)
    return tuple(row[4] for name in names for row in CURRICULUM[name]["train"])


def holdout_documents(*, family: str | None = None) -> tuple[str, ...]:
    validate_curriculum()
    if family is None:
        names = tuple(CURRICULUM)
    else:
        if family not in CURRICULUM:
            raise KeyError(family)
        names = (family,)
    return tuple(text for name in names for text in CURRICULUM[name]["holdout"])


def logic_documents() -> tuple[str, ...]:
    """Game-logic subset used by a separate training pass."""
    return tuple(
        text
        for name in ("game_logic", "fixed_tick", "gameplay")
        for text in train_documents(family=name)
    )


def logic_holdouts() -> tuple[str, ...]:
    return tuple(
        text
        for name in ("game_logic", "fixed_tick", "gameplay")
        for text in holdout_documents(family=name)
    )


def train_english_game_pareto(
    *,
    epochs: int,
    learning_rate: float = 0.05,
    hidden_size: int = 32,
    seed: int = 17,
    gradient_clip: float = 1.0,
    documents: tuple[str, ...] | None = None,
    holdouts: tuple[str, ...] | None = None,
    model_id: str = "english-game-pareto",
) -> dict[str, Any]:
    """SGD-train a byte recurrent model. The caller keeps the returned weights.

    This does not write a canonical checkpoint and does not promote anything.
    """
    from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NumpyRecurrentLM

    train = documents if documents is not None else train_documents()
    held = holdouts if holdouts is not None else holdout_documents()
    if not train or not held:
        raise ValueError("train and holdout documents are required")
    model = NumpyRecurrentLM(
        model_id=model_id,
        config=NeuralLMConfig(hidden_size=hidden_size, seed=seed, dtype="float64"),
    )
    holdout_before = model.loss(held)
    receipt = model.train(
        train,
        epochs=epochs,
        learning_rate=learning_rate,
        gradient_clip=gradient_clip,
    )
    holdout_after = model.loss(held)
    return {
        "schema": TRAIN_SCHEMA,
        "curriculum_version": CURRICULUM_VERSION,
        "epochs": receipt.epochs,
        "learning_rate": receipt.learning_rate,
        "hidden_size": hidden_size,
        "seed": seed,
        "sequence_count": receipt.sequence_count,
        "token_count": receipt.token_count,
        "train_loss_initial": receipt.initial_loss,
        "train_loss_final": receipt.final_loss,
        "holdout_loss_before": holdout_before,
        "holdout_loss_after": holdout_after,
        "model_digest": model.model_digest,
        "model": model,
        "promotion": False,
        "canonical_replaced": False,
        "weights_loaded_from_service": False,
        "byte_loss_is_gameplay_quality": False,
        "perfect_builder_claimed": False,
    }


def first_install_english_game_capabilities() -> dict[str, Any]:
    """Read-only counts for a first install. Does not train or load weights."""
    counts = validate_curriculum()
    families = {}
    for name, family in CURRICULUM.items():
        ranked = max(family["train"], key=pareto_score)
        families[name] = {
            "share": family["share"],
            "train": len(family["train"]),
            "holdout": len(family["holdout"]),
            "top_pareto_score": pareto_score(ranked),
        }
    return {
        "schema": PROBE_SCHEMA,
        "curriculum_version": CURRICULUM_VERSION,
        "training_authorized": False,
        "promotion": False,
        "weights_loaded": False,
        "family_count": counts["families"],
        "train_document_count": counts["train"],
        "holdout_document_count": counts["holdout"],
        "logic_document_count": len(logic_documents()),
        "families": families,
        "scale_example": {
            "source_tier": 32768,
            "target_tier": 16384,
            "divisor": 2,
            "high_tier": 65536,
            "allocates_full_tier_buffer": False,
        },
        "closed_factors": [
            "skin_tone",
            "eye_color",
            "hair_color",
            "hair_style",
            "clothing_primary",
            "clothing_secondary",
            "clothing_trim",
            "item_kind",
            "item_color",
            "wear",
            "pattern",
        ],
        "imports_scale_ladder_module": False,
        "byte_loss_is_gameplay_quality": False,
        "perfect_builder_claimed": False,
    }


_COUNTS = validate_curriculum()
