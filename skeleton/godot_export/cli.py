"""Command line: ``python -m skeleton.godot_export certify <project>...``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import binary, cases, provenance
from .certify import Options, certify_many


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
    return ap


def _provenance(a: argparse.Namespace) -> int:
    arts: dict[str, Path] = {}
    for spec in a.artifact:
        preset, sep, path = spec.partition("=")
        if not sep or not preset or not path:
            print(json.dumps({"error": "invalid --artifact; expected PRESET=PATH"}))
            return 2
        # A duplicate key previously overwrote the earlier artifact before
        # admission, concealing an ambiguous release receipt.
        if preset in arts:
            print(json.dumps({"error": "duplicate --artifact preset"}))
            return 2
        arts[preset] = Path(path)
    if a.verdict == "SHIP" and not arts:
        print(json.dumps({"error": "SHIP provenance requires real artifacts"}))
        return 2
    try:
        m = provenance.build(a.project, a.engine, a.verdict, arts, a.base)
        text = m.dumps()
    except (ValueError, OSError, UnicodeError, RecursionError):
        # Invalid source paths, credentials or malformed contents must not
        # be reflected into publicly visible workflow logs.
        print(json.dumps({"error": "unsafe or invalid provenance inputs"}))
        return 2
    if a.out:
        try:
            provenance.write_manifest_file_new(a.out, m)
        except (ValueError, OSError, UnicodeError, RecursionError):
            print(json.dumps({"error": "unsafe or occupied provenance manifest output"}))
            return 2
    else:
        sys.stdout.write(text)
    return 0


def _verify(a: argparse.Namespace) -> int:
    # A matching artifact hash alone does not prove which project produced it.
    # The CLI's "ok" result must bind artifact bytes AND the source tree.
    # Preserve a JSON error response (rather than argparse SystemExit) for
    # callers that previously omitted the optional --project argument.
    if a.project is None:
        problems = ["project source tree was not supplied for verification"]
        print(json.dumps({"ok": False, "problems": problems}))
        return 1
    try:
        manifest = provenance.read_manifest_file(a.manifest)
        problems = provenance.verify(manifest, a.base, a.project)
    except (ValueError, OSError, UnicodeError, RecursionError):
        # Do not leak attacker-controlled paths or malformed JSON contents
        # into public CI logs. A malformed receipt is never a successful one.
        problems = ["unsafe or malformed provenance manifest"]
    print(json.dumps({"ok": not problems, "problems": problems}))
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
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
