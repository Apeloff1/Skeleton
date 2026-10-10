"""Reproduce a complete tracked-text game inventory without importing code.

Usage: python scripts/audit_dragon_game_repository.py --out /tmp/audit.json
Inventory matches are deliberately broad; a hit is not a working capability.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import warnings


ROOT = Path(__file__).resolve().parents[1]
MATCH = re.compile(r"game|dragon|crawler|emulator|homebrew|godot|unity|unreal|storyline|porting", re.I)
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".yml", ".yaml", ".c", ".h", ".cpp", ".rs", ".toml"}


def inventory() -> dict:
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    rows, errors = [], []
    counts: Counter = Counter()
    for name in filter(None, names):
        path = ROOT / name
        if path.suffix not in EXTENSIONS:
            continue
        raw = path.read_bytes()
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not MATCH.search(name) and not MATCH.search(source):
            continue
        scope = ("historical_snapshot" if name.startswith("satellites/") else "test" if "test" in name.lower()
                 else "runtime" if name.startswith(("skeleton/", "backend/", "frontend/")) else "authority_or_docs")
        counts[scope] += 1
        row = {"path": name, "scope": scope, "sha256": sha256(raw).hexdigest(), "lines": len(source.splitlines())}
        if path.suffix == ".py":
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    tree = ast.parse(source)
                row["symbols"] = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
                row["imports"] = sorted({n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} |
                    {alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names})
            except SyntaxError as exc:
                errors.append({"path": name, "error": str(exc)})
        rows.append(row)
    return {"schema": "skeleton.dragon.repository_game_audit.v1",
        "base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "tracked_files": len(names)-1, "selected_files": len(rows), "counts": dict(counts),
        "python_parse_errors": errors,
        "scope_note": "Full tracked text scan and Python syntax/import inventory; not semantic review or execution of every file. Historical snapshots are not runtime capability proof.",
        "files": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = inventory()
    args.out.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=2))
