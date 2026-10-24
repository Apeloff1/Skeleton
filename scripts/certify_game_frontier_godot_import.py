#!/usr/bin/env python3
"""GF-D certification: real Godot 4 headless import + GDScript parse smoke.

Shirt 1 (QA). Covers TODO items GF-P0-38 (headless parse + emitted scene
import), and the import halves of GF-P0-74 (RigidBody3D) and GF-P0-96
(SoftBody3D). Runs against the actual pinned Godot binary; never mocked.

Sev map (any red Sev1/Sev2 = NO-SHIP):
  GFD-01 Sev1  `--import` exits 0 within budget
  GFD-02 Sev1  no engine ERROR / SCRIPT ERROR / Parse Error lines during import
  GFD-03 Sev2  import produced the .godot/ cache (project actually imported)
  GFD-04 Sev1  every emitted .gd parses (`--check-only`) with no parse error
  GFD-05 Sev2  every emitted .tscn/.scn is referenced-resource clean
               (no "Failed loading resource" / "Cannot open file")
  GFD-06 Sev3  report counts are non-zero (scripts and scenes were emitted)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FATAL = re.compile(r"^(?:\s*)(ERROR:|SCRIPT ERROR:|Parse Error)", re.M)
MISSING = re.compile(r"(Failed loading resource|Cannot open file|Resource file not found)")


def run(godot: str, args: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    r = subprocess.run([godot, "--headless", *args], cwd=cwd, capture_output=True,
                       text=True, timeout=timeout, check=False)
    return r.returncode, r.stdout + "\n" + r.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--godot", required=True)
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()
    proj = a.project.resolve()
    if not (proj / "project.godot").is_file():
        print(json.dumps({"case": "GFD-00", "sev": 1, "fail": "no project.godot", "project": str(proj)}))
        return 1
    fails: list[dict] = []

    code, out = run(a.godot, ["--path", str(proj), "--import"], proj, a.timeout)
    if code != 0:
        fails.append({"case": "GFD-01", "sev": 1, "expected": "exit 0", "actual": code, "tail": out[-3000:]})
    fatal = FATAL.findall(out)
    if fatal:
        fails.append({"case": "GFD-02", "sev": 1, "expected": "no engine errors",
                      "actual": [l for l in out.splitlines() if FATAL.match(l)][:20]})
    if not (proj / ".godot").is_dir():
        fails.append({"case": "GFD-03", "sev": 2, "expected": ".godot/ cache present", "actual": "missing"})
    missing = [l for l in out.splitlines() if MISSING.search(l)]
    if missing:
        fails.append({"case": "GFD-05", "sev": 2, "expected": "all resources resolve", "actual": missing[:20]})

    scripts = sorted(p for p in proj.rglob("*.gd") if ".godot" not in p.parts)
    scenes = sorted(p for p in proj.rglob("*.tscn") if ".godot" not in p.parts) + \
        sorted(p for p in proj.rglob("*.scn") if ".godot" not in p.parts)
    parse_bad = []
    for s in scripts:
        res = "res://" + s.relative_to(proj).as_posix()
        c, o = run(a.godot, ["--path", str(proj), "--check-only", "--script", res], proj, 60)
        if c != 0 or "Parse Error" in o or "SCRIPT ERROR" in o:
            parse_bad.append({"script": res, "exit": c, "tail": o[-800:]})
    if parse_bad:
        fails.append({"case": "GFD-04", "sev": 1, "expected": "all scripts parse", "actual": parse_bad[:10]})
    if not scripts or not scenes:
        fails.append({"case": "GFD-06", "sev": 3, "expected": "scripts and scenes emitted",
                      "actual": {"scripts": len(scripts), "scenes": len(scenes)}})

    print(json.dumps({"project": str(proj), "scripts": len(scripts), "scenes": len(scenes),
                      "fails": fails, "pass": not fails}, indent=1))
    return 0 if not any(f["sev"] <= 2 for f in fails) else 1


if __name__ == "__main__":
    sys.exit(main())
