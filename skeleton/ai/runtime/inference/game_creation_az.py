"""Original A-to-Z game-creation lessons, plus adjacent production topics.

The lines are written for this tree. They are not excerpts from commercial
games, manuals, or soundtracks. Held-out lines are measurement only. A lower
byte loss is not a gameplay-quality score and does not promote a checkpoint.
"""
from __future__ import annotations

from typing import Any

CURRICULUM_VERSION = "skeleton.game_creation_az.v1"
PROBE_SCHEMA = "skeleton.application.game_creation_az_probe.v1"

Lesson = tuple[int, int, int, int, str]

# Pipeline order is the creation path: intent, play, people, place, systems,
# presentation, production, and release. Shares sum to 100.
CURRICULUM: dict[str, dict[str, Any]] = {
    "intent": {
        "share": 8,
        "train": [
            (5, 5, 1, 1, "Start a game by naming the player, the repeated verb, and the feeling that verb should leave. Write the sentence before opening a content tool."),
            (5, 4, 1, 1, "Pick one audience and one session length. A five-minute puzzle and a forty-hour sim do not share a scope plan."),
            (4, 5, 2, 1, "Write the fantasy in playable terms: what the player decides, what the world answers, and what remains true after the answer."),
            (4, 4, 2, 1, "List the adjacent jobs this game needs: interface writing, sound, animation, save migration, and a build receipt. Assign an owner before production art."),
            (3, 4, 1, 1, "Cut any feature that does not change the verb, the readable failure, or the character sheet. Record the cut in the scope line."),
        ],
        "holdout": [
            "A pitch that cannot name the repeated verb is still a theme, and the next writing task is that verb.",
            "Session length is a design constraint. It decides how much tutorial, travel, and failure recovery the slice may contain.",
        ],
    },
    "core_loop": {
        "share": 8,
        "train": [
            (5, 5, 1, 1, "Build the loop as input, immediate feedback, a state change, a success test, and a failure that can be retried from a legal state."),
            (5, 4, 2, 1, "Prove the loop on one screen. Ten identical inputs must produce the same outcome before a second room exists."),
            (4, 5, 2, 1, "Log state before and after every action so a failed attempt can be replayed from the numbers rather than from memory."),
            (4, 4, 2, 1, "Keep one alternate route viable. A single upgrade must not be mandatory for a fair clear of the slice."),
            (3, 4, 2, 2, "Add a shop, a story, or a companion only after the loop survives repeated attempts without a manual reset."),
        ],
        "holdout": [
            "If the loop needs a designer sitting beside the player, the state log is missing and the slice is not ready for content.",
            "Success and failure both need a visible cause. A flag that flips offscreen is not yet a finished loop.",
        ],
    },
    "controls": {
        "share": 7,
        "train": [
            (5, 5, 1, 1, "Sample the pad once at the start of the tick. Store directions, pressed, held, and released. Gameplay reads that snapshot."),
            (5, 4, 2, 1, "Put remapping in one table from physical control to action. Menus, tutorials, and play share the table."),
            (4, 4, 2, 1, "Tune acceleration, stop distance, and buffering on the fixed tick. Do not tune them from the display frame time."),
            (4, 3, 2, 1, "Give every verb a readable cancel. A late press during recovery should fail clearly rather than queue a hidden action."),
            (3, 4, 2, 1, "Record the input snapshot in the replay so a reported bug can be run again without the original hardware."),
        ],
        "holdout": [
            "A second read of the device mid-tick can disagree with the first and make a jump depend on call order.",
            "Controller and keyboard should enter the same action table. Scattering device names through collision code breaks ports.",
        ],
    },
    "character": {
        "share": 8,
        "train": [
            (5, 5, 1, 1, "Write the person once: skin tone, eye colour, hair colour, hair style, brow, lips, and body region. Every portrait copies that sheet."),
            (5, 4, 2, 1, "Clothing stores a primary colour, a secondary colour, a trim, a cloth, a wear, and a pattern. Wear changes marks, not the cloth token."),
            (4, 5, 2, 1, "An item has a kind and a colour and a body region. Changing the colour leaves the kind in the state record."),
            (4, 4, 2, 1, "Accessory is its own field. Adding a scarf records the accessory and leaves eyes, skin, and hair unless the ledger states a cause."),
            (3, 4, 2, 1, "Unknown colour names fail the sheet. Layout does not invent a channel value to hide a typo."),
        ],
        "holdout": [
            "A crowd variant copies the sheet and changes one named field. It does not repaint the face with an unnamed dye.",
            "Dialogue portraits and the doll in the world read one sheet so eye colour cannot drift between scenes.",
        ],
    },
    "world": {
        "share": 7,
        "train": [
            (5, 5, 1, 1, "A level is a route with a landmark, a risk, a shortcut, and a reason to return. Empty space is not a level."),
            (5, 4, 2, 1, "Teach traversal in a safe space, then with one hazard, then combined with a verb the player already owns."),
            (4, 4, 2, 1, "Lock a door with a state flag. The art shows closed, opening, and open. The flag, not the picture, decides passage."),
            (4, 3, 2, 1, "Place readable silhouettes at the decision point. A hazard that reads after the hit frame is late."),
            (3, 4, 2, 2, "Secrets add a route that still respects the progression graph. A skip that voids a required flag is a defect."),
        ],
        "holdout": [
            "Landmarks should be nameable by a player who has walked the space once. If they cannot, the layout is not readable yet.",
            "Streaming a room must not drop the door flag. The room can arrive late. The state cannot.",
        ],
    },
    "combat": {
        "share": 7,
        "train": [
            (5, 5, 1, 1, "A combat beat has approach, a telegraph, a player choice, a resolution, and a rest so the next tell can be seen."),
            (5, 4, 2, 1, "Telegraph on a tick the player can still answer with a verb already taught. Late answers get a recovery, not a lock."),
            (4, 4, 2, 1, "Difficulty changes timings and counts inside the same rules. It does not silently resize a hitbox."),
            (4, 3, 2, 2, "One readable enemy role beats three overlapping roles. The second role waits until the first has a counter and a rest."),
            (3, 4, 2, 1, "Separate cosmetic shake from damage. Shake may drop on a slow machine. Damage and score may not."),
        ],
        "holdout": [
            "If players fail before the tell is visible, lengthen the tell or move the camera before changing health totals.",
            "Two readable boss phases are enough for a slice. A third phase waits until each earlier phase has a fair counter.",
        ],
    },
    "economy": {
        "share": 6,
        "train": [
            (5, 5, 1, 1, "A reward changes a route or a build. A number that changes no decision is the weaker prize."),
            (5, 4, 2, 1, "Name sources, sinks, and a capacity for every resource. Reject a loop that mints the resource from nothing."),
            (4, 4, 2, 1, "Crafting shows the recipe, the ingredients, and a use. The inventory check reads item kind, not the icon pixels."),
            (4, 3, 2, 1, "Prices have a driver: scarcity, faction, or restock. A vendor that buys and sells the same stack at a profit is a defect."),
            (3, 4, 2, 1, "Progression offers a cost and a counterweight. A path that skips the cost must still be playable."),
        ],
        "holdout": [
            "An exploit that turns a craft into free money is audited at the source and the sink before any price table is rewritten.",
            "Item colour is presentation. The economy rule keys on item kind so a recolor cannot mint a new resource.",
        ],
    },
    "story": {
        "share": 7,
        "train": [
            (5, 5, 1, 1, "Keep a ledger of people, what each knows, promises, places, times, and facts true on every branch."),
            (5, 4, 2, 1, "A choice is data: who decided, what they knew, and which flags flipped. Write one payoff and one path that skips it."),
            (4, 4, 2, 1, "A branch may add a fact. It may not silently rewrite a shared fact. Repair the smallest set of later lines."),
            (4, 3, 2, 1, "Keep each speaker's vocabulary stable. Names, injuries, and deaths are ledger entries."),
            (3, 4, 2, 2, "Required clues can be found in the world. A required thread has a resolution on every reachable ending."),
        ],
        "holdout": [
            "A character does not repeat a secret they never witnessed. Knowledge boundaries are data, not a tone of voice.",
            "When two endings disagree on a shared fact, fix the ledger before writing more epilogue lines.",
        ],
    },
    "art_scale": {
        "share": 7,
        "train": [
            (5, 5, 1, 1, "Declare art tiers by halving from 65536 through 32768 and 16384 down to 8. A plan names tiers and allocates no 65536 buffer."),
            (5, 4, 2, 1, "Downscale 32768 to 16384 with divisor 2. Nearest upscale repeats pixels and adds no colours. A box average may mix a channel."),
            (4, 5, 2, 1, "Name animation by state: idle, move, act, hurt, recover. The state flag, not the frame, is authoritative."),
            (4, 4, 2, 1, "Give hazards a silhouette that reads at play distance. Test contrast in the level lighting, with a shape cue besides hue."),
            (3, 4, 2, 1, "Original pixel art records its palette, resolution, and author. A file with no source does not enter the shipping build."),
        ],
        "holdout": [
            "A coarser raster keeps the sheet names for skin, eyes, hair, cloth, and items. Pixel count is not the identity.",
            "Scale2x and nearest are palette tools. They are not a certificate that the picture is native console hardware.",
        ],
    },
    "audio": {
        "share": 6,
        "train": [
            (5, 5, 1, 1, "Original music uses a scale, a seed, and a tempo. Notes are frequency steps. They are not a copied commercial score."),
            (5, 4, 2, 1, "Convert tempo to a quarter as 60 divided by beats per minute. Chip frames per step follow the simulation, not the wall clock."),
            (4, 4, 2, 1, "A missed frame must not skip the input a musical accent was marking. Sound is a listener. The tick is the clock."),
            (4, 3, 2, 1, "Effects for pickup, hit, jump, and failure are short synthesized envelopes. Each effect maps to one state change."),
            (3, 4, 2, 1, "Keep a bus for music, effects, and voice. A muted bus still lets the simulation advance."),
        ],
        "holdout": [
            "Melody timing is an absolute beat from the index and the tempo. It is not a chain of equal gaps that drift.",
            "Voice lines reference the ledger id of the speaker. A swapped portrait does not silently take another person's line.",
        ],
    },
    "interface": {
        "share": 6,
        "train": [
            (5, 5, 1, 1, "The interface shows the next legal verb, the resource that limits it, and the failure if the verb is refused."),
            (5, 4, 2, 1, "Do not use colour as the only channel. Add a shape, a word, or a position the player can name."),
            (4, 4, 2, 1, "Remappable controls, readable contrast, captions, and a way to reduce shake belong in the first playable settings page."),
            (4, 3, 2, 1, "Focus order is data. Keyboard, pad, and pointer move through the same actions."),
            (3, 4, 2, 1, "A tutorial introduces one affordance, gives a safe try, and can be repeated. It does not narrate systems the slice lacks."),
        ],
        "holdout": [
            "If a player cannot tell which object accepts the verb, the interface failed before the difficulty did.",
            "Text that will be translated keeps a stable id and room to grow. The logic reads the id, not the English width.",
        ],
    },
    "simulation": {
        "share": 7,
        "train": [
            (5, 5, 1, 1, "Step the simulation on a fixed interval. Render may interpolate. A long frame runs several ticks or slows. It does not take one giant step."),
            (5, 4, 2, 1, "Cap catch-up ticks. Leftover time stays in the accumulator. Physics and cooldowns read the fixed interval."),
            (4, 5, 2, 1, "One owner writes health, position, and inventory. Other systems emit events that owner applies."),
            (4, 4, 2, 1, "A save stores the tick index, the random stream position, and the authoritative record. Load rejects a record that fails its checks."),
            (3, 4, 2, 2, "Rules are a precondition, an edit, and a postcondition. A failed postcondition rejects the edit and logs the rule id."),
        ],
        "holdout": [
            "Display rate can fall from sixty to twenty without changing travel per simulated second, because the tick advances movement.",
            "A replay stores the seed and the per-tick inputs. Rebuilding the match must match positions at the sampled ticks.",
        ],
    },
    "tools": {
        "share": 6,
        "train": [
            (5, 5, 1, 1, "Content is typed data with a version. The editor writes that data, keeps undo, and refuses a file it cannot migrate."),
            (5, 4, 2, 1, "Every asset row records source, palette, resolution, state names, and target limits. The build copies from that registry."),
            (4, 4, 2, 1, "A pipeline step names its inputs, its command, and the hash of its output. A second run from the same inputs must match or explain why not."),
            (4, 3, 2, 1, "Validate references before packaging. A missing animation state or an unknown item kind fails the build."),
            (3, 4, 2, 1, "Keep the previous good build. A bad export rolls back by hash, not by searching a chat log."),
        ],
        "holdout": [
            "An editor action that depends on click timing is not ready. The same data edit must serialize to the same bytes.",
            "Migrations keep the old file. They write a new version beside it and refuse to guess missing fields.",
        ],
    },
    "playtest": {
        "share": 5,
        "train": [
            (5, 5, 1, 1, "Ask four questions: could the player tell what to do, could they avoid the failure, did the world show the cause, and did a choice matter later."),
            (5, 4, 2, 1, "A failed playtest names the rule or the read, not the player's taste. The next task is that defect."),
            (4, 4, 2, 1, "Balance changes timings, counts, and costs. It records the encounter seed so the same fight can be replayed."),
            (4, 3, 2, 1, "Watch the first thirty seconds without helping. Notes taken while talking over the player hide the missing tell."),
            (3, 4, 1, 1, "High-value tests can come back negative. A check that can only confirm a favorite idea is a weak use of time."),
        ],
        "holdout": [
            "If every tester misses the same door, the door's read is the defect. Adding a hint line is the second option, not the first.",
            "Difficulty complaints after an unread telegraph are camera and timing work. They are not an invitation to inflate health.",
        ],
    },
    "ship": {
        "share": 5,
        "train": [
            (5, 5, 1, 1, "A release names the source revision, the asset registry digest, the target, the commands, and the artifact hash."),
            (5, 4, 2, 1, "The frame budget is split across input, simulation, collision, audio, and the draw. Measure it on the slow target."),
            (4, 4, 2, 1, "Ship the slice when the verb, its feedback, and one fair failure run from a fresh start. Deferred work stays written down."),
            (4, 3, 2, 2, "A patch carries a migration and a rollback hash. It does not overwrite the last good save without a version check."),
            (3, 4, 2, 1, "Unresolved defects stay on the receipt. Polish notes do not replace a playable start, a save round-trip, or the measured frame time."),
        ],
        "holdout": [
            "A folder of loose files is not a release. The receipt has to point at one hash and the commands that produced it.",
            "Cutting a feature to meet the frame budget is recorded. Hiding the miss by skipping input is not an acceptable cut.",
        ],
    },
}


def pareto_score(lesson: Lesson) -> int:
    impact, reusable, effort, risk, _text = lesson
    return impact * reusable - effort - risk


def validate_curriculum() -> dict[str, int]:
    if sum(int(family["share"]) for family in CURRICULUM.values()) != 100:
        raise ValueError("family shares must sum to 100")
    train_texts: list[str] = []
    holdouts: list[str] = []
    for name, family in CURRICULUM.items():
        train = family["train"]
        held = family["holdout"]
        if len(train) < 5 or len(held) < 1:
            raise ValueError(f"{name} is missing lessons")
        for impact, reusable, effort, risk, text in train:
            for score in (impact, reusable, effort, risk):
                if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                    raise ValueError(f"{name} score out of range")
            if not isinstance(text, str) or len(text) < 40:
                raise ValueError(f"{name} lesson is too thin")
            train_texts.append(text)
        for text in held:
            if not isinstance(text, str) or len(text) < 40:
                raise ValueError(f"{name} holdout is too thin")
            holdouts.append(text)
    if len(train_texts) != len(set(train_texts)) or len(holdouts) != len(set(holdouts)):
        raise ValueError("duplicate lesson")
    blob = "\n".join(train_texts)
    for text in holdouts:
        if text in blob:
            raise ValueError("holdout leaked into A-Z train text")
    return {"families": len(CURRICULUM), "train": len(train_texts), "holdout": len(holdouts)}


def train_documents() -> tuple[str, ...]:
    validate_curriculum()
    return tuple(row[4] for family in CURRICULUM.values() for row in family["train"])


def holdout_documents() -> tuple[str, ...]:
    validate_curriculum()
    return tuple(text for family in CURRICULUM.values() for text in family["holdout"])


def first_install_game_creation_probe() -> dict[str, Any]:
    """Read-only A-to-Z counts. Does not train or load weights."""
    counts = validate_curriculum()
    return {
        "schema": PROBE_SCHEMA,
        "curriculum_version": CURRICULUM_VERSION,
        "training_authorized": False,
        "promotion": False,
        "weights_loaded": False,
        "family_count": counts["families"],
        "train_document_count": counts["train"],
        "holdout_document_count": counts["holdout"],
        "pipeline": list(CURRICULUM),
        "covers_game_creation_a_to_z": True,
        "adjacent_topics": [
            "interface",
            "audio",
            "accessibility",
            "tools",
            "localization",
            "build_receipt",
            "frame_budget",
        ],
        "byte_loss_is_gameplay_quality": False,
        "perfect_builder_claimed": False,
    }


_COUNTS = validate_curriculum()
