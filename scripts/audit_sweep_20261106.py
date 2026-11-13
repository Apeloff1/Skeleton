#!/usr/bin/env python3
"""Read every tracked file in a pinned checkout and record format/syntax defects.

Audit-only: never executes repository Python, never follows symlinks, writes only
its own JSONL and summary outputs into the GitHub runner workspace.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib

try:
    import yaml
except ImportError:
    yaml = None

SOURCE_TEXT_EXT = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".sh", ".bash", ".ps1", ".md", ".mdc", ".txt", ".toml", ".yml",
    ".yaml", ".json", ".jsonl", ".xml", ".html", ".css", ".scss",
    ".java", ".kt", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".gd",
}
SIZE_CEILING = 100_000_000
OUTDIR = Path("audit-sweep-results")


def bounded_source_bytes(path: Path, *, limit: int = SIZE_CEILING) -> bytes:
    """Bound text parsing even if a tracked file grows after the stat check."""
    if type(limit) is not int or limit < 0:
        raise ValueError("invalid tracked source byte bound")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("tracked source text exceeds audit byte bound")
    return data


def main() -> int:
    OUTDIR.mkdir(exist_ok=True)
    start = time.monotonic()
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "-z", "--full-name"],
        check=True, stdout=subprocess.PIPE,
    ).stdout
    paths = [os.fsdecode(item) for item in listed.split(b"\0") if item]
    counts = collections.Counter()
    suffixes = collections.Counter()
    defects = []
    sha_to_paths = {}
    seen_casefold = {}
    total_bytes = 0
    entries = []
    report_path = OUTDIR / "audit-files.jsonl"

    with report_path.open("w", encoding="utf-8") as detail:
        for path_string in paths:
            p = Path(path_string)
            suffix = p.suffix.lower()
            suffixes[suffix or "<no-ext>"] += 1
            record = {"path": path_string, "status": "ok", "kind": "regular"}
            folded = path_string.casefold()
            older = seen_casefold.setdefault(folded, path_string)
            if older != path_string:
                record["case_collision_with"] = older
                defects.append({"path": path_string, "error": "case-fold filename collision", "other": older})
            try:
                if p.is_symlink():
                    record["kind"] = "symlink"
                    target = os.readlink(p)
                    record["target"] = target
                    counts["symlinks"] += 1
                    # The target string is audited; the file is NOT dereferenced.
                    record["sha256"] = hashlib.sha256(os.fsencode(target)).hexdigest()
                elif not p.is_file():
                    raise ValueError("tracked path is absent or not a regular file")
                else:
                    size = p.stat().st_size
                    record["size"] = size
                    total_bytes += size
                    counts["readable_files"] += 1
                    if size > SIZE_CEILING:
                        record["status"] = "error"
                        defects.append({"path": path_string, "error": "file exceeds 100MB gate", "bytes": size})
                    digest = hashlib.sha256()
                    with p.open("rb") as inp:
                        for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                            digest.update(chunk)
                    h = digest.hexdigest()
                    record["sha256"] = h
                    prior = sha_to_paths.get(h)
                    if prior is None:
                        sha_to_paths[h] = path_string
                    else:
                        counts["duplicate-content_files"] += 1
                    if suffix in SOURCE_TEXT_EXT:
                        raw = bounded_source_bytes(p)
                        if suffix == ".py" or suffix == ".pyi":
                            compile(raw, path_string, "exec", dont_inherit=True)
                            counts["python_syntax_ok"] += 1
                        elif suffix == ".json":
                            json.loads(raw)
                            counts["json_ok"] += 1
                        elif suffix == ".jsonl":
                            for line_no, line in enumerate(raw.splitlines(), 1):
                                if line.strip():
                                    try:
                                        json.loads(line)
                                    except Exception as exc:
                                        raise ValueError(f"JSONL line {line_no}: {exc}") from exc
                            counts["jsonl_ok"] += 1
                        elif suffix == ".toml":
                            tomllib.loads(raw.decode("utf-8-sig"))
                            counts["toml_ok"] += 1
                        elif suffix in (".yaml", ".yml") and yaml is not None:
                            yaml.safe_load(raw)
                            counts["yaml_ok"] += 1
                        else:
                            raw.decode("utf-8-sig")
                            counts["decoded_text_ok"] += 1
                counts["examined"] += 1
            except Exception as exc:
                record["status"] = "error"
                record["error"] = f"{type(exc).__name__}: {exc}"
                defects.append({"path": path_string, "error": record["error"]})
                counts["examined"] += 1
            detail.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "tracked_paths": len(paths),
        "bytes_hashed": total_bytes,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "counts": dict(counts),
        "extensions": dict(suffixes.most_common()),
        "defects_count": len(defects),
        "defects": defects,
        "per_file_jsonl": str(report_path),
    }
    (OUTDIR / "audit-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "defects": defects[:100]}, indent=2))
    if len(defects) > 100:
        print(f"Additional {len(defects) - 100} defects in the JSON report.")
    return int(bool(defects))


if __name__ == "__main__":
    sys.exit(main())
