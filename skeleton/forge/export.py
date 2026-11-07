"""Real Godot export of a forged project: emit → import → export → boot.

``export_build`` writes the emitted file map to ``out_dir/project``, runs
``godot --headless --import`` and ``--export-release <preset>`` for each
requested preset (``Linux`` and optionally ``Web``, matching
``godot_emit._EXPORT_PRESETS``), then boots the exported Linux executable
headless for a bounded number of frames and scans its log with
:func:`skeleton.forge.playtest.scan_log`.

Export templates must be installed for the engine version
(``~/.local/share/godot/export_templates/4.3.stable``); without them the
preset step fails with ``templates-missing`` and the report says so.

CLI (used by ``.github/workflows/godot-playtest.yml``)::

    python -m skeleton.forge.export --era extraction_now --out dist/godot \\
        --preset Linux --preset Web
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from skeleton.forge.playtest import _run, resolve_binary, scan_log

PRESET_OUTPUTS: Dict[str, str] = {
    "Linux": "linux/game.x86_64",
    "Windows Desktop": "windows/game.exe",
    "Web": "web/index.html",
}
DEFAULT_TIMEOUT_S = 300.0


def _boot_exported(executable: Path, frames: int, timeout: float) -> Dict[str, Any]:
    os.chmod(executable, 0o755)
    code, log, timed_out = _run(
        [str(executable), "--headless", "--quit-after", str(frames)], executable.parent, timeout
    )
    errors = scan_log(log)
    if timed_out:
        errors.append(f"boot timed out after {timeout:.0f}s")
    return {
        "returncode": code,
        "timed_out": timed_out,
        "errors": errors[:50],
        "passed": code == 0 and not errors,
        "log_tail": log[-2000:],
    }


def export_build(files: Mapping[str, str], out_dir: str | Path, *,
                 presets: Sequence[str] = ("Linux",), binary: Optional[str] = None,
                 boot_frames: int = 120, timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Export the emitted project; return a report with artefact paths."""
    if not isinstance(files, Mapping) or "project.godot" not in files:
        raise ValueError("export_build needs an emitted Godot file map with project.godot")
    unknown = [p for p in presets if p not in PRESET_OUTPUTS]
    if unknown or not presets:
        raise ValueError(f"presets must be a non-empty subset of {sorted(PRESET_OUTPUTS)}; got {list(presets)}")
    cfg = files.get("export_presets.cfg", "")
    missing = [p for p in presets if f'name="{p}"' not in cfg]
    if missing:
        raise ValueError(f"export_presets.cfg does not declare {missing}")

    path, source, verified = resolve_binary(binary)
    report: Dict[str, Any] = {
        "binary": path, "binary_source": source, "verified": verified,
        "presets": {}, "passed": False,
    }
    if path is None:
        return {**report, "status": "unavailable", "reason": source}

    out = Path(out_dir)
    project = out / "project"
    from skeleton.forge.projector import write_project
    write_project(project, dict(files), overwrite=True)
    code, log, timed_out = _run([path, "--headless", "--path", str(project), "--import"], project, timeout)
    import_errors = scan_log(log)
    report["import"] = {"returncode": code, "timed_out": timed_out, "errors": import_errors[:50]}
    if timed_out or import_errors:
        return {**report, "status": "failed", "reason": "import"}

    all_ok = True
    for preset in presets:
        target = (out / PRESET_OUTPUTS[preset]).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        code, log, timed_out = _run(
            [path, "--headless", "--path", str(project), "--export-release", preset, str(target)],
            project, timeout,
        )
        entry: Dict[str, Any] = {"output": str(target), "returncode": code, "timed_out": timed_out}
        if "No export template found" in log:
            entry.update(ok=False, reason="templates-missing")
        else:
            entry["ok"] = code == 0 and target.is_file() and not timed_out
            if not entry["ok"]:
                entry["reason"] = "export-failed"
        entry["artefacts"] = sorted(
            str(p.relative_to(out)) for p in target.parent.iterdir() if p.is_file()
        ) if target.parent.is_dir() else []
        entry["bytes"] = sum(p.stat().st_size for p in target.parent.iterdir() if p.is_file()) \
            if target.parent.is_dir() else 0
        entry["log_tail"] = log[-1500:]
        if entry["ok"] and preset == "Linux":
            entry["boot"] = _boot_exported(target, boot_frames, timeout)
            entry["ok"] = entry["boot"]["passed"]
            if not entry["ok"]:
                entry["reason"] = "boot-failed"
        all_ok = all_ok and entry["ok"]
        report["presets"][preset] = entry
    return {**report, "status": "passed" if all_ok else "failed", "passed": all_ok,
            "out_dir": str(out)}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Forge an era and export a real Godot build.")
    parser.add_argument("--era", default="extraction_now")
    parser.add_argument("--out", default="dist/godot")
    parser.add_argument("--preset", action="append", dest="presets")
    parser.add_argument("--title", default=None)
    parser.add_argument("--report", default=None, help="write the JSON report here")
    args = parser.parse_args(argv)
    from skeleton.forge.eras import compile_era
    from skeleton.forge.godot_emit import emit_godot
    files = emit_godot(compile_era(args.era), title=args.title or f"Skeleton {args.era}")
    result = export_build(files, args.out, presets=tuple(args.presets or ["Linux"]))
    result["era"] = args.era
    text = json.dumps(result, indent=2, default=str)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
    summary = {k: result.get(k) for k in ("era", "status", "binary_source", "verified")}
    summary["presets"] = {k: {"ok": v.get("ok"), "reason": v.get("reason"), "bytes": v.get("bytes")}
                          for k, v in result.get("presets", {}).items()}
    print(json.dumps(summary, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["PRESET_OUTPUTS", "export_build", "main"]
