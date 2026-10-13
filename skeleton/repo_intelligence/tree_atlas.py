"""Content-addressed, read-only whole-repository atlas.

The Git tree is authoritative, not a potentially dirty filesystem walk.
All entries are enumerated at one pinned commit; historical snapshots and
symlinks are recorded but never imported, executed, or followed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import os
import tomllib
from typing import Iterable

FORMAT = "skeleton.repository-atlas.v1"
CODE_EXTENSIONS = frozenset({".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp"})
TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]", re.ASCII)
WORD = re.compile(r"[a-z0-9]+")
MAX_BLOB_BYTES = 160_000


class AtlasError(RuntimeError):
    """An atlas is invalid or its source-of-truth cannot be verified."""


def _git(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_PAGER": "cat"})
    try:
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
             "-c", "diff.external=", *args],
            cwd=root, env=env, input=input_bytes, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AtlasError("Git inventory invocation failed") from exc
    if result.returncode:
        raise AtlasError("Git inventory failed: " + result.stderr.decode("utf-8", "replace")[:350])
    return result.stdout


def _canonical(path: str) -> str:
    if not path or "\\" in path or "\x00" in path or path.startswith("/"):
        raise AtlasError("unsafe Git path")
    if any(p in {"", ".", ".."} for p in path.split("/")):
        raise AtlasError("unsafe Git path component")
    if PurePosixPath(path).as_posix() != path:
        raise AtlasError("noncanonical Git path")
    return path


@dataclass(frozen=True, slots=True)
class Entry:
    path: str
    mode: str
    kind: str
    blob: str
    size: int | None
    zone: str
    owner: str
    feature: str
    lifecycle: str

    def json(self) -> dict[str, object]:
        return asdict(self)


def _feature(path: str, zone: str, known: dict[str, str]) -> str:
    if path in known:
        return known[path]
    for prefix, feature in sorted(known.items(), key=lambda kv: -len(kv[0])):
        if prefix.endswith("/") and path.startswith(prefix):
            return feature
    parts = path.split("/")
    # Feature IDs are provisional for paths not governed by an explicit
    # migration mapping. They do not confer authority to relocate a file.
    if len(parts) >= 3 and parts[0] == "skeleton":
        return zone + ":" + "/".join(parts[1:3])
    if len(parts) >= 2 and parts[0] in {"backend", "frontend", "scripts", "tests", ".github", "satellites"}:
        if parts[0] == "satellites" and len(parts) >= 3:
            return "history:" + "/".join(parts[:3])
        return zone + ":" + "/".join(parts[:2])
    return zone + ":" + parts[0]


def load_taxonomy(root: Path) -> tuple[tuple[str, str, str, str], ...]:
    path = root / ".machine" / "repository.toml"
    if not path.is_file() or path.is_symlink():
        raise AtlasError("canonical repository taxonomy unavailable")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    zones = raw.get("zone")
    if not isinstance(zones, list) or not zones:
        raise AtlasError("invalid repository taxonomy")
    rules: list[tuple[str, str, str, str]] = []
    for row in zones:
        if not isinstance(row, dict):
            raise AtlasError("invalid taxonomy zone")
        zone, owner = row.get("name"), row.get("owner")
        lifecycle, prefixes = row.get("lifecycle", "canonical"), row.get("prefixes")
        if not all(isinstance(x, str) and x for x in (zone, owner, lifecycle)):
            raise AtlasError("invalid taxonomy authority")
        if not isinstance(prefixes, list) or not prefixes:
            raise AtlasError("zone missing prefixes")
        for prefix in prefixes:
            if not isinstance(prefix, str) or not prefix:
                raise AtlasError("invalid taxonomy prefix")
            rules.append((prefix, zone, owner, lifecycle))
    return tuple(rules)


def load_feature_mappings(root: Path) -> dict[str, str]:
    """Reuse existing AI-file-tree identities; never invent alternate owners."""
    file = root / "machine" / "ai_file_tree.json"
    if not file.is_file() or file.is_symlink():
        raise AtlasError("AI migration identity contract unavailable")
    source = json.loads(file.read_text(encoding="utf-8"))
    mappings = source.get("mappings")
    if not isinstance(mappings, list):
        raise AtlasError("AI migration contract missing mappings")
    known: dict[str, str] = {}
    for row in mappings:
        if not isinstance(row, dict):
            raise AtlasError("invalid AI mapping")
        name = row.get("id")
        if not isinstance(name, str) or not name:
            raise AtlasError("invalid AI feature identity")
        for key in ("source", "destination"):
            path = row.get(key)
            if not isinstance(path, str) or not path:
                continue
            path = _canonical(path)
            kind = row.get("kind")
            index_key = path + "/" if kind == "tree" else path
            existing = known.get(index_key)
            if existing is not None and existing != name:
                raise AtlasError("conflicting AI feature identities")
            known[index_key] = name
    return known


def scan(root: Path) -> tuple[str, str, tuple[Entry, ...]]:
    """Enumerate ALL tree leaves. No configured file-count truncation."""
    root = root.resolve(strict=True)
    head = _git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise AtlasError("invalid pinned commit")
    tree = _git(root, "rev-parse", "--verify", head + "^{tree}").decode("ascii").strip()
    raw = _git(root, "ls-tree", "-r", "-z", "-l", "--full-tree", head)
    rules, known = load_taxonomy(root), load_feature_mappings(root)
    entries: list[Entry] = []
    paths: set[str] = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            meta, name = record.split(b"\t", 1)
            mode, kind, blob, size = meta.decode("ascii").split()
            path = _canonical(name.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise AtlasError("malformed Git tree entry") from exc
        if path in paths:
            raise AtlasError("duplicate Git path")
        paths.add(path)
        if mode not in {"100644", "100755", "120000", "160000"}:
            raise AtlasError("unsupported tree entry mode")
        if kind not in {"blob", "commit"} or (mode == "160000") != (kind == "commit"):
            raise AtlasError("unexpected tree object type")
        if not re.fullmatch(r"[0-9a-f]{40,64}", blob):
            raise AtlasError("invalid Git object identity")
        if size != "-" and (not size.isdigit() or int(size) < 0):
            raise AtlasError("invalid Git blob size")
        if kind == "blob" and size == "-":
            raise AtlasError("missing Git blob length")
        zone, owner, lifecycle = "unclassified", "unclassified", "unknown"
        for prefix, match_zone, match_owner, match_lifecycle in rules:
            if path == prefix.rstrip("/") or path.startswith(prefix):
                zone, owner, lifecycle = match_zone, match_owner, match_lifecycle
                break
        if path.startswith("satellites/branch-snapshots/"):
            lifecycle = "historical-snapshot"
        entries.append(Entry(path, mode, kind, blob, None if size == "-" else int(size),
                             zone, owner, _feature(path, zone, known), lifecycle))
    if not entries:
        raise AtlasError("empty repository tree is not indexable")
    if _git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip() != head:
        raise AtlasError("HEAD moved during snapshot")
    return head, tree, tuple(sorted(entries, key=lambda e: e.path))


def exact_duplicates(entries: Iterable[Entry]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in entries:
        if e.kind == "blob":
            groups[(e.blob, e.mode if e.mode == "120000" else "file")].append(e.path)
    result = []
    for (blob, _type), paths in sorted(groups.items()):
        if len(paths) > 1:
            result.append({"blob": blob, "paths": sorted(paths), "copies": len(paths),
                           "excess": len(paths) - 1})
    return sorted(result, key=lambda row: (-int(row["copies"]), str(row["blob"])))


def _shingles(data: bytes) -> frozenset[int]:
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        return frozenset()
    tokens = TOKEN.findall(source)
    if len(tokens) < 25:
        return frozenset()
    # Stable token-shingles; no Python hash() randomness.
    return frozenset(int.from_bytes(sha256(" ".join(tokens[i:i+5]).encode()).digest()[:8], "big")
                     for i in range(len(tokens)-4))


def _blobs(root: Path, hashes: list[str]) -> dict[str, bytes]:
    if not hashes:
        return {}
    output = _git(root, "cat-file", "--batch", input_bytes=("\n".join(hashes) + "\n").encode("ascii"))
    values: dict[str, bytes] = {}
    cursor = 0
    for digest in hashes:
        nl = output.find(b"\n", cursor)
        if nl < 0:
            raise AtlasError("incomplete Git blob batch")
        header = output[cursor:nl].decode("ascii")
        fields = header.split(" ")
        if len(fields) != 3 or fields[0] != digest or fields[1] != "blob" or not fields[2].isdigit():
            raise AtlasError("invalid Git batch object")
        size = int(fields[2])
        start, end = nl + 1, nl + 1 + size
        if size > MAX_BLOB_BYTES or end >= len(output) or output[end:end+1] != b"\n":
            raise AtlasError("Git batch object mismatch")
        values[digest] = output[start:end]
        cursor = end + 1
    if cursor != len(output):
        raise AtlasError("unexpected trailing Git batch data")
    return values


def near_duplicates(root: Path, entries: Iterable[Entry], *,
                    max_blobs: int = 600, threshold: float = 0.82) -> dict[str, object]:
    """Bounded, conservative candidate scan; never claims exhaustiveness."""
    if not 0 <= max_blobs <= 3000 or not 0.5 <= threshold <= 1:
        raise ValueError("invalid near-duplicate scan budget")
    by_name: dict[tuple[str, str], list[Entry]] = defaultdict(list)
    for e in entries:
        p = PurePosixPath(e.path)
        if (e.kind == "blob" and e.mode != "120000" and e.size is not None
                and 400 <= e.size <= MAX_BLOB_BYTES and p.suffix in CODE_EXTENSIONS
                and not e.path.startswith(("satellites/", "skeleton/ai/research/legacy/"))):
            by_name[(p.stem.casefold(), p.suffix)].append(e)
    # Pairs must share a filename stem; content-similar files with different
    # names are explicitly outside this conservative first-pass scanner.
    candidates = [sorted(bucket, key=lambda x: x.path) for _, bucket in sorted(by_name.items())
                  if 2 <= len(bucket) <= 24]
    selected: list[list[Entry]] = []
    hashes: set[str] = set()
    for bucket in candidates:
        ids = {e.blob for e in bucket}
        if len(ids) < 2 or len(hashes | ids) > max_blobs:
            continue
        selected.append(bucket)
        hashes.update(ids)
    values = _blobs(root, sorted(hashes))
    fingerprints = {h: _shingles(v) for h, v in values.items()}
    findings: list[dict[str, object]] = []
    for bucket in selected:
        for i, a in enumerate(bucket):
            for b in bucket[i+1:]:
                if a.blob == b.blob:
                    continue
                if min(a.size or 0, b.size or 0) / max(a.size or 1, b.size or 1) < 0.65:
                    continue
                lhs, rhs = fingerprints[a.blob], fingerprints[b.blob]
                if not lhs or not rhs:
                    continue
                score = len(lhs & rhs) / len(lhs | rhs)
                if score >= threshold:
                    findings.append({"a": a.path, "b": b.path,
                                     "similarity": round(score, 5), "method": "token-5gram-jaccard"})
    findings.sort(key=lambda row: (-float(row["similarity"]), str(row["a"]), str(row["b"])))
    return {"exhaustive": False, "comparison_scope": "same-stem-and-extension-canonical-code",
            "blobs_examined": len(hashes), "candidate_buckets": len(selected),
            "limit": max_blobs, "threshold": threshold, "pairs": findings}


def build(root: Path, *, near_limit: int = 0) -> tuple[dict[str, object], tuple[Entry, ...],
                                                        list[dict[str, object]], dict[str, object]]:
    commit, tree, entries = scan(root)
    duplicates = exact_duplicates(entries)
    near = near_duplicates(root, entries, max_blobs=near_limit) if near_limit else {
        "exhaustive": False, "comparison_scope": "not-run", "blobs_examined": 0,
        "candidate_buckets": 0, "limit": 0, "pairs": []}
    zones: Counter[str] = Counter(e.zone for e in entries)
    feature_counts: Counter[str] = Counter(e.feature for e in entries)
    modes: Counter[str] = Counter(e.mode for e in entries)
    # Stable digest computed over the complete inventory and its content identities.
    ledger = "".join(f"{e.mode} {e.blob} {e.path}\n" for e in entries).encode("utf-8")
    manifest: dict[str, object] = {
        "format": FORMAT, "commit": commit, "tree": tree, "inventory_digest": sha256(ledger).hexdigest(),
        "complete": True, "entries": len(entries), "blobs": sum(e.kind == "blob" for e in entries),
        "gitlinks": modes["160000"], "symlinks": modes["120000"],
        "zones": dict(sorted(zones.items())),
        "feature_count": len(feature_counts),
        "features": dict(sorted(feature_counts.items())),
        "exact_duplicate_groups": len(duplicates),
        "exact_duplicate_excess": sum(int(g["excess"]) for g in duplicates),
        "near_duplicate_exhaustive": False,
        "authorities": [".machine/repository.toml", "machine/ai_file_tree.json"],
    }
    return manifest, entries, duplicates, near


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n"


def write_index(directory: Path, manifest: dict[str, object], entries: Iterable[Entry],
                duplicates: Iterable[dict[str, object]], near: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise AtlasError("atlas destination cannot be symlink")
    parts = {"manifest.json": _json(manifest),
             "files.jsonl": "".join(_json(e.json()) for e in entries),
             "exact_duplicates.jsonl": "".join(_json(e) for e in duplicates),
             "near_duplicates.json": _json(near)}
    for name, content in parts.items():
        destination = directory / name
        if destination.is_symlink():
            raise AtlasError("atlas output symlink forbidden")
        tmp = directory / (name + ".tmp")
        if tmp.is_symlink():
            raise AtlasError("atlas temporary symlink forbidden")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(destination)


def query(index_dir: Path, root: Path, phrase: str, *, budget: int = 3000,
          limit: int = 25) -> dict[str, object]:
    """Fail-closed compact navigation. No repository source text is emitted."""
    if not 128 <= budget <= 30000 or not 1 <= limit <= 100:
        raise ValueError("invalid context budget")
    words = frozenset(WORD.findall(phrase.casefold()))
    if not words:
        raise ValueError("empty query")
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT or not manifest.get("complete"):
        raise AtlasError("untrusted index schema")
    head = _git(root.resolve(), "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    if manifest.get("commit") != head:
        raise AtlasError("stale index: rebuild at current pinned commit")
    paths: list[tuple[int, dict[str, object]]] = []
    ledger = sha256()
    seen = 0
    with (index_dir / "files.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            path = _canonical(row["path"])
            if not isinstance(row["blob"], str) or not re.fullmatch(r"[0-9a-f]{40,64}", row["blob"]):
                raise AtlasError("invalid indexed blob identity")
            ledger.update(f'{row["mode"]} {row["blob"]} {path}\n'.encode("utf-8"))
            seen += 1
            hay = frozenset(WORD.findall((path + " " + row["feature"] + " " + row["zone"]).casefold()))
            intersection = words & hay
            if intersection:
                score = len(intersection) * 10 + (5 if words <= hay else 0)
                paths.append((score, row))
    if seen != manifest.get("entries") or ledger.hexdigest() != manifest.get("inventory_digest"):
        raise AtlasError("index inventory completeness/integrity violation")
    paths.sort(key=lambda item: (-item[0], item[1]["path"]))
    result: list[dict[str, object]] = []
    used = 0
    for score, row in paths:
        item = {"path": row["path"], "blob": row["blob"], "feature": row["feature"],
                "zone": row["zone"], "owner": row["owner"], "score": score}
        encoded = _json(item).encode("utf-8")
        if used + len(encoded) > budget or len(result) >= limit:
            break
        used += len(encoded)
        result.append(item)
    return {"format": FORMAT, "commit": head, "query": phrase, "budget_bytes": budget,
            "used_bytes": used, "total_hits": len(paths), "hits": result}
