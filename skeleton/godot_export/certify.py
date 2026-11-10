"""Top-level orchestration: static + optional engine-backed certification."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import binary, export_cert, import_cert, lint_cert, project_checks, scene_checks
from .project import GodotProject
from .report import CertificationReport
from .runner import GodotRunner


@dataclass
class Options:
    godot: str | None = None
    pin: binary.Pin = binary.Pin()
    export: bool = False
    presets: list[str] | None = None
    out_dir: Path | None = None
    ticks: tuple[int, ...] = project_checks.GF_SMOKE_TICKS
    timeout: int = 180


def certify(root: Path, opts: Options, runner: GodotRunner | None = None) -> CertificationReport:
    root = root.resolve()
    if runner is None and opts.godot:
        runner = GodotRunner(opts.godot)
    rep = CertificationReport(str(root), meta={"engine": bool(runner), "export": opts.export})
    if runner is not None:
        version_result = binary.check_version(runner, opts.pin, root)
        rep.extend([version_result])
        # Never execute untrusted project import/export against a mismatched engine.
        if not version_result.passed:
            return rep
        if opts.pin.sha256 is not None:
            # A hash pin must be checked against a real explicit executable, not
            # silently skipped for a PATH alias or a missing binary.
            if not opts.godot or not Path(opts.godot).is_file():
                rep.extend([binary.CaseResult("GFB-02", False, "pinned engine executable unavailable")])
                return rep
            hash_result = binary.check_sha(Path(opts.godot), opts.pin)
            rep.extend([hash_result])
            if not hash_result.passed:
                return rep
        imp = import_cert.certify(root, runner, opts.timeout)
    else:
        imp = import_cert.static_only(root)
    rep.extend(imp.results)
    if not imp.results or not imp.results[0].passed:
        return rep
    project = GodotProject.load(root)
    rep.extend(project_checks.run_all(project, opts.ticks))
    rep.extend(scene_checks.run_all(project))
    rep.extend(lint_cert.certify(project).results)
    if (root / "export_presets.cfg").is_file() or opts.export:
        if opts.export and runner is not None:
            exp = export_cert.certify(root, runner, opts.out_dir, opts.presets)
        else:
            exp, _ = export_cert.static_presets(root)
        rep.extend(exp.results)
    return rep


def certify_many(roots: list[Path], opts: Options, runner: GodotRunner | None = None) -> list[CertificationReport]:
    return [certify(r, opts, runner) for r in roots]
