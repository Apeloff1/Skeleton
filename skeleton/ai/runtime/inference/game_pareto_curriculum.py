"""Original, versioned game-development cases for local 80/20 learning.

No scraped games, proprietary scripts, trademarks, ROMs, or copyrighted game
dialogue are included. These are authored, generic micro-lessons, not a claim
that memorizing them creates a capable game-design agent.
"""

from __future__ import annotations

# Each row: (impact, reusable_across_games, implementation_effort, risk, text).
# A family provides exactly five train cases, including one highest-impact core,
# and two independently written held-out examples.
CURRICULUM_VERSION = "skeleton.game_pareto_curriculum.v2"

CURRICULUM = {
    "mechanics": {
        "share": 20,
        "train": [
            (5, 5, 1, 1, "User: Design the core play loop. Jeeves: Specify player input, immediate feedback, a meaningful choice, changing game state, success conditions, failure recovery, and the reason to try again."),
            (5, 4, 2, 1, "User: Make movement satisfying. Jeeves: Define acceleration, stopping distance, collision, jump buffering, coyote time, camera follow, and tuning limits."),
            (4, 4, 2, 1, "User: Design fair combat. Jeeves: Telegraph attacks, provide counterplay, bound hit stun, define recovery windows, and prevent unavoidable damage."),
            (4, 3, 3, 1, "User: Plan replayable encounters. Jeeves: Combine legible enemy roles, changing terrain, explicit objectives, escalating patterns, and a cooldown between challenges."),
            (3, 4, 2, 1, "User: Create a save system. Jeeves: Serialize authoritative world state, version records, restore atomically, reject invalid states, and avoid losing progress on failure."),
        ],
        "holdout": [
            "User: A jump frequently feels unfair. Jeeves: Inspect collision, input sampling, animation and physics alignment, forgiving timing windows, and landing feedback before changing difficulty.",
            "User: Players cannot tell why they lost. Jeeves: Trace cause and effect, expose readable hazard cues, provide a recovery route, and validate identical outcomes from identical states.",
        ],
    },
    "narrative": {
        "share": 20,
        "train": [
            (5, 5, 1, 1, "User: Write a branching story. Jeeves: Keep a canon ledger for characters, timelines, places, motivations, promises, revelations, and consequences; verify every new scene against it."),
            (5, 4, 2, 1, "User: Structure a quest chain. Jeeves: Declare prerequisites, available choices, world-state transitions, rewards, failure paths, and downstream consequences."),
            (4, 4, 2, 1, "User: Make dialogue consequential. Jeeves: Track knowledge boundaries, relationship flags, player commitments, immediate feedback, and later payoffs without changing an established voice."),
            (4, 3, 3, 1, "User: Create a mystery. Jeeves: Plant discoverable clues, allow multiple deductions, distinguish red herrings from false premises, and resolve required plot threads."),
            (3, 4, 2, 1, "User: Edit a long story. Jeeves: Build scene receipts, compare chapter chronology, propagate minimal canon changes, and preserve character-specific speech patterns."),
        ],
        "holdout": [
            "User: A late chapter conflicts with an earlier choice. Jeeves: Locate the originating choice flag, inspect affected scenes, revise the smallest set of downstream dependencies, and retain established character voice.",
            "User: Multiple endings contradict the same fact. Jeeves: Separate shared canon from branch-specific world state and verify each ending against its reachable prerequisites.",
        ],
    },
    "npc": {
        "share": 15,
        "train": [
            (5, 5, 1, 1, "User: Build a credible NPC. Jeeves: Give the character goals, limited knowledge, persistent memories, relationships, daily routines, and reactions justified by witnessed events."),
            (5, 4, 2, 1, "User: Design faction reputation. Jeeves: Record witnesses, reputation changes, individual trust, faction allegiance, forgiveness conditions, and reactions to rumors versus evidence."),
            (4, 4, 2, 1, "User: Improve companion behavior. Jeeves: Provide safe following, useful assistance, obstacle recovery, nonblocking movement, and transparent command feedback."),
            (4, 3, 3, 1, "User: Generate civilian routines. Jeeves: Model work, travel, rest, interruptions, and event reactions with lower-cost updates when offscreen."),
            (3, 3, 2, 2, "User: Design tactical opponents. Jeeves: Use perceptible sensory inputs, bounded planning, role coordination, cooldowns, retreats, and difficulty-dependent reaction times."),
        ],
        "holdout": [
            "User: A character forgets a promise. Jeeves: Recover the source promise, bound what the character could know, update its state, and keep later dialogue aligned with the repair.",
            "User: Every villager responds alike. Jeeves: Separate shared event knowledge from individual goals, history, fear, social ties, and available actions.",
        ],
    },
    "world": {
        "share": 15,
        "train": [
            (5, 5, 1, 1, "User: Design an explorable region. Jeeves: Link landmarks, readable roads, shortcuts, optional detours, traversal abilities, local stories, and persistent discoveries."),
            (5, 4, 2, 1, "User: Create environmental storytelling. Jeeves: Align landmarks, damaged objects, written hints, NPC behavior, and quest state with world history."),
            (4, 4, 2, 1, "User: Build branching navigation. Jeeves: Preserve spatial logic while providing fast routes, scenic paths, hazardous tradeoffs, return trips, and hidden unlocks."),
            (4, 3, 3, 1, "User: Author reusable puzzles. Jeeves: Define cues, states, invalid moves, one guaranteed solution, alternative legitimate strategies, and recoverable resets."),
            (3, 3, 2, 2, "User: Increase world activity. Jeeves: Add interactions where players make decisions, reuse systemic routines, and respect visibility and device budgets."),
        ],
        "holdout": [
            "User: The map is large but dull. Jeeves: Check meaningful traversal, interlocking activities, readable landmarks, environmental detail, and opportunities for discovery rather than adding empty space.",
            "User: A secret route breaks progression. Jeeves: Reconcile route prerequisites, state flags, encounter dependencies, and the reachable world graph.",
        ],
    },
    "economy": {
        "share": 10,
        "train": [
            (5, 5, 1, 1, "User: Design meaningful progression. Jeeves: Tie rewards to player decisions, keep upgrade tradeoffs visible, prevent runaway scaling, and preserve alternate viable builds."),
            (5, 4, 2, 1, "User: Balance resources. Jeeves: Specify sources, sinks, capacity, scarcity, replenishment, and safeguards against infinite loops."),
            (4, 4, 2, 1, "User: Design crafting. Jeeves: Show recipe prerequisites, discoverable ingredients, item utility, substitution rules, and inventory constraints."),
            (4, 3, 3, 2, "User: Add vendors. Jeeves: Give prices transparent drivers, restock rules, faction effects, and protection against trivial arbitrage."),
            (3, 3, 2, 1, "User: Build optional skills. Jeeves: Give each advancement a cost, playstyle benefit, counterweight, and a viable route without that advancement."),
        ],
        "holdout": [
            "User: A crafting exploit generates free money. Jeeves: Audit acquisition costs, sell values, stack rounding, recursion, and constraints before changing price tables.",
            "User: One ability makes every build obsolete. Jeeves: Compare marginal utility, stacking, counterplay, and opportunity costs across equivalent encounters.",
        ],
    },
    "tooling": {
        "share": 10,
        "train": [
            (5, 5, 1, 1, "User: Generate game code. Jeeves: State engine assumptions, input and output contracts, authoritative state ownership, performance limits, and a small integration path."),
            (5, 4, 2, 1, "User: Build a modular editor. Jeeves: Keep typed data contracts, version migrations, undo history, deterministic serialization, and recoverable error messages."),
            (4, 4, 2, 1, "User: Author reusable assets. Jeeves: Track original source, resolution, palette, animation state, dependencies, and target platform constraints."),
            (4, 3, 3, 1, "User: Diagnose a gameplay bug. Jeeves: Reproduce minimal input and state, isolate the failing subsystem, repair the causal defect, and confirm no canon or save regression."),
            (3, 3, 2, 1, "User: Ship to low-end hardware. Jeeves: Budget CPU, memory, storage, draw calls, and loading time while preserving input responsiveness."),
        ],
        "holdout": [
            "User: A game saves but cannot load older projects. Jeeves: Compare schema versions, design explicit migrations, preserve originals, and reject ambiguous states rather than silently discarding fields.",
            "User: Editor actions are nondeterministic. Jeeves: Identify implicit ordering, unstable seeds, noncanonical serialization, and frame timing dependencies.",
        ],
    },
    "accessibility": {
        "share": 5,
        "train": [
            (5, 5, 1, 1, "User: Make play accessible. Jeeves: Support remappable controls, readable contrast, text scaling, adjustable challenge, captions, and alternatives to color-only cues."),
            (5, 4, 2, 1, "User: Design a tutorial. Jeeves: Introduce one affordance at a time, give safe practice, use immediate feedback, and allow repeatable help."),
            (4, 4, 2, 1, "User: Prevent motion discomfort. Jeeves: Offer camera shake reduction, stable reticles, controllable field of view, and options for motion effects."),
            (4, 3, 2, 1, "User: Make an interface readable. Jeeves: Group actions by importance, minimize input steps, preserve focus visibility, and support keyboard or controller navigation."),
            (3, 3, 2, 1, "User: Localize quests. Jeeves: Separate UI strings from logic, preserve semantic placeholders, allow text expansion, and audit cultural references."),
        ],
        "holdout": [
            "User: A player cannot distinguish quest markers. Jeeves: Add shapes, text, contrast and configurable cues instead of relying on hue alone.",
            "User: Tutorial prompts overwhelm beginners. Jeeves: Break instruction into small demonstrations and gate new concepts on demonstrated understanding.",
        ],
    },
    "review": {
        "share": 5,
        "train": [
            (5, 5, 1, 1, "User: Critique a proposed game. Jeeves: Check player agency, fairness, originality, continuity, production feasibility, performance, and stated design goals before approving."),
            (5, 4, 2, 1, "User: Review a claim. Jeeves: Distinguish measured results, assumptions, and unresolved uncertainty; request evidence rather than fabricating a pass."),
            (4, 4, 2, 1, "User: Resolve feedback conflict. Jeeves: Separate player segments, compare evidence quality, and propose measurable alternatives without sacrificing core intent."),
            (4, 3, 3, 1, "User: Protect originality. Jeeves: Prefer original systems and expression, check asset provenance, avoid direct copying, and flag rights uncertainty for review."),
            (3, 3, 2, 1, "User: Gate a release. Jeeves: Require playable build evidence, save compatibility, performance bounds, accessibility checks, and documented unresolved defects."),
        ],
        "holdout": [
            "User: A reviewer says the demo feels polished but gameplay is unverified. Jeeves: Separate subjective impressions from reproducible evidence and withhold quality certification.",
            "User: A design resembles a famous franchise too closely. Jeeves: Preserve the underlying genre function while replacing protected expressive details and requesting rights review if uncertain.",
        ],
    },
}
