"""Procedural offline capability challenges without accumulating training data.

Prompts are created only on operator request from rule-based scenarios
outside the immutable v1 train/validation/test corpus. Answers remain
inside this verifier; prompt exports never contain labels. The challenge
is NOT a secret benchmark nor a proof of real-world generalization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from scripts.training.generate_offline_foundations import ROOT, generate_example
from skeleton.ai.training.offline_foundations import FAMILIES, _json_equal, _strict_json, _oracle
from skeleton.ai.training.sparse_capability import CAPABILITIES


SCHEMA = "skeleton.offline_capability_challenge.v1"
MAX_PROBES_PER_MODE = 12
MAX_FILE_BYTES = 2_000_000


class ChallengeError(ValueError):
    """Invalid procedural capability challenge or prediction data."""


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def challenge_cases(*, seed: int = 1729, probes_per_mode: int = 1) -> tuple[dict[str, str], ...]:
    if type(seed) is not int or not 0 <= seed <= 100_000:
        raise ChallengeError("challenge seed must be a bounded integer")
    if (
        type(probes_per_mode) is not int
        or not 1 <= probes_per_mode <= MAX_PROBES_PER_MODE
    ):
        raise ChallengeError("challenge mode budget must be 1-12 examples")
    rows: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    groups: set[tuple[str, int]] = set()
    for family in FAMILIES:
        for variant, name in enumerate(CAPABILITIES[family]):
            for round_id in range(probes_per_mode):
                # Challenge indices never overlap pinned groups 0-19.
                # Modulo is limited to 9000 so range is 20-9019.
                group = 20 + ((seed * 17 + variant * 97 + round_id * 13) % 9000)
                if (family, group) in groups:
                    raise ChallengeError("procedural challenge repeated scenario group")
                groups.add((family, group))
                instruction, expected, oracle = generate_example(family, group, variant)
                if not _oracle(family, instruction, expected):
                    raise ChallengeError("generated challenge failed independent answer oracle")
                identity = f"challenge-{family}-{group:05}-{variant}"
                if identity in seen_ids:
                    raise ChallengeError("challenge identities are not unique")
                seen_ids.add(identity)
                rows.append({
                    "id": identity,
                    "family": family,
                    "capability_id": family + ":" + name,
                    "scenario_group": f"{family}-challenge-{group:05}",
                    "instruction": instruction,
                    "expected": expected,
                    "oracle": oracle,
                })
    if len(rows) != len(FAMILIES) * 3 * probes_per_mode:
        raise ChallengeError("procedural capability enumeration is incomplete")
    return tuple(rows)


def challenge_prompts(*, seed: int = 1729, probes_per_mode: int = 1) -> bytes:
    """Prompt-only JSONL: no 'response', 'answer', 'expected' or oracle labels."""
    rows = challenge_cases(seed=seed, probes_per_mode=probes_per_mode)
    fields = ("id", "family", "capability_id", "scenario_group", "instruction")
    return "".join(
        json.dumps({key: row[key] for key in fields}, separators=(",", ":"),
                   ensure_ascii=False) + "\n"
        for row in rows
    ).encode("utf-8")


def challenge_receipt(*, seed: int = 1729, probes_per_mode: int = 1) -> dict[str, Any]:
    prompts = challenge_prompts(seed=seed, probes_per_mode=probes_per_mode)
    return {
        "schema_version": SCHEMA,
        "seed": seed,
        "probes_per_mode": probes_per_mode,
        "modes_covered": 36,
        "families_covered": len(FAMILIES),
        "challenge_count": 36 * probes_per_mode,
        "prompt_only_sha256": _hash(prompts),
        "no_answer_labels_exported": True,
        "training_corpus_expanded": False,
        "training_data_mutated": False,
        "out_of_distribution_generalization_proven": False,
        "licensed_external_sources_loaded": False,
        "model_capability_qualified": False,
    }


def score_challenge(
    prediction_file: str | Path, *,
    seed: int = 1729, probes_per_mode: int = 1,
) -> dict[str, Any]:
    cases = challenge_cases(seed=seed, probes_per_mode=probes_per_mode)
    expected = {row["id"]: row for row in cases}
    file = Path(prediction_file)
    if file.is_symlink() or not file.is_file():
        raise ChallengeError("predictions must be a regular local JSONL file")
    if file.stat().st_size > MAX_FILE_BYTES:
        raise ChallengeError("predictions exceed evaluation size bound")
    with file.open("rb") as reader:
        payload = reader.read(MAX_FILE_BYTES + 1)
    if len(payload) > MAX_FILE_BYTES:
        raise ChallengeError("predictions exceed evaluation size bound")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ChallengeError("predictions must be UTF-8 JSONL") from exc
    lines = text.splitlines()
    if len(lines) != len(cases):
        raise ChallengeError("every procedural challenge must have one prediction")
    predictions: dict[str, str] = {}
    for line in lines:
        if len(line.encode("utf-8")) > 4096:
            raise ChallengeError("prediction row exceeds bounds")
        row = _strict_json(line)
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "prediction"}
            or not isinstance(row["id"], str)
            or not isinstance(row["prediction"], str)
            or len(row["prediction"]) > 400
            or row["id"] not in expected
            or row["id"] in predictions
        ):
            raise ChallengeError("invalid or duplicate prediction identity")
        predictions[row["id"]] = row["prediction"].strip()
    family_scores: dict[str, list[int]] = {name: [0, 0] for name in FAMILIES}
    mode_scores: dict[str, list[int]] = {
        family + ":" + mode: [0, 0]
        for family, modes in CAPABILITIES.items() for mode in modes
    }
    for row in cases:
        prediction = predictions[row["id"]]
        answer = row["expected"]
        if row["oracle"] in ("exact_json", "inventory_oracle", "json_exact"):
            try:
                correct = _json_equal(prediction, _strict_json(answer))
            except ValueError:
                correct = False
        else:
            correct = prediction == answer
        for bucket in (family_scores[row["family"]], mode_scores[row["capability_id"]]):
            bucket[0] += int(correct)
            bucket[1] += 1
    return {
        **challenge_receipt(seed=seed, probes_per_mode=probes_per_mode),
        "schema_version": "skeleton.offline_capability_challenge.score.v1",
        "prediction_sha256": _hash(payload),
        "correct": sum(x[0] for x in family_scores.values()),
        "total": len(cases),
        "by_family": {
            name: {"correct": score[0], "total": score[1]}
            for name, score in family_scores.items()
        },
        "by_mode": {
            name: {"correct": score[0], "total": score[1]}
            for name, score in mode_scores.items()
        },
        "model_capability_qualified": False,
        "training_corpus_expanded": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate on-demand, prompt-only challenges; never train on evaluation answers."
    )
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--per-mode", type=int, default=1)
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--export-prompts", type=Path,
                            help="write new prompt-only file; never export oracle answers")
    operations.add_argument("--score", type=Path,
                            help="score matching prediction JSONL by procedural oracle")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = challenge_receipt(seed=args.seed, probes_per_mode=args.per_mode)
        if args.export_prompts is not None:
            target = args.export_prompts.expanduser().absolute()
            if (
                target.is_symlink() or target.exists()
                or not target.parent.is_dir()
                or target.is_relative_to(ROOT.resolve())
            ):
                raise ChallengeError("challenge export must be an exclusive new local file")
            fd = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(fd, "wb") as writer:
                writer.write(challenge_prompts(seed=args.seed,
                                               probes_per_mode=args.per_mode))
                writer.flush()
                os.fsync(writer.fileno())
            receipt["exported_prompt_only_file"] = str(target)
        if args.score is not None:
            receipt = score_challenge(args.score, seed=args.seed,
                                      probes_per_mode=args.per_mode)
        print(json.dumps(receipt, sort_keys=True, ensure_ascii=False))
        return 0
    except (ChallengeError, ValueError, RuntimeError, OSError) as exc:
        print("offline capability challenge rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
