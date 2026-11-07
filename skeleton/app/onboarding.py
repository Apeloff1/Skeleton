"""First-run onboarding and ``doctor`` diagnostics for the Skeleton CLI.

This module turns the existing host preload, assembly preflight, runtime setup,
and live health probes into one friendly, human-readable readiness report.  It
is read-only unless the caller explicitly runs :func:`run_first_run_setup`, and
it never prints secret values: only key names and check outcomes.

Onboarding state (whether first-run setup has completed) lives outside the
repository in the per-user config directory so that clones stay clean:

* ``$SKELETON_HOME`` when set, otherwise
* ``$XDG_CONFIG_HOME/skeleton`` when set, otherwise
* ``~/.config/skeleton``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import json
import os
from pathlib import Path
import platform
import sys
import time
from typing import Callable, Iterable, Mapping, Sequence

ONBOARDING_SCHEMA_VERSION = 1
ONBOARDING_FILENAME = "onboarding.json"

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_SKIP = "skip"
_STATUS_ORDER = {STATUS_FAIL: 0, STATUS_WARN: 1, STATUS_OK: 2, STATUS_SKIP: 3}
_STATUS_ICON = {STATUS_OK: "✓", STATUS_WARN: "!", STATUS_FAIL: "✗", STATUS_SKIP: "-"}

# Friendly remediation hints keyed by check-code prefix.  The first matching
# prefix wins, so more specific prefixes must come first.
_FIX_HINTS: tuple[tuple[str, str], ...] = (
    ("host:python", "Install Python 3.11 or newer, then re-run `python -m skeleton setup`."),
    ("host:pip", "Install pip for this interpreter: `python -m ensurepip --upgrade`."),
    ("runtime:docker", "Install Docker Desktop (or docker engine) and make sure `docker` is on PATH."),
    ("env:", "Run `python -m skeleton setup` to generate missing local secrets in .env."),
    ("path:", "Your checkout looks incomplete. Re-clone the repo or run `git checkout -- .`."),
    ("service:", "A service folder is missing. Re-clone or run `git status` to see what was removed."),
    ("topology:", "The app manifest is invalid. Run `python -m skeleton app plan` for details."),
    ("probe:", "Start the app with `python -m skeleton app up`, then re-run `python -m skeleton doctor --live`."),
    ("onboarding:", "Run `python -m skeleton setup` to finish first-run setup."),
)


def fix_hint(code: str, fallback: str = "") -> str:
    """Return the friendly remediation hint for a check code."""

    for prefix, hint in _FIX_HINTS:
        if code.startswith(prefix):
            return hint
    return fallback


# ---------------------------------------------------------------------------
# Onboarding state
# ---------------------------------------------------------------------------


def config_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Resolve the per-user Skeleton config directory (never created here)."""

    env = os.environ if environ is None else environ
    explicit = (env.get("SKELETON_HOME") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    xdg = (env.get("XDG_CONFIG_HOME") or "").strip()
    if xdg:
        return Path(xdg).expanduser() / "skeleton"
    home = (env.get("HOME") or "").strip()
    base = Path(home).expanduser() if home else Path.home()
    return base / ".config" / "skeleton"


def onboarding_path(environ: Mapping[str, str] | None = None) -> Path:
    return config_dir(environ) / ONBOARDING_FILENAME


@dataclass(frozen=True)
class OnboardingState:
    completed: bool
    completed_at: float | None = None
    version: int = ONBOARDING_SCHEMA_VERSION
    repo_root: str | None = None
    corrupt: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "completed": self.completed,
            "completed_at": self.completed_at,
            "version": self.version,
            "repo_root": self.repo_root,
            "corrupt": self.corrupt,
        }


def load_onboarding_state(environ: Mapping[str, str] | None = None) -> OnboardingState:
    """Read onboarding state; a missing or unreadable file means not completed."""

    path = onboarding_path(environ)
    if not path.is_file():
        return OnboardingState(completed=False)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return OnboardingState(completed=False, corrupt=True)
    if not isinstance(payload, dict):
        return OnboardingState(completed=False, corrupt=True)
    completed_at = payload.get("completed_at")
    version = payload.get("version")
    return OnboardingState(
        completed=bool(payload.get("completed")),
        completed_at=float(completed_at) if isinstance(completed_at, (int, float)) else None,
        version=int(version) if isinstance(version, int) else ONBOARDING_SCHEMA_VERSION,
        repo_root=str(payload["repo_root"]) if isinstance(payload.get("repo_root"), str) else None,
    )


def mark_onboarding_complete(
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    clock: Callable[[], float] = time.time,
) -> OnboardingState:
    """Atomically persist completed onboarding state."""

    path = onboarding_path(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = OnboardingState(
        completed=True,
        completed_at=float(clock()),
        repo_root=str(repo_root) if repo_root is not None else None,
    )
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return state


def reset_onboarding(environ: Mapping[str, str] | None = None) -> bool:
    """Forget onboarding state so the next run is treated as first-run."""

    path = onboarding_path(environ)
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Doctor report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DoctorItem:
    code: str
    status: str
    title: str
    detail: str = ""
    fix: str = ""
    group: str = "general"

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "status": self.status,
            "title": self.title,
            "detail": self.detail,
            "fix": self.fix,
            "group": self.group,
        }


@dataclass(frozen=True)
class DoctorReport:
    items: tuple[DoctorItem, ...]
    first_run: bool
    python: str = field(default_factory=lambda: platform.python_version())
    platform: str = field(default_factory=lambda: sys.platform)

    @property
    def failures(self) -> tuple[DoctorItem, ...]:
        return tuple(item for item in self.items if item.status == STATUS_FAIL)

    @property
    def warnings(self) -> tuple[DoctorItem, ...]:
        return tuple(item for item in self.items if item.status == STATUS_WARN)

    @property
    def ready(self) -> bool:
        return not self.failures

    @property
    def headline(self) -> str:
        if self.failures:
            n = len(self.failures)
            return f"{n} problem{'s' if n != 1 else ''} need{'s' if n == 1 else ''} attention"
        if self.warnings:
            n = len(self.warnings)
            return f"Ready, with {n} warning{'s' if n != 1 else ''}"
        return "All checks passed"

    def next_steps(self) -> list[str]:
        steps: list[str] = []
        for item in sorted(self.items, key=lambda i: _STATUS_ORDER.get(i.status, 9)):
            if item.status not in (STATUS_FAIL, STATUS_WARN) or not item.fix or item.fix in steps:
                continue
            if item.code.startswith("onboarding:") and any("skeleton setup" in s for s in steps):
                continue  # an earlier step already sends the user to setup
            steps.append(item.fix)
        if not steps:
            if self.first_run:
                steps.append("Run `python -m skeleton setup` to finish first-run setup.")
            else:
                steps.append("Start the app with `python -m skeleton app up`.")
        return steps

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "skeleton.doctor",
            "schema_version": ONBOARDING_SCHEMA_VERSION,
            "ready": self.ready,
            "first_run": self.first_run,
            "headline": self.headline,
            "python": self.python,
            "platform": self.platform,
            "counts": {
                status: sum(1 for item in self.items if item.status == status)
                for status in (STATUS_OK, STATUS_WARN, STATUS_FAIL, STATUS_SKIP)
            },
            "items": [item.to_dict() for item in self.items],
            "next_steps": self.next_steps(),
        }


def _item_from_check(code: str, ok: bool, required: bool, detail: str, remediation: str, group: str) -> DoctorItem:
    status = STATUS_OK if ok else (STATUS_FAIL if required else STATUS_WARN)
    text = (detail or code).strip()
    title = text[:1].upper() + text[1:]
    fix = "" if ok else (remediation or fix_hint(code))
    return DoctorItem(code=code, status=status, title=title, fix=fix, group=group)


def items_from_preload(report: object) -> list[DoctorItem]:
    items: list[DoctorItem] = []
    for check in getattr(report, "checks", ()) or ():
        items.append(
            _item_from_check(
                str(check.code), bool(check.ok), bool(getattr(check, "required", True)),
                str(check.detail), str(getattr(check, "remediation", "") or ""), "host",
            )
        )
    return items


def items_from_preflight(checks: Iterable[object]) -> list[DoctorItem]:
    items: list[DoctorItem] = []
    for check in checks:
        code = str(check.code)
        group = "config" if code.startswith(("env:", "runtime:")) else "repo"
        items.append(
            _item_from_check(
                code, bool(check.ok), bool(getattr(check, "required", True)),
                str(check.message), "", group,
            )
        )
    return items


def items_from_probes(results: Iterable[object]) -> list[DoctorItem]:
    items: list[DoctorItem] = []
    for result in results:
        ok = bool(result.ok)
        status_code = getattr(result, "status", None)
        detail = f"{result.url} -> {status_code if status_code is not None else 'no response'}"
        if getattr(result, "detail", ""):
            detail += f" ({result.detail})"
        items.append(
            DoctorItem(
                code=f"probe:{result.service}",
                status=STATUS_OK if ok else STATUS_FAIL,
                title=f"{result.service} reachable" if ok else f"{result.service} not reachable",
                detail=detail,
                fix="" if ok else fix_hint("probe:"),
                group="live",
            )
        )
    return items


def onboarding_item(state: OnboardingState) -> DoctorItem:
    if state.completed:
        return DoctorItem(
            code="onboarding:state", status=STATUS_OK,
            title="First-run setup complete", group="onboarding",
        )
    detail = "onboarding state file is unreadable" if state.corrupt else "first-run setup has not been run yet"
    return DoctorItem(
        code="onboarding:state", status=STATUS_WARN, title="First-run setup pending",
        detail=detail, fix=fix_hint("onboarding:"), group="onboarding",
    )


def _guard(name: str, fn: Callable[[], list[DoctorItem]]) -> list[DoctorItem]:
    """Run a check family; an unexpected crash becomes one failed item, not a traceback."""

    try:
        return fn()
    except Exception as exc:  # pragma: no cover - exercised via injected failures in tests
        return [
            DoctorItem(
                code=f"{name}:error", status=STATUS_FAIL,
                title=f"{name} checks could not run",
                detail=f"{type(exc).__name__}: {exc}",
                fix="Re-run with `--json` and share the output if this keeps happening.",
                group=name,
            )
        ]


def build_doctor_report(
    root: Path | None = None,
    *,
    live: bool = False,
    full: bool = False,
    timeout: float = 3.0,
    environ: Mapping[str, str] | None = None,
    host_inspector: Callable[[Path], object] | None = None,
    preflight_fn: Callable[..., Iterable[object]] | None = None,
    probe_fn: Callable[..., Iterable[object]] | None = None,
) -> DoctorReport:
    """Assemble a doctor report.  All collaborators are injectable for tests."""

    if root is None:
        from skeleton.app.assembly import find_repo_root

        root = find_repo_root()
    if host_inspector is None:
        from skeleton.app.preloader import inspect_host

        host_inspector = lambda r: inspect_host(r, require_pip=False)  # noqa: E731
    if preflight_fn is None:
        from skeleton.app.assembly import preflight as preflight_fn
    if probe_fn is None:
        from skeleton.app.health import probe_application as probe_fn

    state = load_onboarding_state(environ)
    items: list[DoctorItem] = [onboarding_item(state)]
    items += _guard("host", lambda: items_from_preload(host_inspector(root)))
    host_codes = {item.code for item in items}
    preflight_items = _guard(
        "repo", lambda: items_from_preflight(preflight_fn(root, runtime=True, environ=environ))
    )
    # The host inspector already reports docker; don't show the same problem twice.
    if "host:docker" in host_codes:
        preflight_items = [i for i in preflight_items if i.code != "runtime:docker"]
    items += preflight_items
    if live:
        items += _guard("live", lambda: items_from_probes(probe_fn(full=full, timeout=timeout)))
    else:
        items.append(
            DoctorItem(
                code="probe:skipped", status=STATUS_SKIP, title="Live service probes skipped",
                detail="pass --live to check running services", group="live",
            )
        )
    first_run = not state.completed or not (root / ".env").exists()
    return DoctorReport(items=tuple(items), first_run=first_run)


def render_doctor_report(report: DoctorReport, *, verbose: bool = False, color: bool = False) -> str:
    """Render a doctor report as friendly, grouped plain text."""

    def paint(text: str, status: str) -> str:
        if not color:
            return text
        code = {STATUS_OK: "32", STATUS_WARN: "33", STATUS_FAIL: "31", STATUS_SKIP: "90"}[status]
        return f"\033[{code}m{text}\033[0m"

    lines = [f"Skeleton doctor — {report.headline}", f"Python {report.python} on {report.platform}", ""]
    groups: dict[str, list[DoctorItem]] = {}
    for item in report.items:
        groups.setdefault(item.group, []).append(item)
    for group, items in groups.items():
        shown = items if verbose else [i for i in items if i.status != STATUS_OK]
        counted = [i for i in items if i.status != STATUS_SKIP]
        passed = sum(1 for i in counted if i.status == STATUS_OK)
        header = f"{group}: {passed}/{len(counted)} ok" if counted else f"{group}: skipped"
        lines.append(header)
        for item in sorted(shown, key=lambda i: _STATUS_ORDER.get(i.status, 9)):
            lines.append("  " + paint(f"{_STATUS_ICON[item.status]} {item.title}", item.status))
            if item.detail and item.detail != item.title:
                lines.append(f"      {item.detail}")
    lines.append("")
    lines.append("Next steps:")
    for index, step in enumerate(report.next_steps(), start=1):
        lines.append(f"  {index}. {step}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# First-run setup
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FirstRunResult:
    ok: bool
    env: dict[str, object] | None
    report: DoctorReport
    state: OnboardingState
    messages: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "skeleton.setup",
            "ok": self.ok,
            "env": self.env,
            "onboarding": self.state.to_dict(),
            "doctor": self.report.to_dict(),
            "messages": list(self.messages),
        }


def run_first_run_setup(
    root: Path | None = None,
    *,
    check_only: bool = False,
    rotate_secrets: bool = False,
    environ: Mapping[str, str] | None = None,
    env_writer: Callable[..., object] | None = None,
    doctor: Callable[..., DoctorReport] = build_doctor_report,
    clock: Callable[[], float] = time.time,
) -> FirstRunResult:
    """Create/repair local config, run doctor, and record onboarding completion.

    ``check_only`` performs no writes at all.  Onboarding is only marked
    complete when the doctor reports no failures.
    """

    if root is None:
        from skeleton.app.assembly import find_repo_root

        root = find_repo_root()
    messages: list[str] = []
    env_payload: dict[str, object] | None = None
    if not check_only:
        if env_writer is None:
            from skeleton.app.setup_runtime import ensure_runtime_environment as env_writer
        try:
            result = env_writer(root, rotate_secrets=rotate_secrets)
        except (OSError, ValueError) as exc:
            messages.append(f"Could not write local config: {exc}")
        else:
            env_payload = result.to_dict() if hasattr(result, "to_dict") else None
            if getattr(result, "created", False):
                messages.append("Created .env with fresh local secrets.")
            elif getattr(result, "changed", False):
                messages.append("Repaired missing or placeholder values in .env.")
            else:
                messages.append(".env already configured; nothing changed.")
            for warning in getattr(result, "warnings", ()) or ():
                messages.append(f"Note: {warning}")

    report = doctor(root, environ=environ)
    state = load_onboarding_state(environ)
    if not check_only and report.ready:
        state = mark_onboarding_complete(repo_root=root, environ=environ, clock=clock)
        messages.append("First-run setup complete.")
        # The report was built before the state flipped; refresh the onboarding row.
        report = DoctorReport(
            items=tuple(onboarding_item(state) if i.code == "onboarding:state" else i for i in report.items),
            first_run=False,
            python=report.python,
            platform=report.platform,
        )
    elif not report.ready:
        messages.append("Setup is not finished yet; fix the problems below and run it again.")
    return FirstRunResult(
        ok=report.ready, env=env_payload, report=report, state=state, messages=tuple(messages)
    )


# ---------------------------------------------------------------------------
# CLI glue
# ---------------------------------------------------------------------------


def suggest_command(name: str, commands: Sequence[str]) -> str | None:
    """Return the closest known command for a typo, if any."""

    matches = difflib.get_close_matches(name.lower(), list(commands), n=1, cutoff=0.6)
    return matches[0] if matches else None


def _use_color(stream: object) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")


def run_doctor_cli(argv: Sequence[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m skeleton doctor", description="Check this install and explain how to fix problems.")
    parser.add_argument("--live", action="store_true", help="also probe running services")
    parser.add_argument("--full", action="store_true", help="probe the full service profile")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("-v", "--verbose", action="store_true", help="show passing checks too")
    args = parser.parse_args(list(argv))
    report = build_doctor_report(live=args.live, full=args.full, timeout=args.timeout)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_doctor_report(report, verbose=args.verbose, color=_use_color(sys.stdout)))
    return 0 if report.ready else 1


def run_setup_cli(argv: Sequence[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m skeleton setup", description="First-run setup: local config, readiness checks, next steps.")
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    parser.add_argument("--rotate-secrets", action="store_true", help="regenerate local secrets in .env")
    parser.add_argument("--reset", action="store_true", help="forget onboarding state and exit")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(list(argv))
    if args.reset:
        removed = reset_onboarding()
        if args.json:
            print(json.dumps({"kind": "skeleton.setup.reset", "removed": removed}))
        else:
            print("Onboarding reset; the next run will start first-run setup." if removed else "Onboarding was not set up yet; nothing to reset.")
        return 0
    result = run_first_run_setup(check_only=args.check, rotate_secrets=args.rotate_secrets)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
    else:
        print("Skeleton setup" + (" (check only)" if args.check else ""))
        for message in result.messages:
            print(f"  {message}")
        print("")
        print(render_doctor_report(result.report, color=_use_color(sys.stdout)))
    return 0 if result.ok else 1


__all__ = [
    "DoctorItem", "DoctorReport", "FirstRunResult", "OnboardingState",
    "build_doctor_report", "config_dir", "fix_hint", "load_onboarding_state",
    "mark_onboarding_complete", "onboarding_path", "render_doctor_report",
    "reset_onboarding", "run_doctor_cli", "run_first_run_setup", "run_setup_cli",
    "suggest_command",
]
