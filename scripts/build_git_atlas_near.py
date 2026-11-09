#!/usr/bin/env python3
"""Bounded, evidence-backed near-duplicate candidates for the canonical Git atlas.

Similarity is advisory. It does not imply equivalence, legal safety, ownership,
or authorization to modify files. All examined bytes are checked against Git.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any

from scripts.build_git_atlas import git, SCHEMA

WORDS = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+")
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".c", ".cpp", ".h"}
DEFAULT_MAX_BYTES = 65536
DEFAULT_MAX_PAIRS = 200000
DEFAULT_MAX_BUCKET = 64


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encode(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def _verify_file(root: Path, path: str, sha: str, max_bytes: int) -> tuple[str | None, str]:
    parts = PurePosixPath(path)
    if (
        not path or parts.is_absolute() or ".." in parts.parts or
        path != parts.as_posix() or "\\" in path
    ):
        raise ValueError("unsafe indexed repository path")
    actual = root / path
    if actual.is_symlink() or not actual.resolve().is_relative_to(root):
        raise ValueError(f"indexed source escapes repository root: {path}")
    metadata = actual.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"indexed source is not a regular file: {path}")
    if metadata.st_size > max_bytes:
        return None, "oversize"
    raw = actual.read_bytes()
    if len(raw) != metadata.st_size:
        raise ValueError(f"source changed during similarity scan: {path}")
    algorithm = hashlib.sha1 if len(sha) == 40 else hashlib.sha256
    actual_sha = algorithm(f"blob {len(raw)}\x00".encode("ascii") + raw).hexdigest()
    if actual_sha != sha:
        raise ValueError(f"source differs from pinned Git blob: {path}")
    try:
        return raw.decode("utf-8"), "ok"
    except UnicodeDecodeError:
        return None, "binary_or_non_utf8"


def structural_digest(text: str, path: str) -> str | None:
    if PurePosixPath(path).suffix != ".py":
        return None
    try:
        node = ast.parse(text)
    except (ValueError, SyntaxError, RecursionError):
        return None
    if len(node.body) < 1:
        return None
    structural = ast.dump(node, annotate_fields=True, include_attributes=False)
    return _sha256(structural.encode("utf-8"))


def token_signature(text: str) -> tuple[int, frozenset[str], int] | None:
    words = WORDS.findall(text.casefold())
    if len(words) < 12:
        return None
    # Bound the amount of material per file while preserving source order.
    words = words[:1500]
    shingles = (
        (" ".join(words[i:i + 3]) for i in range(len(words) - 2))
    )
    votes = [0] * 64
    for shingle in shingles:
        fingerprint = int.from_bytes(
            hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big"
        )
        for bit in range(64):
            votes[bit] += 1 if fingerprint & (1 << bit) else -1
    signature = sum((1 << bit) for bit, count in enumerate(votes) if count > 0)
    return signature, frozenset(words), len(words)


def _hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    overlap = len(left & right)
    union = len(left) + len(right) - overlap
    return (overlap / union) if union else 0.0


def near_pairs(
    records: list[dict[str, Any]],
    *,
    max_pairs: int = DEFAULT_MAX_PAIRS,
    max_bucket: int = DEFAULT_MAX_BUCKET,
) -> tuple[list[dict[str, Any]], dict[str, int | bool]]:
    if max_pairs < 1 or max_bucket < 2:
        raise ValueError("similarity safety bounds must be positive")
    bands: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        for band in range(4):
            bands[(band, (record["simhash"] >> (band * 16)) & 0xFFFF)].append(index)
    candidates: set[tuple[int, int]] = set()
    overflow = 0
    capped = False
    for key in sorted(bands):
        bucket = bands[key]
        if len(bucket) > max_bucket:
            overflow += 1
            continue
        for i, left in enumerate(bucket):
            for right in bucket[i + 1:]:
                if left == right:
                    continue
                candidates.add((min(left, right), max(left, right)))
                if len(candidates) >= max_pairs:
                    capped = True
                    break
            if capped:
                break
        if capped:
            break
    result: list[dict[str, Any]] = []
    for left_id, right_id in sorted(candidates):
        left, right = records[left_id], records[right_id]
        if left["sha"] == right["sha"]:
            continue
        length_ratio = min(left["tokens"], right["tokens"]) / max(left["tokens"], right["tokens"])
        if length_ratio < 0.70:
            continue
        distance = _hamming(left["simhash"], right["simhash"])
        if distance > 10:
            continue
        score = _similarity(left["words"], right["words"])
        if score < 0.88:
            continue
        result.append({
            "left_blob_sha": left["sha"], "right_blob_sha": right["sha"],
            "left_example": left["path"], "right_example": right["path"],
            "token_jaccard": round(score, 6), "simhash_hamming": distance,
            "status": "candidate_unverified_no_auto_merge",
        })
    result.sort(key=lambda r: (-r["token_jaccard"], r["simhash_hamming"],
                                r["left_example"], r["right_example"]))
    return result, {
        "candidate_pairs_tested": len(candidates),
        "overflow_buckets": overflow,
        "pair_limit_hit": capped,
        "candidate_search_complete": not (overflow or capped),
    }


def analyze(root: Path, atlas: Path, output: Path, max_bytes: int = DEFAULT_MAX_BYTES,
            max_pairs: int = DEFAULT_MAX_PAIRS) -> dict[str, Any]:
    root = root.resolve()
    if max_bytes < 1024 or max_bytes > 8 * 1024 * 1024:
        raise ValueError("near-duplicate byte limit must be between 1 KiB and 8 MiB")
    summary_data = (atlas / "summary.json").read_bytes()
    summary = json.loads(summary_data)
    if summary.get("schema") != SCHEMA or summary.get("truncated") is not False:
        raise ValueError("missing or incomplete upstream Git atlas")
    current_sha = git(root, "rev-parse", "HEAD").decode().strip()
    if current_sha != summary["commit"]:
        raise ValueError("near duplicate scan must run at the pinned Git atlas commit")
    files_data = (atlas / "files.jsonl").read_bytes()
    receipt = summary["artifacts"]["files.jsonl"]
    if _sha256(files_data) != receipt["sha256"] or len(files_data) != receipt["size"]:
        raise ValueError("Git atlas file ledger digest mismatch")
    files = [json.loads(line) for line in files_data.splitlines() if line]
    if len(files) != summary["tracked_entries"]:
        raise ValueError("Git atlas file ledger count mismatch")
    blobs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in files:
        if item["type"] == "blob" and item["mode"] in ("100644", "100755"):
            if PurePosixPath(item["path"]).suffix.lower() in CODE_EXTENSIONS:
                blobs[item["blob_sha"]].append(item)
    fingerprints: list[dict[str, Any]] = []
    normalized: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped: Counter[str] = Counter()
    for sha, copies in sorted(blobs.items()):
        # A canonical/non-snapshot path takes precedence over historical snapshots.
        item = sorted(copies, key=lambda row: (row["snapshot"], row["path"]))[0]
        content, state = _verify_file(root, item["path"], sha, max_bytes)
        if state != "ok" or content is None:
            skipped[state] += 1
            continue
        normalized_sha = structural_digest(content, item["path"])
        if normalized_sha is not None:
            normalized[normalized_sha].append({"sha": sha, "path": item["path"]})
        signature = token_signature(content)
        if signature is None:
            skipped["short_source"] += 1
            continue
        simhash, words, length = signature
        fingerprints.append({
            "sha": sha, "path": item["path"], "simhash": simhash,
            "words": words, "tokens": length,
        })
    normalized_groups = [
        {"structural_sha256": digest, "members": sorted(members, key=lambda m: m["path"]),
         "status": "syntax_equivalent_candidate_review_only"}
        for digest, members in normalized.items() if len(members) > 1
    ]
    normalized_groups.sort(key=lambda row: row["structural_sha256"])
    candidates, statistics = near_pairs(fingerprints, max_pairs=max_pairs)
    output.mkdir(parents=True, exist_ok=True)
    payloads = {
        "normalized-duplicates.jsonl": b"".join(_encode(group) for group in normalized_groups),
        "near-candidates.jsonl": b"".join(_encode(pair) for pair in candidates),
    }
    for name, data in payloads.items():
        path = output / name
        if path.is_symlink():
            raise ValueError(f"near-duplicate output is a symlink: {name}")
        path.write_bytes(data)
    near_summary = {
        "schema": "skeleton.git-atlas-near.v1", "commit": current_sha,
        "eligible_unique_source_blobs": len(blobs),
        "fingerprinted_blobs": len(fingerprints),
        "normalized_duplicate_groups": len(normalized_groups),
        "near_candidate_pairs": len(candidates),
        "skipped": dict(sorted(skipped.items())),
        **statistics,
        "fully_exhaustive_similarity": False,
        "disposition": "review_only_no_auto_delete_or_consolidation",
        "artifacts": {
            name: {"sha256": _sha256(data), "size": len(data)}
            for name, data in sorted(payloads.items())
        },
    }
    (output / "near-summary.json").write_bytes(_encode(near_summary))
    return near_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-pairs", type=int, default=DEFAULT_MAX_PAIRS)
    args = parser.parse_args()
    try:
        report = analyze(args.root, args.atlas, args.output, args.max_bytes, args.max_pairs)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"near duplicate audit failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
