"""Export certification (GFX-01..09)."""
from __future__ import annotations

import os
from pathlib import Path

from . import configfile, pck, presets as presets_mod
from .provenance import _relative, _digest_beneath
from .platforms import registry
from .report import CertificationReport
from .runner import GodotRunner


def static_presets(root: Path) -> tuple[CertificationReport, list[presets_mod.ExportPreset]]:
    rep = CertificationReport(f"{root}:presets")
    try:
        presets = presets_mod.load(root)
    except FileNotFoundError:
        rep.add("GFX-01", False, "export_presets.cfg missing")
        return rep, []
    except (configfile.ConfigParseError, presets_mod.PresetError) as exc:
        rep.add("GFX-01", False, str(exc))
        return rep, []
    rep.add("GFX-01", bool(presets), {"presets": [p.name for p in presets]})
    for p in presets:
        known = registry.known(p.platform)
        rep.add("GFX-02", known, p.platform, p.name)
        rep.add("GFX-03", p.export_path_is_relative, p.export_path, p.name)
        if known:
            problems = registry.get(p.platform).check_preset(p)
            rep.add("GFX-04", not problems, problems or None, p.name)
        secrets = presets_mod.secret_values(p)
        rep.add("GFX-09", not secrets, secrets or None, p.name)
    dups = presets_mod.duplicate_names(presets)
    rep.add("GFX-08", not dups, dups or None)
    return rep, presets


def check_pck(path: Path, subject: str) -> tuple[bool, object]:
    try:
        h = pck.read(path)
    except (pck.PckError, OSError) as exc:
        return False, str(exc)
    return h.file_count > 0, {"format": h.format_version, "engine": h.engine, "files": h.file_count}


def _export_target(root: Path, relative: str) -> Path:
    """Prepare a no-clobber output under descriptor-anchored parent directories.

    The output directory must be trusted and free of concurrent untrusted
    writers; this is a source-level guard, not a sandbox or release signature.
    """
    parts = _relative(relative)
    if os.name != "posix" or not all(hasattr(os, n) for n in ("O_NOFOLLOW", "O_DIRECTORY")):
        raise ValueError("safe Godot output inspection unavailable on this host")
    absolute = Path(os.path.abspath(root))
    if ".." in absolute.parts:
        raise ValueError("unsafe export root")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        # Never create directories through symlinked pre-existing ancestors.
        for component in absolute.parts[1:] + parts[:-1]:
            try:
                child = os.open(component, flags, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(component, mode=0o700, dir_fd=fd)
                child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        try:
            os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("Godot export output already exists")
    finally:
        os.close(fd)
    return absolute.joinpath(*parts)


def certify(root: Path, runner: GodotRunner, out_dir: Path | None = None, only: list[str] | None = None,
            timeout: int = 600) -> CertificationReport:
    rep, presets = static_presets(root)
    if rep.blocking:
        return rep
    out_dir = out_dir or root
    for p in presets:
        if only and p.name not in only:
            continue
        spec = registry.get(p.platform)
        if not spec.export_on_linux:
            continue
        try:
            target = _export_target(out_dir, p.export_path)
        except (ValueError, OSError) as exc:
            rep.add("GFX-05", False, {"reason": "unsafe-export-target", "error": type(exc).__name__}, p.name)
            continue
        res = runner.export(root, p.name, str(target), "release", timeout)
        rep.add("GFX-05", res.ok, None if res.ok else {"exit": res.code, "tail": res.output[-1500:]}, p.name)
        if not res.ok:
            continue
        try:
            # Reject swapped output symlinks, special files, hardlinks,
            # oversized output, and in-place mutations before parsing data.
            _digest_beneath(Path(os.path.abspath(out_dir)), p.export_path)
            problems = spec.check_artifact(target)
        except (ValueError, OSError) as exc:
            problems = ["unsafe or unreadable export: " + type(exc).__name__]
        rep.add("GFX-06", not problems, problems or str(target), p.name)
        if problems:
            continue
        side = target.with_suffix(".pck")
        pck_path = side if side.is_file() else target
        if pck_path.is_file() and spec.name in ("Linux", "Windows Desktop", "Web"):
            try:
                rel = pck_path.relative_to(Path(os.path.abspath(out_dir))).as_posix()
                _digest_beneath(Path(os.path.abspath(out_dir)), rel)
                ok, detail = check_pck(pck_path, p.name)
            except (ValueError, OSError):
                ok, detail = False, "unsafe or unreadable export sidecar"
            rep.add("GFX-07", ok, detail, p.name)
    return rep
