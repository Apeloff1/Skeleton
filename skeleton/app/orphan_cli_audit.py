"""Bounded, non-executing inventory of candidate installed Python CLI gaps.

A static source-reference inventory is neither reachability proof nor
permission to activate a module. No source modules are imported.
"""
from __future__ import annotations

import argparse
import ast
import configparser
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tomllib
from typing import Sequence


class AuditError(ValueError):
    pass


@dataclass(frozen=True)
class ScanBudget:
    max_entries: int = 150_000
    max_candidates: int = 4_096
    max_file_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 128 * 1024 * 1024

    def __post_init__(self) -> None:
        for value, low, high in (
            (self.max_entries, 1, 1_000_000),
            (self.max_candidates, 1, 32_768),
            (self.max_file_bytes, 1, 16 * 1024 * 1024),
            (self.max_total_bytes, 1, 512 * 1024 * 1024),
        ):
            if type(value) is not int or not low <= value <= high:
                raise AuditError("invalid scan budget")


@dataclass(frozen=True)
class Candidate:
    module: str
    path: str
    source_sha256: str
    source_bytes: int
    callables: tuple[str, ...]
    argv_compatible: tuple[str, ...]
    modern_scripts: tuple[str, ...]
    legacy_scripts: tuple[str, ...]
    root_import_attributes: tuple[str, ...]
    classification: str


class _ReadBudget:
    def __init__(self, limits: ScanBudget):
        self.limits = limits
        self.consumed = 0

    def read(self, path: Path) -> bytes:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise AuditError("nonregular source")
        cap = min(self.limits.max_file_bytes,
                  self.limits.max_total_bytes - self.consumed)
        if before.st_size > cap:
            raise AuditError("source byte ceiling")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags)
        try:
            initial = os.fstat(fd)
            signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if not stat.S_ISREG(initial.st_mode) or signature(initial) != signature(before):
                raise AuditError("source changed before read")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(cap + 1)
            if len(raw) > cap or len(raw) != initial.st_size:
                raise AuditError("source byte ceiling or size changed")
            if signature(os.fstat(fd)) != signature(initial) or signature(path.lstat()) != signature(initial):
                raise AuditError("source changed during read")
            self.consumed += len(raw)
            return raw
        finally:
            os.close(fd)


def _metadata(root: Path, reader: _ReadBudget):
    modern = tomllib.loads(reader.read(root / "pyproject.toml").decode("utf-8"))
    scripts = modern.get("project", {}).get("scripts", {})
    if not isinstance(scripts, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in scripts.items()
    ):
        raise AuditError("invalid modern console metadata")
    legacy_config = configparser.ConfigParser(interpolation=None)
    legacy_config.read_string(reader.read(root / "setup.cfg").decode("utf-8"))
    legacy = {}
    for line in legacy_config["options.entry_points"]["console_scripts"].splitlines():
        if not line.strip():
            continue
        key, sep, target = line.partition("=")
        key, target = key.strip(), target.strip()
        if not sep or not key or not target or key in legacy:
            raise AuditError("invalid legacy console metadata")
        legacy[key] = target
    root_ast = ast.parse(reader.read(root / "skeleton" / "__main__.py"), filename="skeleton/__main__.py")
    imports: dict[str, set[str]] = {}
    for node in ast.walk(root_ast):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.setdefault(node.module, set()).update(n.name for n in node.names)
    return scripts, legacy, imports


def _module(path: Path, root: Path) -> str:
    names = path.relative_to(root).with_suffix("").parts
    if not all(n.isidentifier() for n in names):
        return ""
    return ".".join(names)


def _entry_functions(tree: ast.AST):
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ("main", "run", "cli")]
    names = tuple(sorted({f.name for f in funcs}))
    compatible = []
    for func in funcs:
        args = func.args
        positional = [*args.posonlyargs, *args.args]
        required = len(positional) - len(args.defaults)
        required_keywords = any(default is None for default in args.kw_defaults)
        if positional and positional[0].arg in ("argv", "args", "arguments") and required <= 1 and not required_keywords:
            compatible.append(func.name)
    return names, tuple(sorted(set(compatible)))


def _bindings(scripts, module):
    return tuple(sorted(f"{name}={target}" for name, target in scripts.items()
                        if target.split(":", 1)[0] == module))


def _classification(modern, legacy, imported, names, compatible):
    if modern != legacy:
        return "metadata_drift"
    if modern and imported:
        return "console_and_root_reference"
    if modern:
        return "console_only"
    if imported:
        return "root_reference_only"
    if compatible:
        return "unregistered_argv_candidate"
    if names:
        return "unregistered_other_signature"
    return "no_recognized_entry_function"


def scan(root: Path, *, budget: ScanBudget = ScanBudget()) -> dict:
    root = Path(root).resolve(strict=True)
    package = root / "skeleton"
    if not stat.S_ISDIR(package.lstat().st_mode):
        raise AuditError("skeleton source root must be a real directory")
    reader = _ReadBudget(budget)
    modern, legacy, root_imports = _metadata(root, reader)
    pending = [package]
    records: list[Candidate] = []
    issues: list[dict] = []
    seen = 0
    candidates = 0
    complete = True
    skipped_links = 0
    while pending and complete:
        directory = pending.pop()
        try:
            if not stat.S_ISDIR(directory.lstat().st_mode):
                raise AuditError("directory changed")
            children = []
            with os.scandir(directory) as iterator:
                for child in iterator:
                    seen += 1
                    if seen > budget.max_entries:
                        complete = False
                        break
                    children.append(child)
            if not complete:
                break
            for child in sorted(children, key=lambda item: item.name):
                path = Path(child.path)
                if child.is_symlink():
                    skipped_links += 1
                    continue
                if child.is_dir(follow_symlinks=False):
                    if child.name not in ("tests", "testing", "__pycache__") and not child.name.startswith("."):
                        pending.append(path)
                    continue
                if not child.is_file(follow_symlinks=False):
                    continue
                if not (child.name in ("cli.py", "__main__.py") or child.name.endswith("_cli.py")):
                    continue
                candidates += 1
                if candidates > budget.max_candidates:
                    complete = False
                    break
                relative = path.relative_to(root).as_posix()
                module = _module(path, root)
                if not module:
                    issues.append({"path": relative, "reason": "invalid_module_path"})
                    continue
                try:
                    raw = reader.read(path)
                    tree = ast.parse(raw, filename=relative)
                    names, compatible = _entry_functions(tree)
                except (AuditError, OSError, SyntaxError, UnicodeError, RecursionError) as error:
                    issues.append({"path": relative, "reason": type(error).__name__})
                    continue
                m = _bindings(modern, module)
                l = _bindings(legacy, module)
                imported = tuple(sorted(root_imports.get(module, ())))
                records.append(Candidate(
                    module, relative, hashlib.sha256(raw).hexdigest(), len(raw),
                    names, compatible, m, l, imported,
                    _classification(m, l, imported, names, compatible),
                ))
        except (OSError, AuditError) as error:
            issues.append({"path": directory.relative_to(root).as_posix(),
                           "reason": type(error).__name__})
    records.sort(key=lambda item: item.module)
    totals: dict[str, int] = {}
    for item in records:
        totals[item.classification] = totals.get(item.classification, 0) + 1
    return {
        "schema": "skeleton.installed-cli-source-audit.v1",
        "complete": complete and not issues and not skipped_links,
        "entry_limit_reached": not complete,
        "entries_observed": min(seen, budget.max_entries),
        "candidate_paths_observed": min(candidates, budget.max_candidates),
        "source_bytes_read": reader.consumed,
        "skipped_symlinks": skipped_links,
        "counts": totals,
        "issues": sorted(issues, key=lambda x: (x["path"], x["reason"])),
        "candidates": [asdict(item) for item in records],
        "runtime_reachability_verified": False,
        "execution_authorized": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--max-entries", type=int, default=150_000)
    parser.add_argument("--max-candidates", type=int, default=4096)
    parser.add_argument("--max-file-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--candidates-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = scan(args.root, budget=ScanBudget(args.max_entries, args.max_candidates,
                                                   args.max_file_bytes, args.max_total_bytes))
    except (AuditError, OSError, SyntaxError, UnicodeError, KeyError, configparser.Error) as error:
        print(json.dumps({"error": type(error).__name__, "complete": False}), file=sys.stderr)
        return 2
    if args.candidates_only:
        result["candidates"] = [c for c in result["candidates"]
                                if c["classification"].startswith("unregistered_")
                                or c["classification"] == "metadata_drift"]
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["complete"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
