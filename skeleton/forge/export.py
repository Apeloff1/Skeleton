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
import math
import stat
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from skeleton.forge.playtest import _run, resolve_binary, scan_log

PRESET_OUTPUTS: Dict[str, str] = {
    "Linux": "linux/game.x86_64",
    "Windows Desktop": "windows/game.exe",
    "Web": "web/index.html",
}
DEFAULT_TIMEOUT_S = 300.0
MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_OUTPUT_FILES = 64


def _safe_directory(path: Path) -> Path:
    """Walk through directories without following existing symlinks.

    The resulting output tree must be private to the current build worker:
    this guard is not a substitute for an adversarial concurrent-filesystem
    sandbox. No output target may already exist.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("native Godot exporter requires POSIX no-follow directory custody")
    if ".." in Path(path).parts:
        raise ValueError("native export output traversal refused")
    target = Path(os.path.abspath(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = os.open("/", flags)
    try:
        for part in target.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
    finally:
        os.close(fd)
    return target


def _anchored_directory(path: Path) -> int:
    """Open all ancestor directories without following a single symlink.

    Returns a caller-owned directory FD. This rejects uncanonical traversal
    rather than relying on Path.resolve()/an absolute path's final O_NOFOLLOW.
    """
    if os.name != "posix" or not all(
        hasattr(os, key) for key in ("O_DIRECTORY", "O_NOFOLLOW")
    ):
        raise ValueError("descriptor-relative export verification unavailable")
    raw = Path(path)
    if ".." in raw.parts:
        raise ValueError("export directory traversal refused")
    absolute = Path(os.path.abspath(raw))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    dfd = os.open("/", flags)
    try:
        for name in absolute.parts[1:]:
            next_fd = os.open(name, flags, dir_fd=dfd)
            os.close(dfd)
            dfd = next_fd
        return dfd
    except BaseException:
        os.close(dfd)
        raise


def _bounded_output_inventory(parent: Path) -> list[Path]:
    """Inspect at most MAX_OUTPUT_FILES + 1 entries from an opened parent FD."""
    dfd = _anchored_directory(parent)
    names: list[str] = []
    try:
        with os.scandir(dfd) as iterator:
            for entry in iterator:
                if len(names) >= MAX_OUTPUT_FILES:
                    raise ValueError("export output file budget exhausted")
                if not entry.is_file(follow_symlinks=False):
                    raise ValueError("unsafe export output directory entry")
                names.append(entry.name)
        return [parent / name for name in sorted(names)]
    finally:
        os.close(dfd)


def _regular_output(path: Path) -> bool:
    """Never accept a symlink, directory, device or empty native artifact."""
    try:
        st = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and 0 < st.st_size <= MAX_OUTPUT_BYTES


def _artifact_evidence(path: Path) -> tuple[str, int]:
    """Hash one inode from no-follow ancestor FDs and revalidate its path.

    Verification cannot certify an unlinked old inode after a same-name
    replacement, and must not follow an intermediate symlink to a foreign
    output tree before reading native code or signed resource packs.
    """
    path = Path(path)
    if path.name in ("", ".", ".."):
        raise ValueError("invalid native artifact basename")
    try:
        dfd = _anchored_directory(path.parent)
    except OSError as exc:
        raise ValueError("unsafe native artifact ancestor") from exc
    try:
        try:
            fd = os.open(
                path.name,
                os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=dfd,
            )
        except OSError as exc:
            raise ValueError("unsafe native artifact path") from exc
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or not 0 < before.st_size <= MAX_OUTPUT_BYTES):
                raise ValueError("unsafe or oversized native artifact")
            hasher = hashlib.sha256()
            count = 0
            while True:
                chunk = os.read(fd, min(1 << 20, MAX_OUTPUT_BYTES + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_OUTPUT_BYTES:
                    raise ValueError("artifact exceeded byte cap during hashing")
                hasher.update(chunk)
            after = os.fstat(fd)
            fields = (
                "st_dev", "st_ino", "st_mode", "st_nlink", "st_size",
                "st_mtime_ns", "st_ctime_ns",
            )
            before_id = tuple(getattr(before, attr) for attr in fields)
            after_id = tuple(getattr(after, attr) for attr in fields)
            try:
                linked = os.stat(
                    path.name, dir_fd=dfd, follow_symlinks=False,
                )
            except OSError as exc:
                raise ValueError("artifact path disappeared during hashing") from exc
            linked_id = tuple(getattr(linked, attr) for attr in fields)
            if (count != before.st_size or before_id != after_id
                    or after_id != linked_id
                    or not stat.S_ISREG(linked.st_mode) or linked.st_nlink != 1):
                raise ValueError("artifact changed or path replaced during hashing")
            # A swap of an intermediate directory after open leaves the
            # original FD valid but no longer reachable at its source path.
            try:
                reachable_fd = _anchored_directory(path.parent)
            except OSError as exc:
                raise ValueError("artifact parent changed during hashing") from exc
            try:
                current_dir = os.fstat(reachable_fd)
                held_dir = os.fstat(dfd)
                if (current_dir.st_dev, current_dir.st_ino) != (
                    held_dir.st_dev, held_dir.st_ino,
                ):
                    raise ValueError("artifact parent changed during hashing")
            finally:
                os.close(reachable_fd)
            return hasher.hexdigest(), count
        finally:
            os.close(fd)
    finally:
        os.close(dfd)


def _artifact_digest(path: Path) -> str:
    """Preserve the public digest API while requiring full custody evidence."""
    return _artifact_evidence(path)[0]

def _boot_exported(executable: Path, frames: int, timeout: float) -> Dict[str, Any]:
    if not _regular_output(executable):
        raise ValueError("unsafe or missing Linux executable")
    os.chmod(executable, 0o755, follow_symlinks=False)
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
    from skeleton.forge.source_manifest import source_manifest
    source_manifest(files)
    if (type(boot_frames) is not int or not 1 <= boot_frames <= 100000
            or type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 1 <= timeout <= 1800):
        raise ValueError("bounded Godot export boot frames and timeout required")
    if not isinstance(presets, (tuple, list)) or len(presets) > len(PRESET_OUTPUTS):
        raise ValueError("bounded native export preset inventory required")
    if any(type(p) is not str for p in presets) or len(set(presets)) != len(presets):
        raise ValueError("native export presets must be distinct known strings")
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
        "release_certified": False, "device_qualified": False,
    }
    if path is None:
        return {**report, "status": "unavailable", "reason": source}

    out = _safe_directory(Path(out_dir))
    project = out / "project"
    if project.exists() or project.is_symlink():
        raise ValueError("Godot export project output already exists; no clobber allowed")
    from skeleton.forge.projector import write_project
    write_project(project, dict(files), overwrite=False)
    code, log, timed_out = _run([path, "--headless", "--path", str(project), "--import"], project, timeout)
    import_errors = scan_log(log)
    report["import"] = {"returncode": code, "timed_out": timed_out, "errors": import_errors[:50]}
    if code != 0 or timed_out or import_errors:
        return {**report, "status": "failed", "reason": "import"}

    all_ok = True
    for preset in presets:
        relative = Path(PRESET_OUTPUTS[preset])
        parent = _safe_directory(out / relative.parent)
        target = parent / relative.name
        if target.exists() or target.is_symlink():
            raise ValueError("Godot export target already exists; refusing overwrite")
        code, log, timed_out = _run(
            [path, "--headless", "--path", str(project), "--export-release", preset, str(target)],
            project, timeout,
        )
        entry: Dict[str, Any] = {"output": str(target), "returncode": code, "timed_out": timed_out}
        if "No export template found" in log:
            entry.update(ok=False, reason="templates-missing")
        else:
            entry["ok"] = code == 0 and _regular_output(target) and not timed_out
            if not entry["ok"]:
                entry["reason"] = "export-failed"
        try:
            artefacts = _bounded_output_inventory(parent)
        except (OSError, ValueError):
            entry["ok"], entry["reason"] = False, "unsafe-or-unbounded-artifacts"
            artefacts = []
        entry["artefacts"] = [str(item.relative_to(out)) for item in artefacts]
        entry["bytes"] = 0
        entry["sha256"] = {}
        if entry["ok"]:
            try:
                evidence = {
                    str(item.relative_to(out)): _artifact_evidence(item)
                    for item in artefacts
                }
                entry["bytes"] = sum(size for _, size in evidence.values())
                if entry["bytes"] > MAX_OUTPUT_BYTES:
                    raise ValueError("aggregate export byte budget exhausted")
                entry["sha256"] = {
                    name: digest for name, (digest, _) in evidence.items()
                }
                if preset == "Linux" and not _regular_output(target.with_suffix(".pck")):
                    raise ValueError("missing Linux game resource pack")
                if preset == "Web" and not _regular_output(target.with_suffix(".wasm")):
                    raise ValueError("missing Web engine WASM payload")
            except (OSError, ValueError):
                entry["ok"], entry["reason"] = False, "artifact-custody-failed"
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
