#!/usr/bin/env python3
"""GameForge CI smoke: walk one era, then materialise a Godot tree to disk.

Usage::

    python scripts/gameforge_materialise_smoke.py OUT_DIR [--era soulslike]
        [--archetype extraction] [--max-rounds 3] [--budget-ms 120000]
        [--overwrite]

Steps (all in-process, no Godot binary, no network):

1. ``skeleton.forge.walk_cli.walk_once(era)``: compile, plan, walk. Must pass.
2. ``Forge.materialise(..., target="godot", repair=True)``, glued the same way
   as ``skeleton/testing/test_materialise_e2e_acceptance.py``. The verifier must
   accept the result.
3. The emitted ``files`` mapping is written under OUT_DIR (relative paths only).

Prints per-phase budgets in ms plus a final JSON summary line. Exits 0 on
success, 1 on any failure (including blowing ``--budget-ms``), 2 on usage.
Forge state (quality ledger, provenance) goes to a throwaway temp dir so
OUT_DIR holds only the Godot project.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2
DEFAULT_ERA = "soulslike"
DEFAULT_BUDGET_MS = 120_000


def _ms(start: float) -> int:
    return int(round((time.perf_counter() - start) * 1000))


def _safe_relpath(path: str) -> PurePosixPath:
    rel = PurePosixPath(path)
    if not path or rel.is_absolute() or ".." in rel.parts or "\\" in path:
        raise ValueError(f"unsafe emitted path: {path!r}")
    return rel


def run_walk(era: str) -> Dict[str, Any]:
    from skeleton.forge.walk_cli import walk_once

    payload = walk_once(era)
    payload.pop("_steps_full", None)
    return payload


def run_materialise(era: str, *, state_root: Path, archetype: str, max_rounds: int) -> Dict[str, Any]:
    from skeleton.context.tensor import ContextTensor
    from skeleton.forge.archetypes import default_library
    from skeleton.forge.eras import compile_era
    from skeleton.forge.universal import Forge
    from skeleton.jeeves.builder import BuilderBrain

    forge = Forge(root=state_root)
    blueprint = default_library().build(forge, archetype)
    pack = compile_era(era)
    tensor = ContextTensor.from_era(era)
    build_plan = BuilderBrain().plan(pack, tensor=tensor, reading=None, cortex=None, last_walk=None)
    return forge.materialise(
        blueprint,
        era=era,
        target="godot",
        pack=pack,
        build_plan=build_plan.to_dict(),
        repair=True,
        max_rounds=max_rounds,
    )


def write_tree(files: Dict[str, str], out_dir: Path) -> List[str]:
    written: List[str] = []
    for path in sorted(files):
        body = files[path]
        if not isinstance(body, str):
            raise ValueError(f"emitted file {path!r} is not text")
        target = out_dir.joinpath(*_safe_relpath(path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written.append(path)
    return written


def _prepare_out(out_dir: Path, overwrite: bool) -> None:
    if out_dir.exists():
        if not out_dir.is_dir():
            raise ValueError(f"output path is not a directory: {out_dir}")
        if any(out_dir.iterdir()):
            if not overwrite:
                raise ValueError(f"output dir not empty (use --overwrite): {out_dir}")
            shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir")
    parser.add_argument("--era", default=DEFAULT_ERA)
    parser.add_argument("--archetype", default="extraction")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--budget-ms", type=int, default=DEFAULT_BUDGET_MS)
    parser.add_argument("--overwrite", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    if args.max_rounds < 1 or args.budget_ms < 1:
        print("FAIL usage: --max-rounds and --budget-ms must be >= 1", file=sys.stderr)
        return EXIT_USAGE

    from skeleton.forge.eras import list_eras

    if args.era not in set(list_eras()):
        print(f"FAIL usage: unknown era {args.era!r}", file=sys.stderr)
        return EXIT_USAGE

    out_dir = Path(args.out_dir).expanduser().resolve()
    summary: Dict[str, Any] = {"era": args.era, "archetype": args.archetype, "out_dir": str(out_dir)}
    budgets: Dict[str, int] = {}
    t_total = time.perf_counter()
    cwd = os.getcwd()
    state_root = Path(tempfile.mkdtemp(prefix="gf-smoke-state-"))
    try:
        _prepare_out(out_dir, args.overwrite)
        os.chdir(state_root)  # keep provenance/ledger side files out of the checkout

        t0 = time.perf_counter()
        walk = run_walk(args.era)
        budgets["walk_ms"] = _ms(t0)
        summary["walk"] = {k: walk.get(k) for k in ("label", "passed", "extracted", "collapsed", "t", "bound", "hops", "cores", "required_cores")}
        print(f"[budget] walk {budgets['walk_ms']} ms passed={walk.get('passed')}")
        if not walk.get("passed"):
            raise RuntimeError(f"walk failed for {args.era}: {(walk.get('notes') or ['no notes'])[-1]}")

        t0 = time.perf_counter()
        art = run_materialise(args.era, state_root=state_root, archetype=args.archetype, max_rounds=args.max_rounds)
        budgets["materialise_ms"] = _ms(t0)
        verification = art.get("verification") or {}
        loop = art.get("verify_loop") or {}
        summary["verification"] = {k: verification.get(k) for k in ("accepted", "score", "reason")}
        summary["verify_loop"] = {"accepted": loop.get("accepted"), "stopped_reason": loop.get("stopped_reason")}
        print(
            f"[budget] materialise {budgets['materialise_ms']} ms accepted={verification.get('accepted')} "
            f"score={verification.get('score')} files={art.get('file_count')}"
        )
        if verification.get("accepted") is not True:
            raise RuntimeError(f"forge verifier rejected the tree: {verification.get('reason')}")
        files = art.get("files")
        if not isinstance(files, dict) or "project.godot" not in files:
            raise RuntimeError("materialise returned no Godot project")

        t0 = time.perf_counter()
        written = write_tree(files, out_dir)
        budgets["write_ms"] = _ms(t0)
        summary["files_written"] = len(written)
        print(f"[budget] write {budgets['write_ms']} ms files={len(written)} -> {out_dir}")
    except Exception as exc:  # noqa: BLE001 - CI smoke reports any failure
        budgets["total_ms"] = _ms(t_total)
        summary.update(ok=False, error=f"{type(exc).__name__}: {exc}", budgets=budgets)
        print(f"FAIL {summary['error']}", file=sys.stderr)
        print(json.dumps(summary, sort_keys=True, default=str))
        return EXIT_FAIL
    finally:
        os.chdir(cwd)
        shutil.rmtree(state_root, ignore_errors=True)

    budgets["total_ms"] = _ms(t_total)
    summary["budgets"] = budgets
    over = budgets["total_ms"] > args.budget_ms
    summary["ok"] = not over
    print(f"[budget] total {budgets['total_ms']} ms (limit {args.budget_ms} ms)")
    print(json.dumps(summary, sort_keys=True, default=str))
    if over:
        print(f"FAIL budget: {budgets['total_ms']} ms > {args.budget_ms} ms", file=sys.stderr)
        return EXIT_FAIL
    print(f"PASS GameForge {args.era} walk -> materialise -> {summary['files_written']} files")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
