"""GF-D headless import certification (GFD-00..06) using a GodotRunner."""
from __future__ import annotations

from pathlib import Path

from . import configfile, logscan, references
from .project import GodotProject, path_to_res
from .report import CertificationReport
from .runner import GodotRunner


def static_only(root: Path) -> CertificationReport:
    """Engine-free subset: GFD-00, GFD-05 (static), GFD-06."""
    rep = CertificationReport(str(root))
    if not (root / "project.godot").is_file():
        rep.add("GFD-00", False, "no project.godot")
        return rep
    try:
        project = GodotProject.load(root)
    except configfile.ConfigParseError as exc:
        rep.add("GFD-00", False, str(exc))
        return rep
    rep.add("GFD-00", True)
    dangling = references.all_problems(project)
    rep.add("GFD-05", not dangling, [d.__dict__ for d in dangling[:20]] or None)
    s, c = len(project.scripts()), len(project.scenes())
    rep.add("GFD-06", bool(s and c), {"scripts": s, "scenes": c})
    return rep


def certify(root: Path, runner: GodotRunner, timeout: int = 180) -> CertificationReport:
    rep = static_only(root)
    if not rep.results[0].passed:
        return rep
    project = GodotProject.load(root)
    res = runner.import_project(root, timeout)
    rep.add("GFD-01", res.ok, None if res.ok else {"exit": res.code, "tail": res.output[-3000:]})
    scan = logscan.scan(res.output)
    rep.add("GFD-02", not scan.fatal, scan.fatal[:20] or None)
    rep.add("GFD-03", (root / ".godot").is_dir(), None)
    if scan.missing:
        rep.add("GFD-05", False, {"engine": scan.missing[:20]})
    bad = []
    for script in project.scripts():
        r = runner.check_script(root, path_to_res(root, script))
        s = logscan.scan(r.output)
        if not r.ok or s.fatal:
            bad.append({"script": path_to_res(root, script), "exit": r.code, "tail": r.output[-800:]})
    rep.add("GFD-04", not bad, bad[:10] or None)
    return rep
