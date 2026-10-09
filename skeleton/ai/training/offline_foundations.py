"""Deterministic, auditable original-synthetic curriculum for offline training.

Ownership stays with Skeleton's existing training DatasetRegistry, rights, and
candidate promotion gates. This module only validates and adapts examples;
it cannot produce or automatically promote production model weights.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

SCHEMA = "skeleton.synthetic_offline_curriculum.v1"
DATASET_ID = "skeleton-offline-foundations"
VERSION = "1.0.0"
SEED = 1729
FAMILIES = (
    "integer_arithmetic", "grid_navigation", "aabb_collision",
    "discrete_motion", "finite_state", "inventory", "source_grounding",
    "json_extraction", "game_mechanics", "offline_authority",
    "event_chronology", "text_normalization",
)
SPLITS = {"train": range(0, 14), "validation": range(14, 17), "test": range(17, 20)}
COUNTS = {"train": 504, "validation": 108, "test": 108}
ORACLES = {
    "integer_arithmetic": "exact_integer",
    "grid_navigation": "exact_json",
    "aabb_collision": "geometry_half_open",
    "discrete_motion": "exact_integer",
    "finite_state": "fsm_oracle",
    "inventory": "inventory_oracle",
    "source_grounding": "source_constrained",
    "json_extraction": "json_exact",
    "game_mechanics": "rule_execution",
    "offline_authority": "local_policy",
    "event_chronology": "event_order",
    "text_normalization": "normalization_rule",
}
FIELDS = {"id", "family", "group_id", "split", "instruction", "response", "oracle"}
FILES = ("train.jsonl", "validation.jsonl", "test.jsonl", "train_corpus.txt")
MAX_INPUT_BYTES = 2_000_000
MAX_LINE_BYTES = 4096


class SyntheticCurriculumError(ValueError):
    """A training sample, source identity or split fails admission."""


def _strict_json(raw: str) -> Any:
    def object_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SyntheticCurriculumError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise SyntheticCurriculumError("nonfinite JSON value: " + value)

    try:
        return json.loads(raw, object_pairs_hook=object_hook,
                          parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise SyntheticCurriculumError("invalid JSON in synthetic dataset") from exc


def _read_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SyntheticCurriculumError("dataset path must be a real regular file")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise SyntheticCurriculumError("dataset file exceeds input limit")
    with path.open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise SyntheticCurriculumError("dataset input changed or exceeded limit")
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_equal(actual: str, expected: Mapping[str, Any]) -> bool:
    parsed = _strict_json(actual)
    return (
        isinstance(parsed, dict)
        and json.dumps(parsed, sort_keys=True) == json.dumps(expected, sort_keys=True)
    )


def _oracle(family: str, instruction: str, response: str) -> bool:
    """Independent deterministic answer oracle; no trained model is involved."""
    try:
        if family == "integer_arithmetic":
            add = re.search(r"Calculate (\d+) \+ (\d+)", instruction)
            points = re.search(r"has (\d+) points and gains (\d+)", instruction)
            times = re.search(r"Calculate (\d+) \* (\d+)", instruction)
            if add or points:
                x, y = map(int, (add or points).groups())
                return response == str(x + y)
            if times:
                x, y = map(int, times.groups())
                return response == str(x * y)
            return False

        if family == "grid_navigation":
            pos = re.search(r"starts at \((-?\d+),(-?\d+)\)", instruction)
            move = re.search(r"Move (right|left|east) (\d+) and (up|down|south) (\d+)", instruction)
            if not pos or not move:
                return False
            x, y = map(int, pos.groups())
            horizontal, distance_x, vertical, distance_y = move.groups()
            x += int(distance_x) * (1 if horizontal in ("right", "east") else -1)
            y += int(distance_y) * (1 if vertical == "up" else -1)
            return _json_equal(response, {"x": x, "y": y})

        if family == "aabb_collision":
            box = re.search(
                r"A=\[(-?\d+),(-?\d+),(-?\d+),(-?\d+)\), "
                r"B=\[(-?\d+),(-?\d+),(-?\d+),(-?\d+)\)", instruction
            )
            if not box:
                return False
            ax1, ay1, ax2, ay2, bx1, by1, bx2, by2 = map(int, box.groups())
            if not (ax1 < ax2 and ay1 < ay2 and bx1 < bx2 and by1 < by2):
                return False
            overlaps = ax1 < bx2 and bx1 < ax2 and ay1 < by2 and by1 < ay2
            return response == ("overlap" if overlaps else "no-overlap")

        if family == "discrete_motion":
            match = re.search(
                r"x=(-?\d+), constant velocity=(-?\d+) cells/tick, elapsed=(\d+) ticks",
                instruction,
            )
            return bool(match) and response == str(
                int(match[1]) + int(match[2]) * int(match[3])
            )

        if family == "finite_state":
            match = re.search(r"State=(\w+); event=(\w+)", instruction)
            if not match:
                return False
            state, event = match.groups()
            permitted = {
                ("idle", "start"): "running",
                ("running", "pause"): "paused",
                ("paused", "resume"): "running",
                ("running", "stop"): "idle",
                ("paused", "stop"): "idle",
            }
            return response == permitted.get((state, event), state)

        if family == "inventory":
            stock = re.search(r"has (\d+) potions \(max (\d+)\)", instruction)
            action = re.search(r"(Add|Remove) (\d+)", instruction)
            if not stock or not action:
                return False
            count, maximum = map(int, stock.groups())
            verb, quantity = action.groups()
            qty = int(quantity)
            accepted = count + qty <= maximum if verb == "Add" else qty <= count
            remaining = (
                count + qty if accepted and verb == "Add" else
                count - qty if accepted else count
            )
            return _json_equal(response, {"accepted": accepted, "remaining": remaining})

        if family == "source_grounding":
            evidence = re.search(
                r"Source (note-unit-\d+): invented beacon unit-\d+ "
                r"blinks every (\d+) frames\.", instruction,
            )
            if not evidence:
                return False
            note, frames = evidence.groups()
            if "battery capacity?" in instruction:
                return response == "Not stated in " + note + "."
            if "How often does the beacon blink?" in instruction:
                return response == "Every " + frames + " frames. [" + note + "]"
            return False

        if family == "json_extraction":
            match = re.search(r"Object=(\{[^\n]+\})\.", instruction)
            if not match:
                return False
            source = _strict_json(match[1])
            if not isinstance(source, dict):
                return False
            if "Deal 4 health damage" in instruction:
                expected = {"hp": source["hp"] - 4}
            elif "Extract its position" in instruction:
                expected = source["position"]
            elif "Extract its entity and shield" in instruction:
                expected = {"entity": source["entity"], "shield": source["shield"]}
            else:
                return False
            return _json_equal(response, expected)

        if family == "game_mechanics":
            health = re.search(r"enemy has (\d+) HP and a hit deals (\d+)", instruction)
            coins = re.search(r"(\d+) coins collected, (\d+) points per coin", instruction)
            cooldown = re.search(r"cooldown=(\d+) frames, elapsed=(\d+)", instruction)
            if health:
                return response == str(max(0, int(health[1]) - int(health[2])))
            if coins:
                return response == str(int(coins[1]) * int(coins[2]))
            if cooldown:
                return response == str(max(0, int(cooldown[1]) - int(cooldown[2])))
            return False

        if family == "offline_authority":
            if "Request read selected /scenes/" in instruction:
                return response == "ALLOW"
            if "Request fetch https://" in instruction or "Request launch /tools/" in instruction:
                return response == "DENY"
            return False

        if family == "event_chronology":
            match = re.search(
                r"boot tick (\d+), ready tick (\d+), checkpoint tick (\d+)", instruction
            )
            if not match:
                return False
            boot, ready, checkpoint = map(int, match.groups())
            if not boot < ready < checkpoint:
                return False
            if "List event names" in instruction:
                return response == "boot,ready,checkpoint"
            if "elapsed ticks" in instruction:
                return response == str(checkpoint - boot)
            if "latest?" in instruction:
                return response == "checkpoint"
            return False

        if family == "text_normalization":
            match = re.search(r'Normalize synthetic log "([^"]+)"', instruction)
            if not match or "preserve underscores in identifiers" not in instruction:
                return False
            normalized = re.sub(r"[,;!/]", " ", match[1].lower())
            return response == " ".join(normalized.split())

    except (KeyError, TypeError, ValueError, IndexError, SyntheticCurriculumError):
        return False
    return False


def _split_rows(root: Path, manifest: Mapping[str, Any], split: str) -> tuple[dict[str, Any], ...]:
    spec = manifest["files"][split]
    if (
        not isinstance(spec, dict) or set(spec) !=
        {"file", "sha256", "records", "byte_count", "groups"}
        or spec["file"] != split + ".jsonl"
        or type(spec["records"]) is not int or spec["records"] != COUNTS[split]
        or type(spec["groups"]) is not int
        or spec["groups"] != len(FAMILIES) * len(SPLITS[split])
    ):
        raise SyntheticCurriculumError("invalid split file contract: " + split)
    raw = _read_bytes(root / spec["file"])
    if (
        _sha(raw) != spec["sha256"]
        or len(raw) != spec["byte_count"]
        or not raw.endswith(b"\n")
    ):
        raise SyntheticCurriculumError("dataset split checksum or length mismatch: " + split)
    try:
        lines = raw.decode("utf-8", "strict").splitlines()
    except UnicodeError as exc:
        raise SyntheticCurriculumError("dataset split is not UTF-8") from exc
    if len(lines) != COUNTS[split] or any(
        len(line.encode("utf-8")) > MAX_LINE_BYTES for line in lines
    ):
        raise SyntheticCurriculumError("dataset row count or line size mismatch")
    rows = tuple(_strict_json(line) for line in lines)
    return rows


def _corpus_bytes(rows: tuple[Mapping[str, Any], ...]) -> bytes:
    return "".join(
        "<user>\n" + row["instruction"] + "\n<assistant>\n"
        + row["response"] + "\n<end>\n"
        for row in rows
    ).encode("utf-8")


def validate_curriculum(directory: str | Path) -> dict[str, Any]:
    """Fail closed on wrong labels, duplicates, leaks, or altered file contents."""
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise SyntheticCurriculumError("dataset directory is not regular")
    allowed_files = set(FILES) | {"manifest.json"}
    if {x.name for x in root.iterdir()} != allowed_files:
        raise SyntheticCurriculumError("unexpected or missing dataset file")
    manifest = _strict_json(_read_bytes(root / "manifest.json").decode("utf-8", "strict"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != SCHEMA
        or manifest.get("dataset_id") != DATASET_ID
        or manifest.get("version") != VERSION
        or manifest.get("seed") != SEED
        or manifest.get("source_kind") != "original_algorithmic_synthetic"
        or manifest.get("families") != list(FAMILIES)
        or manifest.get("record_count") != 720
        or manifest.get("record_fields") != sorted(FIELDS)
        or manifest.get("family_record_count") != {name: 60 for name in FAMILIES}
        or manifest.get("rights", {}).get("permitted_uses") != ["training", "evaluation"]
        or manifest.get("rights", {}).get("independent_legal_review_performed") is not False
        or set(manifest.get("files", {})) != set(SPLITS) | {"train_corpus"}
    ):
        raise SyntheticCurriculumError("synthetic curriculum manifest is invalid")
    all_ids: set[str] = set()
    prompt_ids: set[str] = set()
    allocated_groups: set[str] = set()
    datasets: dict[str, tuple[dict[str, Any], ...]] = {}
    for split in ("train", "validation", "test"):
        rows = _split_rows(root, manifest, split)
        expected_ids = [
            "ofv1-" + family + "-" + f"{group:02}" + "-" + str(variant)
            for family in FAMILIES for group in SPLITS[split] for variant in range(3)
        ]
        if [item.get("id") for item in rows if isinstance(item, dict)] != expected_ids:
            raise SyntheticCurriculumError("dataset rows are missing, duplicated or reordered")
        family_groups = Counter()
        for row in rows:
            if not isinstance(row, dict) or set(row) != FIELDS:
                raise SyntheticCurriculumError("invalid row schema")
            family, group, instruction, response = (
                row["family"], row["group_id"], row["instruction"], row["response"]
            )
            if (
                family not in FAMILIES or row["split"] != split
                or row["oracle"] != ORACLES[family]
                or group not in {
                    family + "-scenario-" + f"{i:02}" for i in SPLITS[split]
                }
                or not isinstance(instruction, str) or not isinstance(response, str)
                or not instruction.strip() or not response.strip()
                or len(instruction) > 1024 or len(response) > 400
                or "\x00" in instruction or "\x00" in response
            ):
                raise SyntheticCurriculumError("synthetic row failed shape/length checks")
            if row["id"] in all_ids or instruction in prompt_ids:
                raise SyntheticCurriculumError("exact duplicate identity or prompt")
            all_ids.add(row["id"])
            prompt_ids.add(instruction)
            family_groups[group] += 1
            if not _oracle(family, instruction, response):
                raise SyntheticCurriculumError("synthetic answer failed independent oracle: " + row["id"])
        if any(count != 3 for count in family_groups.values()):
            raise SyntheticCurriculumError("incomplete scenario variants")
        if allocated_groups & family_groups.keys():
            raise SyntheticCurriculumError("scenario leakage between splits")
        allocated_groups.update(family_groups)
        datasets[split] = rows
    if len(all_ids) != 720 or len(allocated_groups) != 240:
        raise SyntheticCurriculumError("wrong total examples or scenarios")
    expected_corpus = _corpus_bytes(datasets["train"])
    corpus_spec = manifest["files"]["train_corpus"]
    if (
        not isinstance(corpus_spec, dict)
        or set(corpus_spec) != {"file", "sha256", "records", "byte_count"}
        or corpus_spec["file"] != "train_corpus.txt"
        or corpus_spec["records"] != COUNTS["train"]
    ):
        raise SyntheticCurriculumError("invalid train-only corpus contract")
    actual_corpus = _read_bytes(root / "train_corpus.txt")
    if (
        actual_corpus != expected_corpus
        or _sha(actual_corpus) != corpus_spec["sha256"]
        or len(actual_corpus) != corpus_spec["byte_count"]
    ):
        raise SyntheticCurriculumError("training corpus differs from admitted train split")
    return {
        "schema_version": "skeleton.synthetic_offline_curriculum.audit.v1",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "split_counts": dict(COUNTS),
        "groups": len(allocated_groups),
        "oracle_verified_rows": len(all_ids),
        "scenario_leakage": 0,
        "exact_duplicate_prompts": 0,
        "train_only_export_sha256": _sha(expected_corpus),
        "manifest_sha256": _sha(_read_bytes(root / "manifest.json")),
        "synthetic_only": True,
        "rights_independently_verified": False,
        "template_generalization_established": False,
        "weights_promoted": False,
    }


def register_with_training_registry(directory: str | Path, registry: Any) -> str:
    """Register verified synthetic train/eval data in the existing data plane.

    Explicit source rights and critical quality gates are required. This is
    dataset admission only; no training job is run and no weights are promoted.
    """
    from skeleton.ai.runtime.training.data import (
        DataQualityReport, DataQualityRule, DatasetManifest, DatasetSplit,
        IngestEnvelope, SyntheticDataReceipt,
    )
    from skeleton.ai.runtime.training.trainer import corpus_digest

    report = validate_curriculum(directory)
    root = Path(directory)
    manifest = _strict_json(_read_bytes(root / "manifest.json").decode("utf-8"))
    corpus = _read_bytes(root / "train_corpus.txt")
    envelope = IngestEnvelope.from_bytes(
        source_id="original-synthetic:" + DATASET_ID + ":" + VERSION,
        payload=corpus,
        parser_version=SCHEMA,
        classification="public",
        rights=("training", "evaluation"),
        trusted=True,
    )
    registry.register_ingest(envelope)
    splits = (
        DatasetSplit("train", corpus_digest((corpus.decode("utf-8"),)), 504),
        DatasetSplit("validation", manifest["files"]["validation"]["sha256"], 108),
        DatasetSplit("test", manifest["files"]["test"]["sha256"], 108),
    )
    training_manifest = DatasetManifest(
        dataset_id=DATASET_ID,
        version=VERSION,
        splits=splits,
        source_ingest_digests=(envelope.content_digest,),
        classification="public",
        permitted_uses=("training", "evaluation"),
        retention_class="operator-managed-synthetic-v1",
        parser_versions=(SCHEMA,),
        synthetic_receipt=SyntheticDataReceipt(
            generator_id="skeleton.offline_foundations.original_algorithmic.v1",
            generator_config_digest=_sha(
                json.dumps(
                    {"seed": SEED, "families": list(FAMILIES), "splits": dict(COUNTS)},
                    sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ),
            source_dataset_digests=(),
            seed=SEED,
            generated_record_count=720,
        ),
        pii_present=False,
        contamination_labels=(),
    )
    digest = registry.register_dataset(training_manifest)
    rules = (
        DataQualityRule("full-row-oracle", "oracle_verified_rows", "==", 720),
        DataQualityRule("no-leaked-scenarios", "scenario_leakage", "==", 0),
        DataQualityRule("no-duplicate-prompts", "exact_duplicate_prompts", "==", 0),
        DataQualityRule("training-count", "training_records", "==", 504),
    )
    metrics = {
        "oracle_verified_rows": float(report["oracle_verified_rows"]),
        "scenario_leakage": float(report["scenario_leakage"]),
        "exact_duplicate_prompts": float(report["exact_duplicate_prompts"]),
        "training_records": 504.0,
    }
    registry.record_quality(DataQualityReport.evaluate(digest, rules, metrics))
    registry.require_training_ready(digest)
    return digest


def evaluate_predictions(
    directory: str | Path,
    predictions_path: str | Path,
    *,
    split: str = "validation",
) -> dict[str, Any]:
    """Score held-out predictions; NEVER train on the answer-bearing splits."""
    validate_curriculum(directory)
    if split not in ("validation", "test"):
        raise SyntheticCurriculumError("only held-out splits may be evaluated")
    root = Path(directory)
    manifest = _strict_json(_read_bytes(root / "manifest.json").decode("utf-8"))
    rows = _split_rows(root, manifest, split)
    answer_map = {row["id"]: row for row in rows}
    raw = _read_bytes(Path(predictions_path))
    try:
        lines = raw.decode("utf-8", "strict").splitlines()
    except UnicodeError as exc:
        raise SyntheticCurriculumError("prediction file is not UTF-8") from exc
    if len(lines) != len(rows):
        raise SyntheticCurriculumError("prediction count must match held-out split")
    answers: dict[str, str] = {}
    for line in lines:
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise SyntheticCurriculumError("prediction line too long")
        item = _strict_json(line)
        if (
            not isinstance(item, dict) or set(item) != {"id", "prediction"}
            or not isinstance(item["id"], str)
            or not isinstance(item["prediction"], str)
            or len(item["prediction"]) > 400
            or item["id"] not in answer_map or item["id"] in answers
        ):
            raise SyntheticCurriculumError("prediction identity/format mismatch")
        answers[item["id"]] = item["prediction"]
    scores: dict[str, list[int]] = {family: [0, 0] for family in FAMILIES}
    for item in rows:
        answer = answers[item["id"]].strip()
        expected = item["response"]
        if item["oracle"] in ("exact_json", "inventory_oracle", "json_exact"):
            try:
                matched = _json_equal(answer, _strict_json(expected))
            except (ValueError, SyntheticCurriculumError):
                matched = False
        else:
            matched = answer == expected
        scores[item["family"]][1] += 1
        scores[item["family"]][0] += int(matched)
    return {
        "schema_version": "skeleton.synthetic_offline_curriculum.evaluation.v1",
        "dataset_id": DATASET_ID,
        "split": split,
        "predictions_sha256": _sha(raw),
        "correct": sum(x[0] for x in scores.values()),
        "total": sum(x[1] for x in scores.values()),
        "by_family": {
            name: {"correct": scores[name][0], "total": scores[name][1]}
            for name in FAMILIES
        },
        "trained_weights_promoted": False,
    }


__all__ = [
    "DATASET_ID", "FAMILIES", "SPLITS", "SyntheticCurriculumError",
    "validate_curriculum", "register_with_training_registry", "evaluate_predictions",
]
