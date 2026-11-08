"""Command line: ``python -m skeleton.godot_export certify <project>...``."""
from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path

from . import binary, cases, provenance
from .certify import Options, certify_many
from .artifact_custody import ExportCustodyError, export_and_inspect
from .runner import GodotRunner


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="skeleton.godot_export", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("certify", help="certify one or more Godot projects")
    c.add_argument("projects", nargs="+", type=Path)
    c.add_argument("--godot", default=None, help="Godot binary; omit for static-only certification")
    c.add_argument("--pin-version", default=binary.DEFAULT_PIN_VERSION)
    c.add_argument("--pin-sha256", default=None)
    c.add_argument("--export", action="store_true", help="run --export-release for each Linux-exportable preset")
    c.add_argument("--preset", action="append", default=None)
    c.add_argument("--out-dir", type=Path, default=None)
    c.add_argument("--ticks", default="30,60", help="allowed physics ticks per second")
    c.add_argument("--timeout", type=int, default=180)
    c.add_argument("--format", choices=("json", "markdown"), default="json")
    sub.add_parser("cases", help="list certification cases")
    pb = sub.add_parser("provenance", help="write a provenance manifest for exported artifacts")
    pb.add_argument("project", type=Path)
    pb.add_argument("--artifact", action="append", default=[], metavar="PRESET=PATH")
    pb.add_argument("--engine", default=binary.DEFAULT_PIN_VERSION)
    pb.add_argument("--verdict", choices=("SHIP", "NO-SHIP"), required=True)
    pb.add_argument("--base", type=Path, default=None)
    pb.add_argument("--out", type=Path, default=None)
    pv = sub.add_parser("verify", help="re-hash artifacts against a provenance manifest")
    pv.add_argument("manifest", type=Path)
    pv.add_argument("--base", type=Path, required=True)
    pv.add_argument("--project", type=Path, default=None)
    e = sub.add_parser("custody-export",
                       help="pin Godot and atomically publish a source-inspected desktop export")
    e.add_argument("--project", type=Path, required=True)
    e.add_argument("--preset", required=True)
    e.add_argument("--output", type=Path, required=True)
    e.add_argument("--platform", required=True, choices=("windows", "linux"))
    e.add_argument("--engine-bin", type=Path, required=True,
                   help="absolute path to a trusted Godot executable")
    e.add_argument("--engine-sha256", required=True,
                   help="required SHA-256 of the exact trusted Godot executable")
    e.add_argument("--engine-version", default=binary.DEFAULT_PIN_VERSION)
    e.add_argument("--timeout", type=int, default=600)
    return ap


def _provenance(a: argparse.Namespace) -> int:
    arts: dict[str, Path] = {}
    for spec in a.artifact:
        preset, sep, path = spec.partition("=")
        if not sep or not preset or not path:
            print(json.dumps({"error": f"bad --artifact {spec!r}, want PRESET=PATH"}))
            return 2
        arts[preset] = Path(path)
    m = provenance.build(a.project, a.engine, a.verdict, arts, a.base)
    text = m.dumps()
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


def _verify(a: argparse.Namespace) -> int:
    m = provenance.Manifest.loads(a.manifest.read_text(encoding="utf-8"))
    problems = provenance.verify(m, a.base, a.project)
    print(json.dumps({"ok": not problems, "problems": problems}))
    return 0 if not problems else 1



def _custody_export(a: argparse.Namespace) -> int:
    """An operator-facing source receipt, never a launch or release verdict."""
    def held(reason: str) -> int:
        print(json.dumps({
            "schema": "skeleton.godot_export.custody_cli.v1",
            "status": "held", "reason": reason,
            "launch_tested": False, "device_qualified": False,
            "release_certified": False,
        }, sort_keys=True))
        return 2

    pin = a.engine_sha256
    if (type(pin) is not str or len(pin) != 64 or
            any(c not in "0123456789abcdef" for c in pin)):
        return held("engine-pin-invalid")
    executable = a.engine_bin
    if not executable.is_absolute():
        return held("engine-binary-must-be-absolute")
    try:
        before = executable.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                not 0 < before.st_size <= (1 << 30)):
            return held("engine-binary-invalid")
        found = binary.sha256_file(executable)
        after = executable.lstat()
        if (found != pin or
                (before.st_dev, before.st_ino, before.st_size,
                 before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_size,
                 after.st_mtime_ns, after.st_ctime_ns)):
            return held("engine-binary-pin-or-identity-mismatch")
        runner = GodotRunner(str(executable))
        result = binary.check_version(
            runner, binary.Pin(version=a.engine_version, sha256=pin), a.project,
        )
        if not result.passed:
            return held("engine-version-mismatch")
        evidence = export_and_inspect(
            runner, a.project, a.preset, a.output, a.platform,
            timeout=a.timeout,
        )
    except (OSError, ValueError, ExportCustodyError):
        return held("source-or-artifact-custody-rejected")
    print(json.dumps({
        "schema": "skeleton.godot_export.custody_cli.v1",
        "status": "source-artifact-inspected",
        "artifact": {
            "path": evidence.path, "platform": evidence.platform,
            "size": evidence.size, "sha256": evidence.sha256,
            "godot_exit_code": evidence.godot_exit_code,
        },
        "godot_executable_sha256": pin,
        "launch_tested": False, "device_qualified": False,
        "release_certified": False,
    }, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.cmd == "custody-export":
        return _custody_export(a)
    if a.cmd == "cases":
        for c in cases.CASES.values():
            print(f"{c.id}\tSev{int(c.severity)}\t{c.title}\t{','.join(c.todo)}")
        return 0
    if a.cmd == "provenance":
        return _provenance(a)
    if a.cmd == "verify":
        return _verify(a)
    opts = Options(godot=binary.locate(a.godot) if a.godot else None,
                   pin=binary.Pin(a.pin_version, a.pin_sha256), export=a.export, presets=a.preset,
                   out_dir=a.out_dir, ticks=tuple(int(t) for t in a.ticks.split(",") if t), timeout=a.timeout)
    if a.godot and opts.godot is None:
        print(json.dumps({"case": "GFB-01", "sev": 1, "fail": f"godot binary not found: {a.godot}"}))
        return 1
    reports = certify_many(a.projects, opts)
    if a.format == "json":
        print(json.dumps([r.to_dict() for r in reports], indent=1, default=str))
    else:
        print("\n".join(r.to_markdown() for r in reports))
    return 0 if all(r.ship for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
