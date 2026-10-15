"""Rights-gated, disjoint, checksum-pinned game-design training datasets.

A production operator supplies an approved on-disk JSON manifest referencing
two local JSONL files: a training corpus and a never-trained evaluation corpus.
No network fetch, implicit scraped sources, or guessed rights are permitted.
The rights fields are review declarations, not legal proof; the operator still
owns verification and license compliance. The loader never downloads content.

The fixed 24-prompt design benchmark is a THIRD split and cannot overlap with
either supplied corpus by exact prompt identity.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .jeeves_production_game_train import ProductionCheckpointError, _strict_json

SCHEMA = "skeleton.jeeves.game_corpus_manifest.v1"
RIGHTS_SCHEMA = "skeleton.jeeves.game_corpus_rights.v1"
FAMILIES = frozenset((
    "mechanics", "narrative", "npc", "world",
    "economy", "tooling", "accessibility", "review",
))
MAX_DATASET_BYTES = 64 * 1024 * 1024
MAX_ROWS_PER_SPLIT = 10000
MAX_WORDS_PER_SPLIT = 200000
MAX_PROMPT_CHARS = 4096
MAX_ANSWER_CHARS = 12000
MIN_TRAIN_PER_FAMILY = 4
MIN_HOLDOUT_PER_FAMILY = 2
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{2,127}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_WHITESPACE = re.compile(r"\s+")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize(value: str) -> str:
    return _WHITESPACE.sub(" ", value.casefold()).strip()


def _safe_file(root: Path, name: Any) -> Path:
    if not isinstance(name, str) or not _ID.fullmatch(name):
        raise ProductionCheckpointError("corpus file must be a simple safe basename")
    if not name.endswith(".jsonl"):
        raise ProductionCheckpointError("corpus files must use JSONL format")
    candidate = root / name
    if (candidate.is_symlink() or not candidate.is_file()
            or candidate.parent.resolve() != root.resolve()):
        raise ProductionCheckpointError("corpus must be a regular file alongside its manifest")
    if not 16 <= candidate.stat().st_size <= MAX_DATASET_BYTES:
        raise ProductionCheckpointError("corpus file size outside approved bounds")
    return candidate


def _text(value: Any, *, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ProductionCheckpointError(f"corpus {label} must contain {minimum}..{maximum} characters")
    if not value.strip() or any(ord(c) < 32 and c not in "\t\n" for c in value):
        raise ProductionCheckpointError("corpus text contains empty or control content")
    if " Jeeves: " in value or "\nJeeves:" in value or "\nUser:" in value:
        raise ProductionCheckpointError("corpus text contains a reserved chat role delimiter")
    return value.strip()


def _check_rights(row: dict[str, Any]) -> None:
    rights = row.get("rights")
    if not isinstance(rights, dict) or rights.get("schema_version") != RIGHTS_SCHEMA:
        raise ProductionCheckpointError("every game corpus record requires rights metadata")
    if rights.get("training_permitted") is not True:
        raise ProductionCheckpointError("training or evaluation use not permitted by rights review")
    kind = rights.get("source_kind")
    if kind not in {"original_authoring", "licensed_training", "public_domain"}:
        raise ProductionCheckpointError("unapproved source kind; scraped/unknown is not admitted")
    for field in ("rights_holder", "rights_basis", "review_id"):
        if (not isinstance(rights.get(field), str)
                or not 3 <= len(rights[field].strip()) <= 512):
            raise ProductionCheckpointError("source rights require an explicit " + field)
    if kind == "licensed_training" and not rights.get("rights_basis", "").startswith("license:"):
        raise ProductionCheckpointError("licensed training needs a license reference")
    # The rights review is a human/legal provenance declaration, not proof
    # established by user-editable JSON alone. Acceptance requires operator
    # verification of the recorded rights holder and review decision.


def _load_split(root: Path, *, filename: Any, digest: Any, split: str) -> list[dict[str, Any]]:
    if not isinstance(digest, str) or not _HEX.fullmatch(digest):
        raise ProductionCheckpointError("corpus SHA-256 must be pinned in the manifest")
    source = _safe_file(root, filename)
    raw = source.read_bytes()
    if _digest(raw) != digest:
        raise ProductionCheckpointError("corpus SHA-256 has changed since rights admission")
    records: list[dict[str, Any]] = []
    words_loaded = 0
    for line_number, raw_line in enumerate(raw.splitlines(), 1):
        if not raw_line.strip():
            raise ProductionCheckpointError("empty JSONL records are not allowed")
        if line_number > MAX_ROWS_PER_SPLIT:
            raise ProductionCheckpointError("game corpus exceeds 10000 records per split")
        row = _strict_json(raw_line)
        if row.get("split") != split:
            raise ProductionCheckpointError("game corpus split mismatch")
        identity = row.get("id")
        if not isinstance(identity, str) or not _ID.fullmatch(identity):
            raise ProductionCheckpointError("corpus record id is missing or malformed")
        if row.get("family") not in FAMILIES:
            raise ProductionCheckpointError("unknown game-design curriculum family")
        prompt = _text(row.get("prompt"), label="prompt", minimum=10, maximum=MAX_PROMPT_CHARS)
        answer = _text(row.get("answer"), label="answer", minimum=20, maximum=MAX_ANSWER_CHARS)
        words_loaded += len(prompt.split()) + len(answer.split())
        if words_loaded > MAX_WORDS_PER_SPLIT:
            raise ProductionCheckpointError("game corpus exceeds bounded tokenizer word budget")
        _check_rights(row)
        records.append(row)
    return records


def _shingles(text: str, n: int = 6) -> set[tuple[str, ...]]:
    words = _normalize(text).split()
    return {tuple(words[i:i+n]) for i in range(max(0, len(words)-n+1))}


def _split_contamination(a: str, b: str) -> bool:
    """Catch copied long prompt passages without punishing shared game terms."""
    if _normalize(a) == _normalize(b):
        return True
    aa, bb = _shingles(a), _shingles(b)
    return bool(aa and bb and len(aa & bb) / min(len(aa), len(bb)) >= .85)


def load_approved_corpus(manifest_path: Path) -> tuple[
    tuple[str, ...], dict[str, tuple[str, ...]], dict[str, Any],
]:
    """Return (train texts, heldout by family, receipt); do not touch model."""
    if (manifest_path.is_symlink() or not manifest_path.is_file()
            or not 16 <= manifest_path.stat().st_size <= 64 * 1024):
        raise ProductionCheckpointError("game corpus manifest must be a bounded regular file")
    manifest_raw = manifest_path.read_bytes()
    config = _strict_json(manifest_raw)
    if config.get("schema_version") != SCHEMA:
        raise ProductionCheckpointError("unsupported production game corpus schema")
    if config.get("rights_reviewed") is not True:
        raise ProductionCheckpointError("dataset lacks explicit human rights-review declaration")
    if not isinstance(config.get("review_id"), str) or len(config["review_id"].strip()) < 3:
        raise ProductionCheckpointError("manifest needs an independently documented rights review ID")
    train_filename = config.get("train_file")
    holdout_filename = config.get("heldout_file")
    if train_filename == holdout_filename:
        raise ProductionCheckpointError("training and held-out files must be distinct")
    root = manifest_path.parent
    training = _load_split(root, filename=train_filename, digest=config.get("train_sha256"), split="train")
    heldout = _load_split(root, filename=holdout_filename, digest=config.get("heldout_sha256"), split="heldout")
    if not training or not heldout:
        raise ProductionCheckpointError("both game-design splits must contain records")

    per_family_train: dict[str, list[str]] = defaultdict(list)
    per_family_eval: dict[str, list[str]] = defaultdict(list)
    ids: set[str] = set()
    unique_text: dict[str, str] = {}
    for row in training + heldout:
        identity = row["id"]
        if identity in ids:
            raise ProductionCheckpointError("duplicate record ID across train and held-out")
        ids.add(identity)
        chat = "User: " + row["prompt"].strip() + " Jeeves: " + row["answer"].strip()
        normalized = _normalize(chat)
        if normalized in unique_text:
            raise ProductionCheckpointError("exact duplicate game-design example")
        unique_text[normalized] = identity
        dest = per_family_train if row["split"] == "train" else per_family_eval
        dest[row["family"]].append(chat)
    if any(
        len(per_family_train[family]) < MIN_TRAIN_PER_FAMILY or
        len(per_family_eval[family]) < MIN_HOLDOUT_PER_FAMILY
        for family in FAMILIES
    ):
        raise ProductionCheckpointError("each game family needs 4 training and 2 held-out examples")

    train_prompts = [row["prompt"] for row in training]
    test_prompts = [row["prompt"] for row in heldout]
    from .jeeves_game_design_benchmark import BENCHMARK
    benchmark_prompts = [prompt for _, prompt, _ in BENCHMARK]
    seen_benchmark = {_normalize(p) for p in benchmark_prompts}
    for p in train_prompts + test_prompts:
        if _normalize(p) in seen_benchmark:
            raise ProductionCheckpointError("game corpus overlaps immutable third-split design benchmark")
    # Indexed six-gram probes catch near-copies without quadratic all-pair
    # comparisons across up to 20,000 records. Exact string identity is
    # checked for all rows above.
    train_index: dict[tuple[str, ...], set[int]] = defaultdict(set)
    train_sets = [_shingles(prompt) for prompt in train_prompts]
    for idx, grams in enumerate(train_sets):
        for gram in grams:
            train_index[gram].add(idx)
    for held_prompt in test_prompts:
        grams = _shingles(held_prompt)
        candidate_ids: set[int] = set()
        for gram in grams:
            candidate_ids.update(train_index.get(gram, ()))
        for idx in candidate_ids:
            if _split_contamination(held_prompt, train_prompts[idx]):
                raise ProductionCheckpointError("near-duplicate prompt leaked between corpus splits")
    # Prompt partition alone is insufficient: copied reference *answers*
    # can make held-out loss appear to improve without transfer of skills.
    # Apply the same high-similarity policy to the actual target sequences.
    training_answers = [row["answer"] for row in training]
    eval_answers = [row["answer"] for row in heldout]
    answer_index: dict[tuple[str, ...], set[int]] = defaultdict(set)
    for idx, answer in enumerate(training_answers):
        for gram in _shingles(answer):
            answer_index[gram].add(idx)
    exact_training_answers = {_normalize(answer) for answer in training_answers}
    for answer in eval_answers:
        if _normalize(answer) in exact_training_answers:
            raise ProductionCheckpointError("held-out game design answer copied from training")
        candidates: set[int] = set()
        for gram in _shingles(answer):
            candidates.update(answer_index.get(gram, ()))
        for idx in candidates:
            if _split_contamination(answer, training_answers[idx]):
                raise ProductionCheckpointError("held-out reference answer near-duplicates training")
    # Preserve authored training order and family-key order, not sorted
    # vocabulary occurrences. Model fit and optimizer progress stay replayable.
    train_texts = tuple(
        "User: " + row["prompt"].strip() + " Jeeves: " + row["answer"].strip()
        for row in training
    )
    heldout_texts = {
        family: tuple(per_family_eval[family]) for family in sorted(FAMILIES)
    }
    receipt = {
        "schema_version": SCHEMA,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _digest(manifest_raw),
        "train_sha256": config["train_sha256"],
        "heldout_sha256": config["heldout_sha256"],
        "rights_review_id": config["review_id"],
        "train_examples": len(training),
        "heldout_examples": len(heldout),
        "families": sorted(FAMILIES),
        "heldout_used_for_training": False,
        "benchmark_overlap_checked": True,
        "all_records_declared_training_permitted": True,
        "independent_rights_verification_still_required": True,
    }
    return train_texts, heldout_texts, receipt


def main(argv: list[str] | None = None) -> int:
    """Validate a rights-approved corpus without opening a model or running SGD."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _training, _heldout, receipt = load_approved_corpus(args.manifest)
        print(json.dumps({
            "status": "valid_dataset_pending_independent_rights_confirmation",
            **receipt,
            "model_weights_modified": False,
            "training_executed": False,
        }, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:400]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA", "RIGHTS_SCHEMA", "FAMILIES", "load_approved_corpus"]
