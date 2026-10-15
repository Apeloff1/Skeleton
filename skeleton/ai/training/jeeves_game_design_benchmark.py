"""Independent game-design answer probes for an unpromoted Jeeves candidate.

This benchmark uses entirely different prompts from the Pareto training
curriculum. It records *actual generations* from the pinned original and
candidate speaking models for human review. An optional keyword-coverage
heuristic is diagnostic only; it is neither a safety gate nor certification of
creative design, quality, generalization, or player enjoyment.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .jeeves_production_game_train import (
    MAX_BYTES, ProductionCheckpointError, _active_snapshot, _strict_json,
)

SCHEMA = "skeleton.jeeves.game_design_answer_benchmark.v1"
# Intentionally not in the training curriculum or its held-out loss split.
# (family, fresh design request, diagnostic concepts; no answer leakage)
BENCHMARK: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("mechanics", "Design a two-button climbing game where a mistake is recoverable.", ("input", "feedback", "recovery")),
    ("mechanics", "Plan a stealth game loop for players who prefer pacifist solutions.", ("choice", "detection", "objective")),
    ("mechanics", "What design would make an underwater dash predictable?", ("timing", "collision", "feedback")),
    ("narrative", "A rescued character later becomes the antagonist: preserve continuity.", ("motivation", "timeline", "choice")),
    ("narrative", "Plan three different endings without contradicting a shared history.", ("branch", "consequence", "canon")),
    ("narrative", "Outline a mystery whose clues can be discovered in any order.", ("clue", "deduction", "reveal")),
    ("npc", "Design a shopkeeper who recognizes prior help but misses unwitnessed crimes.", ("memory", "witness", "reaction")),
    ("npc", "Make a friendly companion recover after losing the player in a maze.", ("path", "recover", "distance")),
    ("npc", "Explain how two factions respond differently to the same diplomatic act.", ("reputation", "goals", "relationship")),
    ("world", "Make a compact archipelago explorable by foot and short ferry rides.", ("route", "landmark", "travel")),
    ("world", "Plan meaningful shortcuts in a changing city, preserving believable streets.", ("shortcut", "unlock", "navigation")),
    ("world", "Build an optional cave that changes its entrance after rainfall.", ("hazard", "state", "return")),
    ("economy", "Prevent a potion recipe from creating infinite currency.", ("source", "cost", "sink")),
    ("economy", "Balance three equally viable specializations across early and late play.", ("tradeoff", "progression", "reward")),
    ("economy", "Give fishing a purpose without making the player grind.", ("resource", "loop", "choice")),
    ("tooling", "Design an editor undo transaction that never corrupts a world file.", ("transaction", "version", "restore")),
    ("tooling", "Plan a deterministic cross-platform save migration.", ("schema", "validate", "compatibility")),
    ("tooling", "Reduce asset streaming memory on a low-end handheld.", ("memory", "load", "budget")),
    ("accessibility", "Make a color-coded puzzle usable to a color-blind player.", ("shape", "contrast", "cue")),
    ("accessibility", "Design an optional tutorial for a rhythm game without audio.", ("visual", "timing", "practice")),
    ("accessibility", "Let players disable camera shake without altering collision physics.", ("camera", "option", "physics")),
    ("review", "Critique a fun combat prototype that lacks usable save/load.", ("risk", "evidence", "release")),
    ("review", "Evaluate a proposed spiritual successor without copying a studio's art.", ("original", "rights", "expression")),
    ("review", "A demo looks beautiful but player-choice outcomes are untested. Review it.", ("evidence", "uncertain", "validation")),
)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _load(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file() or not 64 <= path.stat().st_size <= MAX_BYTES:
        raise ProductionCheckpointError("benchmark input must be a bounded, regular cortex checkpoint")
    raw = path.read_bytes()
    blob = _strict_json(raw)
    if not isinstance(blob.get("lms"), dict) or not isinstance(blob.get("own"), dict):
        raise ProductionCheckpointError("benchmark requires a full Jeeves cortex checkpoint")
    _active_snapshot(blob)
    if not isinstance(blob.get("bpe"), dict):
        raise ProductionCheckpointError("benchmark cortex tokenizer missing")
    return blob, hashlib.sha256(raw).hexdigest()


def _model_from(blob: dict[str, Any]) -> Any:
    from skeleton.cortex.bpe import BytePairEncoder
    from skeleton.cortex.transformer import TinyTransformer

    _, snap, _ = _active_snapshot(blob)
    if snap.get("kind") == "torch-stack":
        from skeleton.cortex.torch_lm import TorchTransformer
        model = TorchTransformer.from_snapshot(snap)
        if model.snapshot().get("state") != snap.get("state"):
            raise ProductionCheckpointError("restored torch weights differ from submitted checkpoint")
        return model
    model = TinyTransformer.from_snapshot(snap)
    model.bpe = BytePairEncoder.from_snapshot(blob["bpe"])
    if model.snapshot().get("E") != snap.get("E"):
        raise ProductionCheckpointError("restored native weights differ from submitted checkpoint")
    return model


def _simple_diagnostics(output: str, terms: tuple[str, ...]) -> dict[str, Any]:
    # Deliberately a NON-AUTHORITATIVE lexical probe; not a creativity score.
    lowered = output.casefold()
    matched = [term for term in terms if term in lowered]
    return {
        "diagnostic_terms_present": matched,
        "diagnostic_terms_total": len(terms),
        "unknown_tokens": sum(output.split().count(marker) for marker in ("__unk__", "<UNK>")),
        "printable_characters": sum(c.isprintable() for c in output),
        "requires_independent_review": True,
    }


def compare(parent: Path, candidate: Path, *, expected_parent_sha256: str) -> dict[str, Any]:
    """Verify parent lineage, then generate the same fresh prompts from both."""
    if parent.resolve() == candidate.resolve():
        raise ProductionCheckpointError("benchmark parent and candidate must be different files")
    original, parent_hash = _load(parent)
    updated, candidate_hash = _load(candidate)
    if parent_hash != expected_parent_sha256:
        raise ProductionCheckpointError("parent SHA differs from operator-pinned production checkpoint")
    parent_key, parent_snap, mouth = _active_snapshot(original)
    candidate_key, candidate_snap, candidate_mouth = _active_snapshot(updated)
    if (parent_key, mouth) != (candidate_key, candidate_mouth):
        raise ProductionCheckpointError("candidate switched Jeeves speaking model")
    if original.get("bpe") != updated.get("bpe"):
        raise ProductionCheckpointError("candidate changed production tokenizer")
    if any(original.get(k) != updated.get(k) for k in set(original) | set(updated)
           if k != parent_key):
        raise ProductionCheckpointError("candidate changed unrelated Jeeves state")
    if parent_snap == candidate_snap:
        raise ProductionCheckpointError("candidate did not change the selected weights")
    if type(candidate_snap.get("steps")) is not int or candidate_snap["steps"] <= parent_snap["steps"]:
        raise ProductionCheckpointError("candidate lacks additional optimizer steps")
    a = _model_from(original)
    b = _model_from(updated)
    observations = []
    for idx, (family, prompt, terms) in enumerate(BENCHMARK):
        seed = 71 + idx * 13
        before = str(a.decode(prompt, n=64, seed=seed))
        after = str(b.decode(prompt, n=64, seed=seed))
        observations.append({
            "family": family, "prompt": prompt, "seed": seed,
            "parent_output": before, "candidate_output": after,
            "parent_diagnostics": _simple_diagnostics(before, terms),
            "candidate_diagnostics": _simple_diagnostics(after, terms),
            "review_questions": [
                "Does the proposal describe a playable, actionable game design?",
                "Are cause-and-effect, player agency, and failure recovery clear?",
                "Does the answer respect world canon, technical constraints, and originality?",
                "Does it improve on the parent without merely echoing prompt words?",
            ],
            "independent_reviewer_score": None,
        })
    if hashlib.sha256(parent.read_bytes()).hexdigest() != parent_hash:
        raise ProductionCheckpointError("parent changed during comparison")
    result = {
        "schema_version": SCHEMA,
        "status": "needs_independent_game_design_review",
        "training_set_overlap": False,
        "family_count": len({row[0] for row in BENCHMARK}),
        "fresh_heldout_prompts": len(observations),
        "benchmark_digest": _digest(BENCHMARK),
        "parent_checkpoint_sha256": parent_hash,
        "candidate_checkpoint_sha256": candidate_hash,
        "active_model_key": parent_key,
        "produced_model_generations": True,
        "model_score_proves_game_quality": False,
        "human_review_complete": False,
        "production_promotion": False,
        "results": observations,
    }
    return result


def publish_review(report: dict[str, Any], output: Path) -> dict[str, Any]:
    from .jeeves_production_readiness import _save_new_private
    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")
    _save_new_private(output, payload + b"\n")
    return {**{key: value for key, value in report.items() if key != "results"},
            "report_path": str(output.resolve()), "report_sha256": hashlib.sha256(payload + b"\n").hexdigest()}


__all__ = ["BENCHMARK", "SCHEMA", "compare", "publish_review"]
