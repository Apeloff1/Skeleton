#!/usr/bin/env python3
"""Deterministic, read-only, Git-tracked repository navigation and duplicate index.

Separate from the richer repository-machine manifest: this inventory deliberately
includes every tracked path, including historical satellites and binary assets.
All output is derived from one immutable HEAD tree and is safe to rebuild.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from hashlib import blake2b, sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Iterable

VERSION = "skeleton.repository-navigation.v1"
TEXT_SUFFIXES = frozenset({".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".md", ".c", ".h", ".cpp", ".rs", ".go", ".sh"})
STOP_NAMES = frozenset({"__init__.py", "index.ts", "index.tsx", "index.js", "package.json", "readme.md", "main.py", "config.py"})
TOKENS = re.compile(rb"[a-z_][a-z_0-9]{2,}")
MAX_NEAR_BYTES = 256_000


class InventoryError(RuntimeError):
    """A source or artifact violated inventory bounds or provenance."""


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode:
        raise InventoryError(f"git {args[0]} failed: {result.stderr[:300]!r}")
    return result.stdout


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def safe_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(contents, encoding="utf-8", newline="\n")
    os.replace(temp, path)


@dataclass(frozen=True)
class GitFile:
    path: str
    sha: str
    size: int
    mode: str
    zone: str
    owner: str
    lifecycle: str
    feature: str
    role: str

    def as_dict(self) -> dict[str, object]:
        return self.__dict__ if hasattr(self, "__dict__") else {key: getattr(self, key) for key in self.__dataclass_fields__}


def load_zones(root: Path) -> tuple[tuple[str, tuple[str, ...], str, str], ...]:
    config_path = root / ".machine" / "repository.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    zones = []
    for item in data["zone"]:
        zones.append((item["name"], tuple(item["prefixes"]), item["owner"], item["lifecycle"]))
    if len({zone[0] for zone in zones}) != len(zones):
        raise InventoryError("zone identities must be unique")
    return tuple(zones)


def classify(path: str, zones: tuple[tuple[str, tuple[str, ...], str, str], ...]) -> tuple[str, str, str]:
    for zone, prefixes, owner, lifecycle in zones:
        if any(path.startswith(prefix) for prefix in prefixes):
            return zone, owner, lifecycle
    return "unclassified", "unassigned", "unclassified"


def feature_path(path: str) -> str:
    parts = path.split("/")
    if parts[0] == "satellites" and len(parts) >= 3 and parts[1] == "branch-snapshots":
        return "/".join(parts[:3])
    if len(parts) <= 2:
        return parts[0]
    if parts[0] == "skeleton" and len(parts) >= 4 and parts[1] == "ai":
        return "/".join(parts[:4])
    if parts[0] == "frontend" and len(parts) >= 4 and parts[1] == "features":
        return "/".join(parts[:3])
    if parts[0] in {"skeleton", "backend", "frontend", "machine", "docs", "tests"}:
        return "/".join(parts[:3])
    return "/".join(parts[:2])


def role_for(path: str) -> str:
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    suffix = Path(name).suffix
    if lower.startswith(".github/workflows/") and suffix in {".yml", ".yaml"}:
        return "workflow"
    if name.startswith("test_") or "/tests/" in f"/{lower}/" or "/testing/" in f"/{lower}/" or ".test." in name:
        return "test"
    if lower.startswith("satellites/") or lower.startswith("complete/"):
        return "historical-source"
    if suffix in {".py", ".js", ".jsx", ".tsx", ".ts", ".rs", ".c", ".h", ".go", ".cpp"}:
        return "source"
    if suffix in {".md", ".mdx", ".rst"}:
        return "documentation"
    if suffix in {".yml", ".yaml", ".json", ".toml", ".ini", ".cfg"}:
        return "configuration-or-data"
    if suffix in {".png", ".jpg", ".mp4", ".zst", ".bson", ".woff", ".ttf"}:
        return "binary-asset"
    return "support"


def tracked_files(root: Path, zones: tuple[tuple[str, tuple[str, ...], str, str], ...]) -> tuple[str, list[GitFile]]:
    commit = git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    raw = git(root, "ls-tree", "-r", "-l", "-z", "HEAD")
    rows: list[GitFile] = []
    seen: set[str] = set()
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            meta, raw_path = item.split(b"\t", 1)
            mode, kind, raw_sha, raw_size = meta.split()
            path = raw_path.decode("utf-8", errors="strict")
            if not path or path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
                raise InventoryError("non-canonical tracked path")
            if path in seen:
                raise InventoryError("duplicate tree path")
            seen.add(path)
            if kind.decode("ascii") not in {"blob", "commit"}:
                raise InventoryError("unexpected git tree object")
            # Submodules have no blob body/size and remain visible as entries.
            size = -1 if raw_size == b"-" else int(raw_size)
            digest = raw_sha.decode("ascii")
            if not re.fullmatch(r"[0-9a-f]{40,64}", digest) or size < -1:
                raise InventoryError("invalid Git object metadata")
        except (UnicodeError, ValueError) as exc:
            raise InventoryError("invalid Git tree entry") from exc
        zone, owner, lifecycle = classify(path, zones)
        rows.append(GitFile(path, digest, size, mode.decode("ascii"), zone, owner, lifecycle, feature_path(path), role_for(path)))
    if not rows:
        raise InventoryError("empty repository tree")
    rows.sort(key=lambda entry: entry.path)
    return commit, rows


def group_summary(files: Iterable[GitFile], attr: str) -> list[dict[str, object]]:
    entries: dict[str, dict[str, object]] = {}
    for file in files:
        name = getattr(file, attr)
        record = entries.setdefault(name, {"name": name, "files": 0, "bytes": 0, "roles": {}, "zones": {}})
        record["files"] += 1
        record["bytes"] += max(file.size, 0)
        roles = record["roles"]
        roles[file.role] = roles.get(file.role, 0) + 1
        zones = record["zones"]
        zones[file.zone] = zones.get(file.zone, 0) + 1
    return sorted(entries.values(), key=lambda item: item["name"])


def directories(files: Iterable[GitFile]) -> list[dict[str, object]]:
    stats = defaultdict(lambda: [0, 0, 0])
    for file in files:
        parts = file.path.split("/")
        for depth in range(1, len(parts)):
            name = "/".join(parts[:depth])
            stats[name][0] += 1
            stats[name][1] += max(file.size, 0)
            if depth == len(parts) - 1:
                stats[name][2] += 1
    return [{"path": name, "subtree_files": counts[0], "subtree_bytes": counts[1], "direct_files": counts[2]} for name, counts in sorted(stats.items())]


def exact_duplicates(files: Iterable[GitFile]) -> list[dict[str, object]]:
    shared = defaultdict(list)
    for file in files:
        if file.size >= 0:
            shared[file.sha].append(file)
    return [{"blob": digest, "size": group[0].size, "paths": sorted(file.path for file in group)} for digest, group in sorted(shared.items()) if len(group) > 1]


def candidate_pairs(files: list[GitFile], *, limit: int) -> tuple[list[tuple[GitFile, GitFile]], int]:
    """Bounded deterministic LSH-like basename/size neighborhood candidate search.

    This is candidate generation, not a similarity assertion. Near-duplicate
    classification requires reading and comparing both source blobs.
    """
    by_name = defaultdict(list)
    for file in files:
        if file.size < 200 or file.size > MAX_NEAR_BYTES or file.mode not in {"100644", "100755"}:
            continue
        name = file.path.rsplit("/", 1)[-1].lower()
        if name in STOP_NAMES or Path(name).suffix not in TEXT_SUFFIXES:
            continue
        by_name[name].append(file)
    possible: list[tuple[int, str, str, GitFile, GitFile]] = []
    for name, group in sorted(by_name.items()):
        ordered = sorted(group, key=lambda f: (f.size, f.path))
        for i, file in enumerate(ordered):
            for other in ordered[i + 1:i + 5]:
                if file.sha == other.sha or file.path == other.path or file.size * 4 < other.size * 3:
                    continue
                same_relative = (
                    file.path.endswith("/" + other.path.split("/")[-2] + "/" + name)
                    or other.path.endswith("/" + file.path.split("/")[-2] + "/" + name)
                )
                priority = 0 if same_relative else 1
                possible.append((priority, file.path, other.path, file, other))
    possible.sort(key=lambda candidate: candidate[:3])
    return [(a, b) for _, _, _, a, b in possible[:limit]], max(0, len(possible) - limit)


def read_git_blobs(root: Path, shas: Iterable[str]) -> dict[str, bytes]:
    """Read candidate blobs in one bounded git batch, without shell interpolation."""
    identities = sorted(set(shas))
    if not identities:
        return {}
    result: dict[str, bytes] = {}
    proc = subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin and proc.stdout
    try:
        for digest in identities:
            proc.stdin.write((digest + "\n").encode("ascii"))
            proc.stdin.flush()
            header = proc.stdout.readline().rstrip(b"\n")
            chunks = header.split(b" ")
            if len(chunks) != 3 or chunks[0] != digest.encode("ascii") or chunks[1] != b"blob":
                raise InventoryError("Git blob identity/type mismatch")
            size = int(chunks[2])
            if size > MAX_NEAR_BYTES or size < 0:
                raise InventoryError("candidate blob exceeds safe size")
            contents = proc.stdout.read(size)
            if len(contents) != size or proc.stdout.read(1) != b"\n":
                raise InventoryError("short Git object stream")
            result[digest] = contents
    finally:
        proc.stdin.close()
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()
    return result


def token_fingerprint(blob: bytes) -> frozenset[bytes]:
    """Hashed token 4-grams reduce identifier-order/whitespace noise."""
    tokens = TOKENS.findall(blob.lower())
    if len(tokens) < 24:
        return frozenset()
    return frozenset(blake2b(b"\x1f".join(tokens[i:i + 4]), digest_size=8).digest() for i in range(len(tokens) - 3))


def near_duplicates(root: Path, files: list[GitFile], *, candidate_limit: int, threshold: float) -> dict[str, object]:
    pairs, skipped = candidate_pairs(files, limit=candidate_limit)
    contents = read_git_blobs(root, (file.sha for pair in pairs for file in pair))
    fingerprints = {digest: token_fingerprint(body) for digest, body in contents.items()}
    matches = []
    for left, right in pairs:
        a, b = fingerprints[left.sha], fingerprints[right.sha]
        if len(a) < 8 or len(b) < 8:
            continue
        score = len(a & b) / len(a | b)
        if score >= threshold:
            matches.append({"left": left.path, "right": right.path, "left_blob": left.sha, "right_blob": right.sha, "similarity": round(score, 4), "method": "token-4gram-jaccard", "classification": "review-required"})
    matches.sort(key=lambda p: (-p["similarity"], p["left"], p["right"]))
    return {"method": "basename-and-size-candidates-with-token-4gram-jaccard", "threshold": threshold, "candidate_pairs_inspected": len(pairs), "candidate_pairs_deferred": skipped, "content_verified_matches": matches, "note": "Heuristic similarity never establishes equivalent behavior or authorizes deletion, import inversion, or merging."}


def build(root: Path, out: Path, *, near_limit: int = 2000, near_threshold: float = 0.82) -> dict[str, object]:
    if near_limit < 0 or not 0 <= near_threshold <= 1:
        raise InventoryError("invalid similarity budget")
    zones = load_zones(root)
    commit, files = tracked_files(root, zones)
    duplicates = exact_duplicates(files)
    features = group_summary(files, "feature")
    grouped_zones = group_summary(files, "zone")
    root_count = defaultdict(int)
    for file in files:
        root_count[file.path.split("/")[0]] += 1
    summary = {
        "schema": VERSION,
        "commit": commit,
        "complete_git_tree": True,
        "file_count": len(files),
        "directory_count": len(directories(files)),
        "feature_count": len(features),
        "zone_count": len(grouped_zones),
        "unclassified_files": sum(f.zone == "unclassified" for f in files),
        "exact_duplicate_groups": len(duplicates),
        "exact_extra_copies": sum(len(g["paths"]) - 1 for g in duplicates),
        "exact_extra_bytes": sum((len(g["paths"]) - 1) * g["size"] for g in duplicates),
        "root_file_counts": dict(sorted(root_count.items())),
        "indexes": ["files.jsonl", "features.json", "zones.json", "directories.json", "exact-duplicates.json", "near-duplicates.json"],
        "authority": "Read-only projection. machine/architecture.json and .machine/repository.toml retain ownership authority.",
    }
    near = near_duplicates(root, files, candidate_limit=near_limit, threshold=near_threshold)
    safe_write(out / "files.jsonl", "".join(canonical(f.as_dict()) + "\n" for f in files))
    for name, payload in (("features", features), ("zones", grouped_zones), ("directories", directories(files)), ("exact-duplicates", duplicates), ("near-duplicates", near)):
        safe_write(out / (name + ".json"), canonical({"schema": VERSION, "commit": commit, "data": payload}) + "\n")
    # Manifest binds all shards to the exact source commit and contents.
    summary["artifact_digests"] = {name: sha256((out / name).read_bytes()).hexdigest() for name in summary["indexes"]}
    safe_write(out / "summary.json", canonical(summary) + "\n")
    return summary


def query(out: Path, text: str, *, max_bytes: int = 8_000) -> dict[str, object]:
    """A context-budgeted navigation result; never return full source content."""
    if not text.strip() or max_bytes < 1024 or max_bytes > 60_000:
        raise InventoryError("invalid query or context budget")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    terms = text.lower().split()
    hits = []
    with (out / "files.jsonl").open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            path = row["path"].lower()
            if all(term in path or term in row["zone"] or term in row["feature"] for term in terms):
                hits.append({"path": row["path"], "blob": row["sha"], "zone": row["zone"], "feature": row["feature"], "owner": row["owner"], "lifecycle": row["lifecycle"]})
    result = {"schema": VERSION, "commit": summary["commit"], "query": text, "total_hits": len(hits), "hits": []}
    for row in hits:
        if len(canonical({**result, "hits": [*result["hits"], row]}).encode("utf-8")) > max_bytes:
            break
        result["hits"].append(row)
    result["truncated_to_context_budget"] = len(result["hits"]) < len(hits)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default=".machine/repository-navigation")
    parser.add_argument("--near-limit", type=int, default=2000)
    parser.add_argument("--near-threshold", type=float, default=0.82)
    parser.add_argument("--query", default="")
    parser.add_argument("--context-bytes", type=int, default=8000)
    args = parser.parse_args()
    root = Path(args.root).resolve(strict=True)
    out = Path(args.output)
    if not out.is_absolute():
        out = root / out
    try:
        payload = query(out, args.query, max_bytes=args.context_bytes) if args.query else build(root, out, near_limit=args.near_limit, near_threshold=args.near_threshold)
    except (InventoryError, OSError, ValueError, tomllib.TOMLDecodeError, subprocess.SubprocessError) as exc:
        print(f"repository navigation indexing failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(canonical(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
