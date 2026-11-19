"""Assemble reviewed, original game-design work into leak-resistant train/eval JSONL.

Input is authored material exported by the game studio and explicitly reviewed
by a human. No crawling, LLM-generated "approval", rights inference or model
training occurs here. All records from one source project stay in the SAME
split, preventing scene-by-scene copies of a single game from masquerading as
independent held-out designs.

The builder stages output privately, validates it with the actual production
dataset loader, and exclusively publishes train/eval files before their
manifest. Existing datasets cannot be overwritten.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

from .jeeves_production_game_train import ProductionCheckpointError, _strict_json
from .jeeves_game_corpus import (
    FAMILIES, MIN_TRAIN_PER_FAMILY, MIN_HOLDOUT_PER_FAMILY,
    MAX_DATASET_BYTES, _check_rights, _ID, _text, load_approved_corpus, SCHEMA,
)

INTAKE_SCHEMA = "skeleton.jeeves.reviewed_game_design_intake.v1"
MAX_INTAKE_EXAMPLES = 10000
MAX_PROJECTS = 4096
MAX_INTake_BYTES = 64 * 1024 * 1024
MIN_QUALITY_NOTE_LENGTH = 24


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _validated_examples(intake: Path) -> tuple[list[dict[str, Any]], str]:
    if intake.is_symlink() or not intake.is_file():
        raise ProductionCheckpointError("reviewed game corpus intake must be a regular file")
    if not 16 <= intake.stat().st_size <= MAX_INTake_BYTES:
        raise ProductionCheckpointError("reviewed game corpus intake outside bounded file size")
    raw = intake.read_bytes()
    rows: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    project_ids: set[str] = set()
    for index, line in enumerate(raw.splitlines(), 1):
        if index > MAX_INTAKE_EXAMPLES:
            raise ProductionCheckpointError("reviewed corpus exceeds 10000 examples")
        if not line.strip():
            raise ProductionCheckpointError("reviewed corpus cannot have blank JSONL lines")
        row = _strict_json(line)
        if row.get("schema_version") != INTAKE_SCHEMA:
            raise ProductionCheckpointError("unknown game design intake record schema")
        rid = row.get("id")
        project = row.get("source_project_id")
        if not isinstance(rid, str) or not _ID.fullmatch(rid) or rid in record_ids:
            raise ProductionCheckpointError("reviewed game examples need unique safe IDs")
        if not isinstance(project, str) or not _ID.fullmatch(project):
            raise ProductionCheckpointError("reviewed examples need a valid source project ID")
        if row.get("family") not in FAMILIES:
            raise ProductionCheckpointError("reviewed game example has unknown domain")
        _text(row.get("prompt"), label="prompt", minimum=10, maximum=4096)
        _text(row.get("answer"), label="answer", minimum=20, maximum=12000)
        _check_rights(row)
        if row.get("quality_approved") is not True:
            raise ProductionCheckpointError("game design example has no affirmative human quality approval")
        reviewer = row.get("quality_reviewer_id")
        note = row.get("quality_review_note")
        if not isinstance(reviewer, str) or not 3 <= len(reviewer.strip()) <= 128:
            raise ProductionCheckpointError("human quality reviewer identity missing")
        if not isinstance(note, str) or len(note.strip()) < MIN_QUALITY_NOTE_LENGTH:
            raise ProductionCheckpointError("quality review must include actionable evidence notes")
        record_ids.add(rid)
        project_ids.add(project)
        if len(project_ids) > MAX_PROJECTS:
            raise ProductionCheckpointError("reviewed game corpus exceeds project group budget")
        rows.append(row)
    if not rows:
        raise ProductionCheckpointError("reviewed corpus has no examples")
    return rows, _sha(raw)


def _by_project(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["source_project_id"]].append(row)
    return dict(grouped)


def partition_projects(
    rows: list[dict[str, Any]], *, seed: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Deterministic project-grouped holdout with all eight domain quotas."""
    if not isinstance(seed, str) or not 3 <= len(seed) <= 128:
        raise ProductionCheckpointError("partition seed must be explicitly identified")
    grouped = _by_project(rows)
    train_remain = Counter(row["family"] for row in rows)
    eval_counts: Counter[str] = Counter()
    heldout_projects: set[str] = set()
    # Global ordering means a project used by multiple domains cannot land
    # on different sides of the held-out evaluation boundary.
    projects = sorted(
        grouped, key=lambda name: (_sha((seed + "|" + name).encode("utf-8")), name),
    )
    for project in projects:
        counts = Counter(row["family"] for row in grouped[project])
        contributes = any(eval_counts[family] < MIN_HOLDOUT_PER_FAMILY for family in counts)
        leaves_training = all(
            train_remain[family] - count >= MIN_TRAIN_PER_FAMILY
            for family, count in counts.items()
        )
        if contributes and leaves_training:
            heldout_projects.add(project)
            for family, amount in counts.items():
                eval_counts[family] += amount
                train_remain[family] -= amount
    if any(
        eval_counts[family] < MIN_HOLDOUT_PER_FAMILY or
        train_remain[family] < MIN_TRAIN_PER_FAMILY for family in FAMILIES
    ):
        raise ProductionCheckpointError(
            "insufficient independent project groups to make eight-domain train/eval partitions"
        )
    training = [row for row in rows if row["source_project_id"] not in heldout_projects]
    heldout = [row for row in rows if row["source_project_id"] in heldout_projects]
    return training, heldout, {
        "train_project_count": len(grouped) - len(heldout_projects),
        "heldout_project_count": len(heldout_projects),
        "heldout_project_ids_sha256": _sha(json.dumps(
            sorted(heldout_projects), separators=(",", ":")
        ).encode("utf-8")),
        "heldout_example_count": len(heldout),
        "train_example_count": len(training),
        "independent_project_partition": True,
    }


def build(
    *, intake: Path, destination: Path, prefix: str, partition_seed: str,
    rights_review_id: str,
) -> dict[str, Any]:
    if not isinstance(prefix, str) or not _ID.fullmatch(prefix) or len(prefix) > 80:
        raise ProductionCheckpointError("output prefix must be a safe 3-80 character slug")
    if not isinstance(rights_review_id, str) or not 3 <= len(rights_review_id.strip()) <= 128:
        raise ProductionCheckpointError("an external rights review ID is mandatory")
    if destination.is_symlink() or not destination.is_dir():
        raise ProductionCheckpointError("corpus output directory must be an existing regular directory")
    source_rows, source_sha = _validated_examples(intake)
    if intake.resolve().parent.resolve() == destination.resolve():
        raise ProductionCheckpointError("reviewed intake and published datasets need separate directories")
    training, heldout, partition = partition_projects(source_rows, seed=partition_seed)
    filenames = {
        "train": prefix + "-train.jsonl",
        "heldout": prefix + "-heldout.jsonl",
        "manifest": prefix + "-manifest.json",
    }
    targets = {name: destination / filename for name, filename in filenames.items()}
    if any(target.exists() or target.is_symlink() for target in targets.values()):
        raise ProductionCheckpointError("destination already contains a dataset with this prefix")

    with tempfile.TemporaryDirectory(prefix=".jeeves-corpus-", dir=destination) as folder:
        staging = Path(folder)
        for key, group in (("train", training), ("heldout", heldout)):
            with (staging / filenames[key]).open("xb") as output:
                for row in group:
                    published = {
                        "id": row["id"],
                        "source_project_id": row["source_project_id"],
                        "split": key,
                        "family": row["family"],
                        "prompt": row["prompt"].strip(),
                        "answer": row["answer"].strip(),
                        "rights": row["rights"],
                        "quality_reviewer_id": row["quality_reviewer_id"],
                        "quality_approved": True,
                        "quality_review_note": row["quality_review_note"],
                    }
                    output.write((json.dumps(
                        published, ensure_ascii=False, sort_keys=True,
                        allow_nan=False, separators=(",", ":"),
                    ) + "\n").encode("utf-8"))
                output.flush()
                os.fsync(output.fileno())
            os.chmod(staging / filenames[key], 0o600)

        manifest = {
            "schema_version": SCHEMA,
            "rights_reviewed": True,
            "review_id": rights_review_id.strip(),
            "train_file": filenames["train"],
            "heldout_file": filenames["heldout"],
            "train_sha256": _sha((staging / filenames["train"]).read_bytes()),
            "heldout_sha256": _sha((staging / filenames["heldout"]).read_bytes()),
            "source_schema_version": INTAKE_SCHEMA,
            "approved_intake_sha256": source_sha,
            "project_partition": partition,
            "rights_declarations_need_operator_verification": True,
            "generation_does_not_constitute_legal_review": True,
        }
        with (staging / filenames["manifest"]).open("xb") as output:
            output.write((json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, indent=2,
                allow_nan=False,
            ) + "\n").encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        os.chmod(staging / filenames["manifest"], 0o600)
        # Production loader supplies the final acceptance authority. It
        # catches long copied passages, benchmark contamination and invalid
        # rights metadata even when the builder's source fields passed.
        _train, _held, validated = load_approved_corpus(staging / filenames["manifest"])
        published: list[Path] = []
        try:
            for key in ("train", "heldout", "manifest"):
                os.link(staging / filenames[key], targets[key])
                published.append(targets[key])
        except Exception:
            for target in published:
                target.unlink(missing_ok=True)
            raise
    return {
        "status": "reviewed_game_dataset_published_candidate_for_rights_confirmation",
        "paths": {key: str(value.resolve()) for key, value in targets.items()},
        "manifest_sha256": _sha(targets["manifest"].read_bytes()),
        "train_sha256": manifest["train_sha256"],
        "heldout_sha256": manifest["heldout_sha256"],
        "approved_intake_sha256": source_sha,
        "rights_review_id": rights_review_id.strip(),
        "project_partition": partition,
        "loader_acceptance": validated,
        "production_weights_modified": False,
        "training_started": False,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--partition-seed", required=True)
    parser.add_argument("--rights-review-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = build(
            intake=args.intake, destination=args.output_dir, prefix=args.prefix,
            partition_seed=args.partition_seed, rights_review_id=args.rights_review_id,
        )
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:400]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
