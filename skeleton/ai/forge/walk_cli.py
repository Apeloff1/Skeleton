"""Forge walk CLI — strict args, era matrix, and a prerequisite doctor.

Backs ``python -m skeleton walk`` / ``eras`` / ``doctor``. Kept out of
``skeleton/__main__.py`` so it can be tested without the process entry point.

Exit codes are part of the contract:

* ``0`` every walk passed (or doctor found no failing check)
* ``1`` a walk failed (no extract, collapse, or teleport) / doctor check failed
* ``2`` bad usage (unknown flag, missing value, unknown era, bad number)

The walker itself is unchanged; this layer only selects inputs and reports.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

WALK_MODES = ("ideal", "thermal")
DEFAULT_ERA = "extraction_now"

Printer = Callable[[str], None]


class UsageError(ValueError):
    """Bad CLI input; maps to exit code 2."""


@dataclass
class WalkArgs:
    era: str = DEFAULT_ERA
    blend: Optional[Tuple[str, str]] = None
    t: float = 0.5
    as_json: bool = False
    mode: str = "ideal"
    seed: Optional[str] = None
    all_eras: bool = False
    steps: bool = False


def _value(rest: Sequence[str], i: int, flag: str) -> str:
    if i + 1 >= len(rest) or rest[i + 1].startswith("--"):
        raise UsageError(f"{flag} needs a value")
    return rest[i + 1]


def parse_walk_args(rest: Sequence[str]) -> WalkArgs:
    """Parse ``walk`` flags. Unknown flags are refused rather than ignored."""
    args = WalkArgs()
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--era":
            args.era = _value(rest, i, a); i += 2
        elif a == "--blend":
            if i + 2 >= len(rest) or rest[i + 1].startswith("--") or rest[i + 2].startswith("--"):
                raise UsageError("--blend needs two eras")
            args.blend = (rest[i + 1], rest[i + 2]); i += 3
        elif a == "--t":
            raw = _value(rest, i, a)
            try:
                args.t = float(raw)
            except ValueError:
                raise UsageError(f"--t must be a number, got {raw!r}") from None
            if not 0.0 <= args.t <= 1.0:
                raise UsageError("--t must be between 0 and 1")
            i += 2
        elif a == "--mode":
            args.mode = _value(rest, i, a)
            if args.mode not in WALK_MODES:
                raise UsageError(f"--mode must be one of {', '.join(WALK_MODES)}")
            i += 2
        elif a == "--seed":
            args.seed = _value(rest, i, a); i += 2
        elif a == "--json":
            args.as_json = True; i += 1
        elif a == "--all-eras":
            args.all_eras = True; i += 1
        elif a == "--steps":
            args.steps = True; i += 1
        else:
            raise UsageError(f"unknown walk option: {a}")
    if args.all_eras and args.blend:
        raise UsageError("--all-eras and --blend are mutually exclusive")
    _check_eras([args.era] + (list(args.blend) if args.blend else []))
    return args


def _check_eras(names: Sequence[str]) -> None:
    from skeleton.forge.eras import list_eras

    known = set(list_eras())
    for name in names:
        if name not in known:
            raise UsageError(f"unknown era: {name}")


def walk_once(
    era: str,
    *,
    blend: Optional[Tuple[str, str]] = None,
    t: float = 0.5,
    mode: str = "ideal",
    seed: Optional[str] = None,
) -> Dict[str, Any]:
    """Compile → plan → walk one era (or blend). Returns the report payload."""
    from skeleton.context.dodeca import Dodecahedron
    from skeleton.context.oracle import Magic8Ball
    from skeleton.context.tensor import ContextTensor
    from skeleton.forge.eras import blend_eras, compile_era
    from skeleton.forge.walk import walk_from_pack
    from skeleton.jeeves.builder import BuilderBrain

    if blend:
        pack = blend_eras(blend[0], blend[1], t)
        tensor = ContextTensor.from_era(blend[0]).lerp(ContextTensor.from_era(blend[1]), t)
        label = f"{blend[0]}+{blend[1]}@{t:g}"
    else:
        pack = compile_era(era)
        tensor = ContextTensor.from_era(era)
        label = era
    reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
    plan = BuilderBrain().plan(pack, tensor=tensor, reading=reading)
    plan_dict = plan.to_dict()
    if seed is not None:
        plan_dict["seed"] = seed
    report = walk_from_pack(pack, plan=plan_dict, mode=mode)
    payload = report.to_dict()
    payload["label"] = label
    payload["plan"] = {"bias": plan.room_bias, "extract_late": plan.extract_late, "era": plan.era}
    if seed is not None:
        payload["seed"] = seed
    payload["_steps_full"] = [s.to_dict() for s in report.steps]
    return payload


def _summary_line(p: Dict[str, Any]) -> str:
    verdict = "PASS" if p["passed"] else "FAIL"
    line = (
        f"{verdict} {p['label']:24} extracted={p['extracted']} t={p['t']:.2f} "
        f"hops={p['hops']} cores={p['cores']}/{p['required_cores']}"
    )
    if p["mode"] == "thermal":
        line += f" heat_peak={p['heat_peak']:.2f} vents={p['vents']}"
    if not p["passed"] and p.get("notes"):
        line += f" reason={p['notes'][-1]}"
    return line


def _public(p: Dict[str, Any], *, full_steps: bool) -> Dict[str, Any]:
    out = {k: v for k, v in p.items() if k != "_steps_full"}
    if full_steps:
        out["steps"] = p["_steps_full"]
    return out


def run_walk(rest: Sequence[str], out: Printer = print) -> int:
    """``walk`` entry: single era/blend, or ``--all-eras`` matrix."""
    try:
        args = parse_walk_args(rest)
    except UsageError as exc:
        out(f"walk: {exc}")
        return EXIT_USAGE

    if args.all_eras:
        from skeleton.forge.eras import list_eras

        results = [walk_once(e, mode=args.mode, seed=args.seed) for e in list_eras()]
        failed = [r["label"] for r in results if not r["passed"]]
        if args.as_json:
            out(json.dumps({
                "mode": args.mode,
                "total": len(results),
                "passed": len(results) - len(failed),
                "failed": failed,
                "walks": [_public(r, full_steps=args.steps) for r in results],
            }, indent=2, default=str))
        else:
            for r in results:
                out(_summary_line(r))
            out(f"{len(results) - len(failed)}/{len(results)} eras passed ({args.mode})")
        return EXIT_FAIL if failed else EXIT_OK

    p = walk_once(args.era, blend=args.blend, t=args.t, mode=args.mode, seed=args.seed)
    if args.as_json:
        out(json.dumps(_public(p, full_steps=args.steps), indent=2, default=str))
    else:
        # First line keeps the historical format CI greps for.
        out(f"extracted={p['extracted']} t={p['t']:.2f} hops={p['hops']} cores={p['cores']}/{p['required_cores']}")
        if args.steps:
            for s in p["_steps_full"]:
                out(f"  t={s['t']:>8.3f} {s['room']:12} {s['action']:10} {s['detail']}")
        if not p["passed"]:
            for note in p.get("notes", []):
                out(f"  note: {note}")
    return EXIT_OK if p["passed"] else EXIT_FAIL


def run_eras(rest: Sequence[str], out: Printer = print) -> int:
    """``eras`` entry: human table (historical) or ``--json``."""
    from skeleton.forge.eras import compile_era, list_eras

    flags = list(rest)
    unknown = [f for f in flags if f != "--json"]
    if unknown:
        out(f"eras: unknown option: {unknown[0]}")
        return EXIT_USAGE
    rows = []
    for era in list_eras():
        pack = compile_era(era)
        rows.append({
            "era": era,
            "primary_dps": pack["primary_dps"],
            "speed": pack["player"]["speed"],
            "collapse_max": (pack.get("session") or {}).get("collapse_max"),
        })
    if "--json" in flags:
        out(json.dumps(rows, indent=2, default=str))
    else:
        for r in rows:
            out(f"{r['era']:22} dps={r['primary_dps']:<7} speed={r['speed']}")
    return EXIT_OK


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "required": self.required, "detail": self.detail}


@dataclass
class DoctorReport:
    checks: List[DoctorCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.required)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "checks": [c.to_dict() for c in self.checks]}


def _godot_binary(env: Dict[str, str]) -> Optional[str]:
    explicit = env.get("GODOT_BIN") or env.get("GODOT")
    if explicit:
        return explicit if os.path.isfile(explicit) and os.access(explicit, os.X_OK) else None
    for name in ("godot4", "godot"):
        found = shutil.which(name, path=env.get("PATH"))
        if found:
            return found
    return None


def run_doctor_checks(
    *,
    out_dir: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    walk_era: str = DEFAULT_ERA,
) -> DoctorReport:
    """Probe what a forge run needs. Godot is optional (headless playtest only)."""
    env = dict(os.environ if env is None else env)
    report = DoctorReport()

    try:
        from skeleton.forge.eras import compile_era, list_eras

        eras = list_eras()
        bad = []
        for e in eras:
            try:
                compile_era(e)
            except Exception as exc:  # report, don't crash the doctor
                bad.append(f"{e}: {exc}")
        report.checks.append(DoctorCheck(
            "eras_compile", not bad,
            f"{len(eras)} eras compile" if not bad else "; ".join(bad[:3]),
        ))
    except Exception as exc:
        report.checks.append(DoctorCheck("eras_compile", False, f"import failed: {exc}"))

    try:
        p = walk_once(walk_era)
        report.checks.append(DoctorCheck(
            "walk_smoke", bool(p["passed"]),
            f"{walk_era} extracted in {p['t']:.2f}s" if p["passed"] else f"{walk_era}: {(p.get('notes') or ['failed'])[-1]}",
        ))
    except Exception as exc:
        report.checks.append(DoctorCheck("walk_smoke", False, f"{walk_era}: {exc}"))

    target = out_dir or tempfile.gettempdir()
    try:
        os.makedirs(target, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target, prefix=".skeleton-doctor-", delete=True):
            pass
        report.checks.append(DoctorCheck("output_writable", True, target))
    except OSError as exc:
        report.checks.append(DoctorCheck("output_writable", False, f"{target}: {exc}"))

    godot = _godot_binary(env)
    report.checks.append(DoctorCheck(
        "godot_binary", godot is not None,
        godot or "not found (set GODOT_BIN); headless playtest gate will be skipped",
        required=False,
    ))
    return report


def run_doctor(rest: Sequence[str], out: Printer = print) -> int:
    """``doctor`` entry: ``[--out DIR] [--json]``."""
    out_dir: Optional[str] = None
    as_json = False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--json":
            as_json = True; i += 1
        elif a == "--out":
            try:
                out_dir = _value(rest, i, a)
            except UsageError as exc:
                out(f"doctor: {exc}")
                return EXIT_USAGE
            i += 2
        else:
            out(f"doctor: unknown option: {a}")
            return EXIT_USAGE
    report = run_doctor_checks(out_dir=out_dir)
    if as_json:
        out(json.dumps(report.to_dict(), indent=2))
    else:
        for c in report.checks:
            mark = "ok  " if c.ok else ("FAIL" if c.required else "warn")
            out(f"[{mark}] {c.name:16} {c.detail}")
        out("doctor: ok" if report.ok else "doctor: failing checks")
    return EXIT_OK if report.ok else EXIT_FAIL
