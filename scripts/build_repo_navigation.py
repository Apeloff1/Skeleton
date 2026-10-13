#!/usr/bin/env python3
"""Lossless, deterministic, sharded Git-tree navigation and duplicate inventory.

Includes every tracked Git object independently of machine-model scan budgets.
No source is moved, imported, executed, deleted, or auto-deduplicated. Stdlib only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import tomllib

SCHEMA = "skeleton.repository-navigation.v1"
OUTPUT = "machine/repo_navigation"
CODE = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".go", ".java", ".kt", ".c", ".h", ".cpp", ".cs"})
TOKEN = re.compile(r"[A-Za-z_]\w*|\d+|[^\s]", re.ASCII)
SKIP_NEAR = ("satellites/", "complete/", "skeleton/audio/", "skeleton/testing/", "tests/", "backend/tests/", "skeleton/cue/gb46/")


def dump(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def git_tree(root: Path) -> list[dict[str, object]]:
    raw = subprocess.check_output(["git", "ls-tree", "-r", "-z", "-l", "HEAD"], cwd=root)
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in raw.split(b"\x00"):
        if not entry:
            continue
        descriptor, filename = entry.split(b"\t", 1)
        mode, kind, oid, size = descriptor.decode("ascii").split()
        path = filename.decode("utf-8", "strict")
        if path == OUTPUT or path.startswith(OUTPUT + "/"):
            continue
        if path.startswith("/") or "\\" in path or any(x in ("", ".", "..") for x in path.split("/")):
            raise ValueError(f"unsafe Git path: {path!r}")
        if path in seen:
            raise ValueError(f"duplicate Git path: {path}")
        seen.add(path)
        if kind not in ("blob", "commit"):
            raise ValueError(f"unexpected Git object {kind}: {path}")
        rows.append({"p": path, "g": oid, "b": int(size) if size != "-" else None, "m": mode, "t": kind})
    return sorted(rows, key=lambda row: str(row["p"]))


def zones(root: Path) -> list[dict[str, object]]:
    config = tomllib.loads((root / ".machine/repository.toml").read_text("utf-8"))
    rules = config["zone"]
    names = [r["name"] for r in rules]
    if len(names) != len(set(names)):
        raise ValueError("repeated zone name in canonical machine taxonomy")
    return rules


def placement(path: str, rules: list[dict[str, object]]) -> dict[str, str]:
    for rule in rules:  # First match wins: matches the existing policy.
        if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in rule["prefixes"]):
            return {key: str(rule[key]) for key in ("name", "owner", "purpose", "lifecycle", "criticality")}
    return {"name": "unclassified", "owner": "unclassified", "purpose": "Unclassified repository path", "lifecycle": "transitional", "criticality": "medium"}


def feature_of(path: str) -> str:
    parts = path.split("/")
    if len(parts) < 2:
        return "root-config"
    if parts[0] == "satellites" and len(parts) >= 3:
        return "/".join(parts[:3])
    if parts[0] == "skeleton" and len(parts) >= 4 and parts[1] == "ai":
        return "/".join(parts[:4])
    if parts[0] == "frontend" and len(parts) >= 4 and parts[1] in ("features", "app", "src"):
        return "/".join(parts[:3])
    if parts[0] == "backend" and len(parts) >= 3:
        return "/".join(parts[:3])
    if parts[0] == "skeleton" and len(parts) >= 3:
        return "/".join(parts[:3])
    return "/".join(parts[:2])


def shard_of(path: str) -> str:
    parts = path.split("/")
    if len(parts) == 1:
        return "_root"
    if parts[0] == "skeleton":
        return "skeleton/" + (parts[1] if len(parts) > 2 else "_root")
    if parts[0] == "satellites":
        return "satellites/" + (parts[1] if len(parts) > 2 else "_root")
    return parts[0]


def shingles(text: str) -> frozenset[tuple[str, ...]]:
    tokens = TOKEN.findall(text)
    return frozenset(zip(*(tokens[i:] for i in range(5)))) if len(tokens) >= 5 else frozenset()


def near_duplicates(root: Path, files: list[dict[str, object]], *, threshold: float = 0.83, max_pairs: int = 12000) -> tuple[list[dict[str, object]], dict[str, int]]:
    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in files:
        path = str(row["p"])
        if (path.startswith(SKIP_NEAR) or Path(path).suffix.lower() not in CODE or
                row["t"] != "blob" or row["m"] == "120000" or
                row["b"] is None or not 30 <= int(row["b"]) <= 250_000):
            continue
        name = Path(path).name
        if name in ("__init__.py", "index.ts", "index.tsx", "__main__.py"):
            continue
        buckets[name].append(row)
    cached: dict[str, frozenset[tuple[str, ...]]] = {}
    results: list[dict[str, object]] = []
    stats = {"basename_groups": len(buckets), "oversized_groups": 0, "pair_limit_reached": 0, "candidate_pairs": 0, "unreadable": 0}

    def load(row: dict[str, object]) -> frozenset[tuple[str, ...]]:
        p = str(row["p"])
        if p not in cached:
            try:
                raw = (root / p).read_bytes()
                if len(raw) != row["b"]:
                    raise ValueError("working tree size differs from Git")
                cached[p] = shingles(raw.decode("utf-8"))
            except (OSError, UnicodeError, ValueError):
                stats["unreadable"] += 1
                cached[p] = frozenset()
        return cached[p]

    for name, group in sorted(buckets.items()):
        if len(group) < 2:
            continue
        if len(group) > 32:
            stats["oversized_groups"] += 1
            continue
        group = sorted(group, key=lambda row: str(row["p"]))
        for i, left in enumerate(group):
            for right in group[i + 1:]:
                if left["g"] == right["g"]:
                    continue
                a, b = int(left["b"]), int(right["b"])
                if min(a, b) / max(a, b) < 0.75:
                    continue
                if stats["candidate_pairs"] >= max_pairs:
                    stats["pair_limit_reached"] = 1
                    return results, stats
                stats["candidate_pairs"] += 1
                aa, bb = load(left), load(right)
                if not aa or not bb:
                    continue
                score = len(aa & bb) / len(aa | bb)
                if score >= threshold:
                    results.append({"a": left["p"], "b": right["p"], "jaccard_5gram": round(score, 4), "confidence": "candidate-requires-review"})
    return results, stats


def build(root: Path, *, compute_near: bool = True) -> dict[str, str]:
    files = git_tree(root)
    rules = zones(root)
    shards: dict[str, list[dict[str, object]]] = defaultdict(list)
    grouped: dict[str, dict[str, object]] = {}
    dirs: dict[str, dict[str, object]] = {}
    exact: dict[str, list[str]] = defaultdict(list)
    unclassified: list[str] = []
    bytes_total = 0
    zone_counts: Counter[str] = Counter()
    fingerprint = sha256()
    for row in files:
        p = str(row["p"])
        z = placement(p, rules)
        f = feature_of(p)
        row["z"] = z["name"]
        row["f"] = f
        fingerprint.update(dump([row["p"], row["g"], row["b"], row["m"], row["t"]]).encode("utf-8"))
        zone_counts[z["name"]] += 1
        if z["name"] == "unclassified":
            unclassified.append(p)
        if row["t"] == "blob":
            exact[str(row["g"])].append(p)
        bytes_total += int(row["b"] or 0)
        shards[shard_of(p)].append(row)
        feat = grouped.setdefault(f, {"files": 0, "bytes": 0, "zones": Counter(), "extensions": Counter(), "tests": 0, "entrypoints": [], "examples": []})
        feat["files"] += 1
        feat["bytes"] += int(row["b"] or 0)
        feat["zones"][z["name"]] += 1
        feat["extensions"][Path(p).suffix.lower() or "(no-extension)"] += 1
        if "/test" in p or p.split("/")[-1].startswith("test_"):
            feat["tests"] += 1
        if Path(p).name in ("__main__.py", "main.py", "cli.py", "app.py", "server.py", "index.ts", "index.js", "package.json") and len(feat["entrypoints"]) < 8:
            feat["entrypoints"].append(p)
        if len(feat["examples"]) < 3:
            feat["examples"].append(p)
        parts = p.split("/")
        for depth in range(1, min(len(parts), 5)):
            prefix = "/".join(parts[:depth])
            directory = dirs.setdefault(prefix, {"files": 0, "bytes": 0, "zones": Counter()})
            directory["files"] += 1
            directory["bytes"] += int(row["b"] or 0)
            directory["zones"][z["name"]] += 1
    dupes = [{"git_blob": key, "paths": sorted(paths)} for key, paths in exact.items() if len(paths) > 1]
    dupes.sort(key=lambda row: (-len(row["paths"]), row["git_blob"]))
    near, near_stats = near_duplicates(root, files) if compute_near else ([], {"status": "not-computed"})
    record = {
        "schema": SCHEMA, "tracked_objects": len(files),
        "blobs": sum(row["t"] == "blob" for row in files),
        "submodules": sum(row["t"] == "commit" for row in files),
        "bytes": bytes_total,
        "git_snapshot_sha256": fingerprint.hexdigest(),
        "zones": len(zone_counts), "features": len(grouped), "shards": len(shards),
        "directories_indexed": len(dirs),
        "exact_duplicate_groups": len(dupes),
        "extra_exact_copies": sum(len(d["paths"]) - 1 for d in dupes),
        "near_duplicate_candidates": len(near),
        "near_scan": near_stats, "unclassified_count": len(unclassified),
        "authorities": {"taxonomy": ".machine/repository.toml", "runtime_atlas": "skeleton/repo_machine/atlas.py", "ai_migrations": "machine/ai_file_tree.json", "symbol_index": ".machine/code-search-index.json (workflow artifact)"},
        "navigation": {"groups": "features.json", "directory_tree": "tree.json", "all_files": "files/", "duplicates": "duplicates.json", "near_duplicates": "near_duplicates.json", "zones": "zones.json", "unclassified": "unclassified.json"},
        "warnings": ["Duplicate bytes do not imply redundant behavior or safe removal", "Near-duplicates are heuristic review candidates, not proof of equivalent contracts"],
    }
    def counts(c: Counter[str]) -> dict[str, int]:
        return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))
    feature_rows = {k: {**v, "zones": counts(v["zones"]), "extensions": counts(v["extensions"])} for k, v in sorted(grouped.items())}
    directory_rows = {k: {**v, "zones": counts(v["zones"])} for k, v in sorted(dirs.items())}
    zone_rows = [{"name": r["name"], "owner": r["owner"], "lifecycle": r["lifecycle"], "criticality": r["criticality"], "purpose": r["purpose"], "prefixes": r["prefixes"], "file_count": zone_counts[r["name"]]} for r in rules]
    outputs = {
        "manifest.json": dump(record),
        "features.json": dump({"schema": SCHEMA, "features": feature_rows}),
        "tree.json": dump({"schema": SCHEMA, "directories": directory_rows}),
        "zones.json": dump({"schema": SCHEMA, "zones": zone_rows}),
        "duplicates.json": dump({"schema": SCHEMA, "identity": "Git blob object ID (byte-identical)", "groups": dupes}),
        "near_duplicates.json": dump({"schema": SCHEMA, "method": "same basename + comparable size + token five-shingle Jaccard >= 0.83", "stats": near_stats, "candidates": near}),
        "unclassified.json": dump({"schema": SCHEMA, "paths": unclassified}),
    }
    for s, rows in sorted(shards.items()):
        outputs[f"files/{s}.jsonl"] = "".join(dump(row) for row in rows)
    return outputs


def write_index(root: Path, output: Path, *, compute_near: bool = True) -> int:
    generated = build(root, compute_near=compute_near)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for old in output.rglob("*"):
        if old.is_file() and old.suffix in (".json", ".jsonl") and old.relative_to(output).as_posix() not in generated:
            old.unlink()
    for name, content in generated.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise ValueError(f"refusing symlink output: {target}")
        if target.exists() and target.read_text("utf-8") == content:
            continue
        target.write_text(content, encoding="utf-8", newline="\n")
    return len(generated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path(OUTPUT))
    parser.add_argument("--skip-near", action="store_true", help="For quick inventory diagnostics; full CI runs the near scan")
    opts = parser.parse_args()
    root = opts.root.resolve()
    target = opts.output if opts.output.is_absolute() else root / opts.output
    written = write_index(root, target, compute_near=not opts.skip_near)
    manifest = json.loads((target / "manifest.json").read_text("utf-8"))
    print(f"navigation files={manifest['tracked_objects']} exact={manifest['exact_duplicate_groups']} near={manifest['near_duplicate_candidates']} outputs={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
