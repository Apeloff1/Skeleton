"""Pareto-weighted, original game-design curriculum for an existing local neural model.

Operator-only: no provider training, no promotion, and no modification to the
input checkpoint. This is a small byte-level RNN exercise, not an LLM quality
or general game-design proficiency claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

SCHEMA = "skeleton.game_pareto_training.v1"
# (impact, reusability, effort, risk, original prompt/completion)
# Five training cases + one held-out case per family. The highest value
# case in each family is the 20% high-leverage core.
CURRICULUM = {
    "mechanics": {
        "share": 30,
        "train": [
            (5, 5, 1, 1, "Player: Design a playable loop. Jeeves: Define input, visible feedback, a meaningful decision, a win or loss condition, and a repeatable next action."),
            (4, 4, 2, 1, "Player: What makes jumping fair? Jeeves: Define gravity, coyote time, jump buffering, collision rules, and readable landing feedback."),
            (4, 3, 2, 2, "Player: Design combat. Jeeves: Specify telegraphs, hit windows, recovery, damage limits, dodge costs, and counterplay."),
            (3, 3, 2, 1, "Player: Plan difficulty. Jeeves: Teach a safe pattern, combine learned patterns, offer recovery, and expose difficulty controls."),
            (3, 3, 3, 1, "Player: Define saving. Jeeves: Serialize authoritative state, version the schema, restore deterministically, and validate transitions."),
        ],
        "holdout": "Player: Why is this mechanic confusing? Jeeves: Check affordances, response latency, rule consistency, feedback clarity, and recoverable failure.",
    },
    "narrative": {
        "share": 25,
        "train": [
            (5, 5, 1, 1, "Player: Write a long game story. Jeeves: Maintain a canon ledger of characters, locations, timelines, promises, and consequences across every scene."),
            (4, 4, 2, 1, "Player: Structure a quest. Jeeves: Record prerequisites, stages, branching choices, failure handling, rewards, and downstream world changes."),
            (4, 3, 2, 1, "Player: Make decisions matter. Jeeves: Show immediate feedback, track flags, and pay off choices without contradicting established canon."),
            (3, 3, 2, 1, "Player: Plan a mystery. Jeeves: Seed clues, permit misleading leads, make deductions possible, and resolve required plot threads."),
            (3, 3, 3, 1, "Player: Revise dialogue. Jeeves: Preserve each speaker's voice, knowledge, motives, relationships, and historical continuity."),
        ],
        "holdout": "Player: Repair a contradictory chapter. Jeeves: Compare timeline and canon facts, locate the contradiction, repair the smallest dependency chain, and preserve established voice.",
    },
    "npc": {
        "share": 25,
        "train": [
            (5, 5, 1, 1, "Player: Build believable NPCs. Jeeves: Give each NPC goals, bounded knowledge, memory, relationships, schedules, reactions, and consistent dialogue."),
            (4, 4, 2, 1, "Player: Design faction reputation. Jeeves: Track witnessed actions, individual and faction reactions, decay rules, and justified consequences."),
            (4, 3, 2, 1, "Player: Make an escort NPC useful. Jeeves: Offer path awareness, safe following distance, recovery behavior, and nonblocking assistance."),
            (3, 3, 2, 1, "Player: Add civilian routines. Jeeves: Model sleep, work, travel, interruptions, and load-aware simulation outside the player's view."),
            (3, 3, 3, 2, "Player: Give enemies tactics. Jeeves: Use perceptible senses, goals, cover, retreat conditions, cooldowns, and difficulty-bounded reactions."),
        ],
        "holdout": "Player: NPC forgot an important promise. Jeeves: Restore the promise from canon-backed memory, update the relationship, and constrain future lines to the known facts.",
    },
    "world": {
        "share": 20,
        "train": [
            (5, 5, 1, 1, "Player: Design an explorable world. Jeeves: Connect landmarks, navigable routes, meaningful detours, readable hazards, and persistent state."),
            (4, 4, 2, 1, "Player: Build a region. Jeeves: Establish biome, traversal grammar, local history, encounters, resource loops, and visual identity."),
            (4, 3, 2, 1, "Player: Create shortcuts. Jeeves: Reward discovery, preserve spatial logic, and update traversal after unlocking the route."),
            (3, 3, 2, 1, "Player: Author a puzzle. Jeeves: Present legible clues, support experimentation, ensure a valid solution, and handle resets safely."),
            (3, 3, 3, 2, "Player: Optimize for old hardware. Jeeves: Bound update work, stream assets, reduce draw load, and preserve deterministic gameplay."),
        ],
        "holdout": "Player: The world feels empty. Jeeves: Add purpose-driven NPCs, encounters, interactions, secrets, and environmental storytelling without exceeding device budgets.",
    },
}


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _priority(row: tuple[int, int, int, int, str]) -> float:
    impact, reuse, effort, risk, _ = row
    return (impact * reuse) / (1 + effort + risk)


def plan() -> tuple[dict[str, object], tuple[str, ...], tuple[str, ...]]:
    """Build a deterministic 80/20 exposure plan (not a Pareto optimality proof)."""
    families = tuple(CURRICULUM)
    if sum(int(CURRICULUM[name]["share"]) for name in families) != 100:
        raise ValueError("game curriculum allocation must total 100")
    core: dict[str, str] = {}
    tails: dict[str, list[str]] = {}
    holdout: list[str] = []
    for family in families:
        group = CURRICULUM[family]
        rows = group["train"]
        if len(rows) != 5 or any(len(row) != 5 for row in rows):
            raise ValueError("each game family requires five authored training cases")
        if any(not isinstance(row[4], str) or not row[4].strip() for row in rows):
            raise ValueError("training text must be non-empty")
        ranked = sorted(rows, key=lambda row: (-_priority(row), row[4]))
        core[family] = ranked[0][4]
        tails[family] = [row[4] for row in ranked[1:]]
        holdout.append(str(group["holdout"]))
    tail_order = [tails[family][index] for index in range(4) for family in families]
    # One of five examples per family is the core (20% of distinct train data).
    # Each remaining example is exposed once and core examples occupy 80% of
    # the 80 scheduled examples. Category shares are 30/25/25/20 exactly.
    exposures = 5 * len(tail_order)
    targets = {family: exposures * int(CURRICULUM[family]["share"]) // 100 for family in families}
    if sum(targets.values()) != exposures:
        raise ValueError("curriculum allocation has fractional exposure counts")
    quotas = {family: targets[family] - len(tails[family]) for family in families}
    if min(quotas.values()) < 0:
        raise ValueError("curriculum cannot satisfy core exposure budget")
    total_core = sum(quotas.values())
    credit = dict.fromkeys(families, 0)
    remaining = quotas.copy()
    core_order: list[str] = []
    for _ in range(total_core):
        for family in families:
            credit[family] += quotas[family]
        family = max((name for name in families if remaining[name]), key=lambda name: (credit[name], -families.index(name)))
        core_order.append(core[family])
        remaining[family] -= 1
        credit[family] -= total_core
    documents: list[str] = []
    for index, tail in enumerate(tail_order):
        documents.extend(core_order[index * 4 : (index + 1) * 4])
        documents.append(tail)
    if len(documents) != exposures or len(core_order) != 4 * len(tail_order):
        raise ValueError("game curriculum does not meet its 80/20 budget")
    summary: dict[str, object] = {
        "schema_version": SCHEMA,
        "source": "original_synthetic_in_repo",
        "curriculum_digest": _digest(CURRICULUM),
        "distinct_training_cases": 20,
        "distinct_core_cases": 4,
        "heldout_cases": len(holdout),
        "scheduled_exposures": exposures,
        "core_exposures": total_core,
        "tail_exposures": len(tail_order),
        "family_exposures": targets,
        "epochs_are_full_schedule_passes": True,
        "model_promotion": False,
    }
    return summary, tuple(documents), tuple(holdout)


def train(args: argparse.Namespace) -> dict[str, object]:
    from .artifact import load_local_model_artifact, write_local_model_artifact
    from .neural import NumpyRecurrentLM

    if args.base_artifact is None or args.output is None:
        raise ValueError("--base-artifact and --output are required for training")
    source = Path(args.base_artifact).expanduser()
    destination = Path(args.output).expanduser()
    if source.resolve() == destination.resolve():
        raise ValueError("refusing to overwrite the parent model")
    if destination.exists() or destination.is_symlink():
        raise ValueError("candidate destination already exists")
    if not destination.parent.is_dir():
        raise ValueError("candidate output directory must already exist")
    if args.epochs < 1 or args.epochs > 10:
        raise ValueError("bounded training epochs must be between 1 and 10")
    if not 0 < args.learning_rate <= 0.1:
        raise ValueError("learning rate must be in (0, 0.1]")
    if not 0 <= args.max_heldout_regression <= 1:
        raise ValueError("heldout regression budget must be in [0, 1]")

    summary, documents, holdout = plan()
    loaded = load_local_model_artifact(source)
    model = loaded.model
    if not isinstance(model, NumpyRecurrentLM):
        raise ValueError("Pareto exercise supports only existing NumPy recurrent checkpoints; GGUF and transformer weights are not changed")
    parent_digest = model.model_digest
    before = model.loss(holdout)
    receipt = model.train(documents, epochs=args.epochs, learning_rate=args.learning_rate, gradient_clip=1.0)
    after = model.loss(holdout)
    report: dict[str, object] = {
        **summary,
        "parent_model_digest": parent_digest,
        "candidate_model_digest": model.model_digest,
        "model_id": model.model_id,
        "heldout_loss_before": before,
        "heldout_loss_after": after,
        "train_loss_before": receipt.initial_loss,
        "train_loss_after": receipt.final_loss,
        "learning_rate": args.learning_rate,
        "epochs": args.epochs,
        "training_receipt_digest": receipt.digest,
        "candidate_promoted": False,
    }
    if not math.isfinite(after) or after > before * (1 + args.max_heldout_regression):
        report["status"] = "rejected_heldout_regression"
        report["artifact_written"] = False
        return report
    written = write_local_model_artifact(model, destination)
    report.update(
        status="candidate_trained",
        artifact_written=True,
        output_path=str(destination.resolve()),
        artifact_sha256=written.artifact_sha256,
        artifact_bytes=written.artifact_bytes,
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="Show curriculum without loading or training a model")
    parser.add_argument("--base-artifact", type=Path, help="Existing native recurrent model artifact JSON")
    parser.add_argument("--output", type=Path, help="New candidate artifact JSON; parent is never overwritten")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=0.005)
    parser.add_argument("--max-heldout-regression", type=float, default=0.10)
    args = parser.parse_args(argv)
    try:
        if args.plan:
            result = plan()[0]
        else:
            result = train(args)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if result.get("status") != "rejected_heldout_regression" else 3
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
