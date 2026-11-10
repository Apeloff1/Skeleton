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
from contextlib import closing
import json
import os
import sys
import math
import stat
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from skeleton.forge.playtest import _run, resolve_binary, scan_log
from skeleton.godot_export.provenance import _digest_beneath

PRESET_OUTPUTS: Dict[str, str] = {
    "Linux": "linux/game.x86_64",
    "Windows Desktop": "windows/game.exe",
    "Web": "web/index.html",
}
DEFAULT_TIMEOUT_S = 300.0
MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_OUTPUT_FILES = 64
MAX_EXPORT_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024


def _open_directory(path: Path) -> tuple[Path, int]:
    """Create or open each directory relative to a no-follow parent fd."""
    if (os.name != "posix"
            or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "supports_dir_fd")
            or not all(fn in os.supports_dir_fd for fn in
                       (os.open, os.mkdir, os.unlink))):
        raise ValueError("native Godot exporter requires POSIX no-follow directory custody")
    target = Path(os.path.abspath(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for component in target.parts[1:]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return target, fd
    except BaseException:
        os.close(fd)
        raise


def _safe_directory(path: Path) -> Path:
    """Prepare a no-follow directory; this is not an OS sandbox."""
    target, dfd = _open_directory(path)
    os.close(dfd)
    return target


def _verify_report_parent(parent: Path, dfd: int) -> None:
    """Require the original open directory to remain reachable by its path."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current = os.open("/", flags)
    try:
        try:
            for component in parent.parts[1:]:
                child = os.open(component, flags, dir_fd=current)
                os.close(current)
                current = child
            before, after = os.fstat(dfd), os.fstat(current)
        except OSError as exc:
            raise ValueError("report parent changed during publication") from exc
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("report parent changed during publication")
    finally:
        os.close(current)


def _write_report_new(path: Path, text: str) -> None:
    """Publish bounded create-only receipts with post-write path revalidation.

    Never interpret a written fd as proof that the original path still points
    to it. A renamed or symlink-substituted parent must not produce a
    successful report receipt. On any failure, unlink only our own inode.
    """
    if type(text) is not str:
        raise ValueError("report must be textual JSON")
    data = text.encode("utf-8")
    if len(data) > MAX_REPORT_BYTES:
        raise ValueError("report byte budget exceeded")
    path = Path(path)
    if path.name in ("", ".", ".."):
        raise ValueError("invalid report filename")
    parent, dfd = _open_directory(path.parent)
    created: os.stat_result | None = None
    completed = False
    try:
        fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=dfd,
        )
        created = os.fstat(fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(dfd)
        _verify_report_parent(parent, dfd)
        linked = os.stat(path.name, dir_fd=dfd, follow_symlinks=False)
        if (linked.st_dev, linked.st_ino) != (created.st_dev, created.st_ino):
            raise ValueError("report path changed during publication")
        if (not stat.S_ISREG(linked.st_mode)
                or linked.st_nlink != 1 or linked.st_size != len(data)):
            raise ValueError("report file changed during publication")
        # A same-size rewrite is invisible to the inode/size checks above.
        # Reopen the published entry relative to the held parent and compare
        # the actual bounded bytes before returning a successful receipt.
        # No direct path open or following of a substituted symbolic link.
        read_fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=dfd,
        )
        try:
            read_before = os.fstat(read_fd)
            if (not stat.S_ISREG(read_before.st_mode)
                    or read_before.st_nlink != 1
                    or read_before.st_size != len(data)
                    or (read_before.st_dev, read_before.st_ino) !=
                    (created.st_dev, created.st_ino)):
                raise ValueError("report identity changed during verification")
            with os.fdopen(read_fd, "rb", closefd=False) as handle:
                observed = handle.read(len(data) + 1)
            read_after = os.fstat(read_fd)
            if (observed != data
                    or (read_before.st_size, read_before.st_mtime_ns,
                        read_before.st_ctime_ns) !=
                    (read_after.st_size, read_after.st_mtime_ns,
                     read_after.st_ctime_ns)):
                raise ValueError("report contents changed during verification")
            reachable = os.stat(
                path.name, dir_fd=dfd, follow_symlinks=False,
            )
            if (reachable.st_dev, reachable.st_ino) != (
                    read_after.st_dev, read_after.st_ino):
                raise ValueError("report path replaced during verification")
        finally:
            os.close(read_fd)
        _verify_report_parent(parent, dfd)
        completed = True
    finally:
        try:
            if not completed and created is not None:
                try:
                    linked = os.stat(path.name, dir_fd=dfd, follow_symlinks=False)
                    if (linked.st_dev, linked.st_ino) == (
                        created.st_dev, created.st_ino
                    ):
                        os.unlink(path.name, dir_fd=dfd)
                except FileNotFoundError:
                    pass
        finally:
            os.close(dfd)


def _regular_output(path: Path) -> bool:
    """Never accept a symlink, directory, device or empty native artifact."""
    try:
        st = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and 0 < st.st_size <= MAX_OUTPUT_BYTES


def _artifact_digest(path: Path) -> str:
    """Digest output through no-follow ancestors, not a path-only open.

    The shared provenance primitive re-anchors the parent after streaming,
    verifies the current leaf, and allows the export's explicit 2 GiB cap.
    """
    if not _regular_output(path):
        raise ValueError("unsafe or oversized native artifact")
    digest, size = _digest_beneath(
        Path(path).parent, Path(path).name, max_bytes=MAX_OUTPUT_BYTES,
    )
    if not 0 < size <= MAX_OUTPUT_BYTES:
        raise ValueError("unsafe or empty native artifact")
    return digest


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
    cumulative_output_bytes = 0
    for preset in presets:
        relative = Path(PRESET_OUTPUTS[preset])
        parent, output_dfd = _open_directory(out / relative.parent)
        with closing(output_dfd):
            target = parent / relative.name
            if target.exists() or target.is_symlink():
                raise ValueError("Godot export target already exists; refusing overwrite")
            code, log, timed_out = _run(
                [path, "--headless", "--path", str(project), "--export-release", preset, str(target)],
                project, timeout,
            )
            _verify_report_parent(parent, output_dfd)
            entry: Dict[str, Any] = {"output": str(target), "returncode": code, "timed_out": timed_out}
            if "No export template found" in log:
                entry.update(ok=False, reason="templates-missing")
            else:
                entry["ok"] = code == 0 and _regular_output(target) and not timed_out
                if not entry["ok"]:
                    entry["reason"] = "export-failed"
            # A huge output directory must not be fully enumerated and sorted.
            artefacts: list[Path] = []
            too_many = False
            with os.scandir(parent) as entries:
                for item in entries:
                    if len(artefacts) == MAX_OUTPUT_FILES:
                        too_many = True
                        break
                    artefacts.append(Path(item.path))
            artefacts.sort()
            if too_many or any(not _regular_output(item) for item in artefacts):
                entry["ok"], entry["reason"] = False, "unsafe-or-unbounded-artifacts"
                artefacts = []
            entry["artefacts"] = [str(item.relative_to(out)) for item in artefacts]
            # Preserve the exact listed inode and metadata for each artifact.
            # A later hash of a substituted same-name file is NOT evidence
            # that the exporter produced the original discovered inventory.
            listed = {item: item.lstat() for item in artefacts}
            entry["bytes"] = sum(info.st_size for info in listed.values())
            entry["sha256"] = {}
            # A per-artifact bound alone could admit 64 × 2 GiB across multiple
            # presets. Count the whole invocation before hashing expensive output
            # or running an exported executable. Reject rather than truncating the
            # inventory or permitting an unqualified partial pass.
            if entry["bytes"] > MAX_EXPORT_TOTAL_BYTES - cumulative_output_bytes:
                entry["ok"] = False
                entry["reason"] = "cumulative-output-byte-budget-exceeded"
                report["presets"][preset] = entry
                return {
                    **report,
                    "status": "failed",
                    "reason": "output-byte-budget",
                    "passed": False,
                    "out_dir": str(out),
                }
            cumulative_output_bytes += entry["bytes"]
            if entry["ok"]:
                try:
                    receipts: dict[str, str] = {}
                    verified_bytes = 0
                    fields = (
                        "st_dev", "st_ino", "st_mode", "st_nlink",
                        "st_size", "st_mtime_ns", "st_ctime_ns",
                    )
                    for item in artefacts:
                        digest = _artifact_digest(item)
                        _verify_report_parent(parent, output_dfd)
                        after_hash = item.lstat()
                        if any(
                            getattr(listed[item], field) != getattr(after_hash, field)
                            for field in fields
                        ):
                            raise ValueError("artifact identity changed after inventory")
                        verified_bytes += after_hash.st_size
                        if verified_bytes > MAX_EXPORT_TOTAL_BYTES - (
                            cumulative_output_bytes - entry["bytes"]
                        ):
                            raise ValueError("artifact byte budget exceeded during hashing")
                        receipts[str(item.relative_to(out))] = digest
                    if verified_bytes != entry["bytes"]:
                        raise ValueError("artifact byte inventory changed during hashing")
                    if preset == "Linux" and not _regular_output(target.with_suffix(".pck")):
                        raise ValueError("missing Linux game resource pack")
                    if preset == "Web" and not _regular_output(target.with_suffix(".wasm")):
                        raise ValueError("missing Web engine WASM payload")
                    entry["sha256"] = receipts
                except (OSError, ValueError):
                    entry["ok"], entry["reason"] = False, "artifact-custody-failed"
            _verify_report_parent(parent, output_dfd)
            entry["log_tail"] = log[-1500:]
            if entry["ok"] and preset == "Linux":
                entry["boot"] = _boot_exported(target, boot_frames, timeout)
                entry["ok"] = entry["boot"]["passed"]
                if not entry["ok"]:
                    entry["reason"] = "boot-failed"
            _verify_report_parent(parent, output_dfd)
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
        _write_report_new(Path(args.report), text)
    summary = {k: result.get(k) for k in ("era", "status", "binary_source", "verified")}
    summary["presets"] = {k: {"ok": v.get("ok"), "reason": v.get("reason"), "bytes": v.get("bytes")}
                          for k, v in result.get("presets", {}).items()}
    print(json.dumps(summary, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["PRESET_OUTPUTS", "export_build", "main"]
