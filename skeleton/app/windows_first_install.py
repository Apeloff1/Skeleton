"""Native (Docker-free) Windows first install: doctor, local API, build and play.

The PowerShell bootstrap (``scripts/windows/bootstrap.ps1``) owns toolchain
acquisition, the virtual environment and the per-user configuration. It then
delegates every product step to this module so that Windows, CI and Linux
developer machines run the same, tested code:

``doctor``  Host and toolchain readiness (Python, Skeleton import, Godot 4,
            writable games directory, seal secret present). Never prints a
            secret value.
``serve``   Starts the canonical Skeleton API (:func:`skeleton.api.server.
            create_app`) bound to loopback only. No Docker or MongoDB is
            required; canonical memory reports ``disabled`` until configured.
``build``   Builds a playable Godot project from a natural-language brief
            through the running API (``POST /api/v1/game/build``), downloads
            the proven files and writes them under the games directory.
``play``    Opens a generated project in Godot, or with ``--check`` proves it
            headlessly: ``CORE_LOOP_OK`` from the main scene and
            ``FORGE_INTERACTIVE_OK`` from the maintained input replay.
``smoke``   ``build`` followed by ``play --check``; the CI acceptance journey.

The only executor for games remains
:func:`skeleton.forge.game_builder.build_playable_game` behind the API; this
module is an adapter and never compiles, repairs or proves a game itself.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

DOCTOR_SCHEMA = "skeleton.windows_first_install.doctor.v1"
BUILD_SCHEMA = "skeleton.windows_first_install.build.v1"
PLAY_SCHEMA = "skeleton.windows_first_install.play.v1"
SMOKE_SCHEMA = "skeleton.windows_first_install.smoke.v1"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8710
ATTESTER = "windows-first-install"
TENANT = "studio"
CORE_LOOP_MARKER = "CORE_LOOP_OK"
INTERACTIVE_MARKER = "FORGE_INTERACTIVE_OK"
INTERACTIVE_SCRIPT = "res://scripts/runtime/interactive_smoke.gd"
MIN_PYTHON = (3, 11)
MIN_GODOT = (4, 3)
SAMPLE_BRIEF = (
    "A small platformer. Fantasy: rain-slick ledges above a drowned switchyard. "
    "Core loop: run and jump from ledge to ledge until the far gate. Scope: small prototype."
)
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
_GODOT_VERSION_RE = re.compile(r"^(\d+)\.(\d+)")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_PROJECT_FILES = 4096
_MAX_PROJECT_BYTES = 64 * 1024 * 1024

Runner = Callable[..., subprocess.CompletedProcess]


class FirstInstallError(RuntimeError):
    """A first-install step failed with an operator-facing remediation."""

    def __init__(self, message: str, *, remediation: str = "") -> None:
        super().__init__(message)
        self.remediation = remediation


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    required: bool
    detail: str
    remediation: str = ""


# --------------------------------------------------------------------------- paths


def default_data_root(env: Mapping[str, str] | None = None) -> Path:
    """Per-user data root: ``%LOCALAPPDATA%\\Skeleton`` on Windows."""
    env = os.environ if env is None else env
    explicit = env.get("SKELETON_HOME", "").strip()
    if explicit:
        return Path(explicit)
    local = env.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "Skeleton"
    return Path.home() / ".local" / "share" / "skeleton"


def default_games_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    explicit = env.get("SKELETON_GAMES_DIR", "").strip()
    if explicit:
        return Path(explicit)
    return default_data_root(env) / "games"


def slugify(title: str, *, limit: int = 48) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")[:limit].strip("-")
    return slug or "game"


# --------------------------------------------------------------------------- godot


def find_godot(env: Mapping[str, str] | None = None) -> Path | None:
    """Resolve Godot the same way the canonical playtest does, console build first."""
    env = os.environ if env is None else env
    for name in ("SKELETON_GODOT_BIN", "GODOT_BINARY"):
        value = env.get(name, "").strip()
        if value and Path(value).is_file():
            return Path(value)
    for name in ("godot4", "godot"):
        found = shutil.which(name, path=env.get("PATH"))
        if found:
            return Path(found)
    return None


def parse_godot_version(text: str) -> tuple[int, int] | None:
    match = _GODOT_VERSION_RE.match(text.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def godot_version(binary: Path, runner: Runner = subprocess.run) -> str | None:
    try:
        proc = runner(
            [str(binary), "--headless", "--version"],
            capture_output=True, text=True, timeout=60, creationflags=_creationflags(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    return line[-1].strip() if line else None


# --------------------------------------------------------------------------- doctor


def doctor(
    *,
    env: Mapping[str, str] | None = None,
    runner: Runner = subprocess.run,
    require_godot: bool = True,
    require_secret: bool = True,
) -> dict[str, Any]:
    """Return a machine-readable readiness report. Required failures set ``ok`` false."""
    env = os.environ if env is None else env
    checks: list[Check] = []
    version = sys.version_info[:2]
    checks.append(Check(
        "python", version >= MIN_PYTHON, True,
        f"Python {platform.python_version()} ({sys.executable})",
        "Install Python 3.11 or newer (bootstrap.ps1 -InstallMissing uses winget).",
    ))
    try:
        from skeleton.forge.game_builder import build_playable_game  # noqa: F401
        from skeleton.api.server import create_app  # noqa: F401
        checks.append(Check("skeleton_import", True, True, "skeleton API and game builder import"))
    except Exception as exc:  # pragma: no cover - exercised on broken installs
        checks.append(Check(
            "skeleton_import", False, True, f"import failed: {type(exc).__name__}",
            "Re-run scripts\\windows\\bootstrap.ps1 to reinstall dependencies into .venv.",
        ))
    try:
        import uvicorn  # noqa: F401
        checks.append(Check("uvicorn", True, True, "ASGI server available"))
    except ImportError:
        checks.append(Check("uvicorn", False, True, "uvicorn is not installed",
                            "Re-run scripts\\windows\\bootstrap.ps1."))
    godot = find_godot(env)
    if godot is None:
        checks.append(Check(
            "godot", False, require_godot, "Godot 4 binary not found",
            "Run bootstrap.ps1 (downloads pinned, SHA-512 verified Godot) or set SKELETON_GODOT_BIN.",
        ))
    else:
        reported = godot_version(godot, runner)
        parsed = parse_godot_version(reported or "")
        ok = parsed is not None and parsed >= MIN_GODOT and parsed[0] == 4
        checks.append(Check(
            "godot", ok, require_godot, f"{godot} -> {reported or 'no version output'}",
            "" if ok else "Install Godot 4.3 or newer (4.x) and point SKELETON_GODOT_BIN at the console binary.",
        ))
    games = default_games_dir(env)
    try:
        games.mkdir(parents=True, exist_ok=True)
        probe = games / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(Check("games_dir", True, True, f"writable: {games}"))
    except OSError as exc:
        checks.append(Check("games_dir", False, True, f"not writable: {games} ({exc.strerror})",
                            "Choose another folder with SKELETON_GAMES_DIR."))
    has_secret = bool(env.get("GF_SEAL_SECRET", "").strip() or env.get("GF_SEAL_KEYRING", "").strip())
    checks.append(Check(
        "seal_secret", has_secret, require_secret,
        "request seal secret configured" if has_secret else "GF_SEAL_SECRET is not set",
        "" if has_secret else "Start through scripts\\windows\\skeleton.ps1, which loads the per-user secret.",
    ))
    provider = env.get("AI_PROVIDER", "").strip().lower() or "none"
    provider_detail = {
        "none": "no model provider: deterministic game compiler only (supported)",
        "openai": "hosted provider configured" if env.get("OPENAI_API_KEY") else "openai selected but no key loaded",
        "local": "guarded local provider selected; needs the trusted guard bootstrap (see docs)",
    }.get(provider, f"provider {provider!r}")
    checks.append(Check("ai_provider", True, False, provider_detail))
    required_ok = all(check.ok for check in checks if check.required)
    return {
        "schema": DOCTOR_SCHEMA,
        "ok": required_ok,
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "checks": [asdict(check) for check in checks],
    }


# --------------------------------------------------------------------------- api client


class ApiClient:
    """Minimal sealed client for the local Skeleton API (stdlib only)."""

    def __init__(self, base_url: str, *, secret: str, attester: str = ATTESTER,
                 tenant: str = TENANT, timeout: float = 30.0,
                 opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        if not secret:
            raise FirstInstallError("GF_SEAL_SECRET is not set",
                                    remediation="Start through scripts\\windows\\skeleton.ps1.")
        self.base_url = base_url.rstrip("/")
        self._secret = secret
        self._attester = attester
        self._tenant = tenant
        self._timeout = timeout
        self._opener = opener

    def _headers(self) -> dict[str, str]:
        from skeleton.api.hmac_seal import mint_seal

        seal = mint_seal(self._attester, secret=self._secret)
        if not seal:
            raise FirstInstallError("could not mint a request seal")
        return {"content-type": "application/json", "accept": "application/json",
                "x-gf-seal": seal, "x-skeleton-tenant": self._tenant}

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> tuple[int, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=self._headers())
        try:
            with self._opener(req, timeout=self._timeout) as response:
                raw = response.read()
                return int(response.status), json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()[:4096]
            try:
                return int(exc.code), json.loads(raw) if raw else None
            except ValueError:
                return int(exc.code), {"raw": raw.decode("utf-8", "replace")}

    def wait_healthy(self, *, timeout: float = 90.0, interval: float = 1.0,
                     sleep: Callable[[float], None] = time.sleep,
                     clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
        deadline = clock() + timeout
        last: Any = None
        while True:
            try:
                status, body = self.request("GET", "/api/v1/health")
                last = (status, body)
                if status == 200 and isinstance(body, Mapping) and body.get("status") == "healthy":
                    return dict(body)
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
                last = type(exc).__name__
            if clock() >= deadline:
                raise FirstInstallError(
                    f"Skeleton API did not become healthy at {self.base_url} (last: {str(last)[:200]})",
                    remediation="Check the API log under %LOCALAPPDATA%\\Skeleton\\logs and run 'skeleton.ps1 doctor'.",
                )
            sleep(interval)

    def build(self, brief: str, *, playtest: str = "require", deadline_s: float = 120.0,
              poll_timeout: float = 240.0, interval: float = 1.0,
              sleep: Callable[[float], None] = time.sleep,
              clock: Callable[[], float] = time.monotonic,
              on_status: Callable[[Mapping[str, Any]], None] | None = None) -> dict[str, Any]:
        status, ack = self.request("POST", "/api/v1/game/build", {
            "brief": brief, "playtest": playtest, "deadline_s": deadline_s, "include_files": True,
        })
        if status != 202 or not isinstance(ack, Mapping) or not ack.get("execution_id"):
            raise FirstInstallError(f"build was not accepted (HTTP {status}): {str(ack)[:300]}")
        ref = str(ack.get("status_ref") or f"/api/v1/game/build/{ack['execution_id']}")
        if not ref.startswith("/api/v1/game/build/"):
            raise FirstInstallError("unexpected build status reference")
        deadline = clock() + poll_timeout
        while True:
            status, view = self.request("GET", ref)
            if status != 200 or not isinstance(view, Mapping):
                raise FirstInstallError(f"build status failed (HTTP {status})")
            if on_status is not None:
                on_status(view)
            if view.get("status") in TERMINAL:
                return dict(view)
            if clock() >= deadline:
                raise FirstInstallError(f"build {ack['execution_id']} did not finish in {poll_timeout:g}s")
            sleep(interval)


# --------------------------------------------------------------------------- projects


def _safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if (not name or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts)
            or ":" in name or len(path.parts) > 16):
        raise FirstInstallError(f"refusing unsafe project path {name!r}")
    return path


def write_project_files(files: Mapping[str, str], dest: Path) -> list[str]:
    """Write API-returned project files under ``dest``; refuses traversal and overwrite."""
    if not isinstance(files, Mapping) or not files:
        raise FirstInstallError("the build returned no project files")
    if len(files) > _MAX_PROJECT_FILES:
        raise FirstInstallError("the build returned too many files")
    total = sum(len(str(text).encode("utf-8")) for text in files.values())
    if total > _MAX_PROJECT_BYTES:
        raise FirstInstallError("the build returned too much data")
    if dest.exists() and any(dest.iterdir()):
        raise FirstInstallError(f"destination is not empty: {dest}")
    staged = dest.with_name(dest.name + ".partial")
    if staged.exists():
        shutil.rmtree(staged)
    written: list[str] = []
    for name in sorted(files):
        rel = _safe_relative(str(name))
        target = staged.joinpath(*rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(files[name]), encoding="utf-8", newline="\n")
        written.append(rel.as_posix())
    if "project.godot" not in written:
        shutil.rmtree(staged, ignore_errors=True)
        raise FirstInstallError("the build did not include project.godot")
    if dest.exists():
        dest.rmdir()
    staged.replace(dest)
    return written


def unique_project_dir(games_dir: Path, title: str, *, clock: Callable[[], float] = time.time) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(clock()))
    base = games_dir / f"{slugify(title)}-{stamp}"
    candidate, n = base, 1
    while candidate.exists():
        n += 1
        candidate = games_dir / f"{base.name}-{n}"
    return candidate


def latest_project(games_dir: Path) -> Path | None:
    projects = [p.parent for p in games_dir.glob("*/project.godot") if p.is_file()]
    return max(projects, key=lambda p: p.stat().st_mtime) if projects else None


def build_via_api(client: ApiClient, brief: str, games_dir: Path, *, playtest: str = "require",
                  echo: Callable[[str], None] = print) -> dict[str, Any]:
    started = time.monotonic()
    seen: set[str] = set()

    def report(view: Mapping[str, Any]) -> None:
        message = str(view.get("message") or view.get("status") or "")
        if message and message not in seen:
            seen.add(message)
            echo(f"  [{float(view.get('progress') or 0) * 100:5.1f}%] {message}")

    view = client.build(brief, playtest=playtest, on_status=report)
    result = view.get("result") if isinstance(view.get("result"), Mapping) else None
    if view.get("status") != "succeeded" or not result or result.get("ok") is not True:
        error = view.get("error") or (result or {}).get("error")
        raise FirstInstallError(f"game build {view.get('status')}: {error}",
                                remediation="Run 'skeleton.ps1 doctor'; Godot must be installed for playtest=require.")
    proof = str(result.get("proof") or "")
    if playtest == "require" and CORE_LOOP_MARKER not in proof:
        raise FirstInstallError(f"build succeeded without {CORE_LOOP_MARKER} proof")
    title = str((result.get("spec") or {}).get("title") or "game")
    dest = unique_project_dir(games_dir, title)
    files = result.get("files")
    if not isinstance(files, Mapping):
        raise FirstInstallError("the API omitted project files (files_omitted or include_files ignored)")
    written = write_project_files(files, dest)
    return {
        "schema": BUILD_SCHEMA,
        "ok": True,
        "execution_id": view.get("execution_id"),
        "title": title,
        "genre": (result.get("spec") or {}).get("genre"),
        "proof": proof,
        "playtest_status": (result.get("playtest") or {}).get("status"),
        "project_dir": str(dest),
        "file_count": len(written),
        "elapsed_s": round(time.monotonic() - started, 2),
        "stubbed": list(result.get("stubbed") or []),
    }


# --------------------------------------------------------------------------- play


def _run_godot(runner: Runner, cmd: Sequence[str], cwd: Path, timeout: float) -> tuple[int, str]:
    try:
        proc = runner(list(cmd), cwd=str(cwd), capture_output=True, text=True,
                      timeout=timeout, creationflags=_creationflags())
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        return 124, out if isinstance(out, str) else out.decode("utf-8", "replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def play_check(project: Path, godot: Path, *, runner: Runner = subprocess.run,
               timeout: float = 180.0) -> dict[str, Any]:
    """Prove a generated project headlessly: core loop plus the input replay."""
    if not (project / "project.godot").is_file():
        raise FirstInstallError(f"not a Godot project: {project}")
    steps: list[dict[str, Any]] = []
    plan = (
        ("import", [str(godot), "--headless", "--path", str(project), "--import"], None),
        ("core_loop", [str(godot), "--headless", "--path", str(project), "--quit-after", "240"], CORE_LOOP_MARKER),
        ("interactive", [str(godot), "--headless", "--fixed-fps", "60", "--path", str(project),
                         "--script", INTERACTIVE_SCRIPT], INTERACTIVE_MARKER),
    )
    ok = True
    for name, cmd, marker in plan:
        if name == "interactive" and not (project / "scripts" / "runtime" / "interactive_smoke.gd").is_file():
            steps.append({"step": name, "ok": True, "skipped": "project has no input replay"})
            continue
        rc, log = _run_godot(runner, cmd, project, timeout)
        line = ""
        if marker is not None:
            line = next((ln.strip() for ln in log.splitlines() if ln.strip().startswith(marker)), "")
        # Import must exit cleanly; a run step is proven only by its marker line,
        # which the generated runtime prints after the real loop completes.
        passed = rc == 0 if marker is None else bool(line) and rc == 0
        steps.append({"step": name, "ok": passed, "returncode": rc, "marker": line[:300]})
        if not passed:
            ok = False
            steps[-1]["log_tail"] = log[-1500:]
            break
    return {"schema": PLAY_SCHEMA, "ok": ok, "project_dir": str(project), "godot": str(godot), "steps": steps}


def play_open(project: Path, godot: Path) -> int:
    """Open the project in a normal Godot window (detached)."""
    if not (project / "project.godot").is_file():
        raise FirstInstallError(f"not a Godot project: {project}")
    kwargs: dict[str, Any] = {"cwd": str(project)}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    windowed = godot
    if godot.name.lower().endswith("_console.exe"):
        sibling = godot.with_name(godot.name[: -len("_console.exe")] + ".exe")
        if sibling.is_file():
            windowed = sibling
    proc = subprocess.Popen([str(windowed), "--path", str(project)], **kwargs)
    return proc.pid


# --------------------------------------------------------------------------- serve


def build_app(port: int, *, studio: bool = True) -> tuple[Any, Any]:
    """Canonical API, optionally composed with the Local Studio under ``/studio``."""
    from skeleton.api.server import create_app

    canonical = create_app()
    if not studio:
        return canonical, None
    from skeleton.app.local_studio import StudioSettings, compose, create_studio_app

    settings = StudioSettings(port=port, games_dir=default_games_dir(),
                              seal_secret=os.environ.get("GF_SEAL_SECRET", ""))
    return compose(canonical, create_studio_app(settings)), settings


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, allow_remote: bool = False,
          studio: bool = True) -> None:
    if host not in _LOOPBACK and not allow_remote:
        raise FirstInstallError("refusing to bind a non-loopback address without --allow-remote")
    if not (os.environ.get("GF_SEAL_SECRET") or os.environ.get("GF_SEAL_KEYRING")):
        raise FirstInstallError("GF_SEAL_SECRET is not set; protected routes would fail closed",
                                remediation="Start through scripts\\windows\\skeleton.ps1 start.")
    if allow_remote and studio:
        raise FirstInstallError("the Local Studio is loopback-only; pass --no-studio with --allow-remote")
    import uvicorn

    app, settings = build_app(port, studio=studio)
    if settings is not None:
        from skeleton.app.local_studio import write_studio_url

        url_file = write_studio_url(settings, default_data_root() / "run")
        print(f"Skeleton Local Studio: open the link in {url_file} (or run: skeleton.ps1 studio)", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="info")


# --------------------------------------------------------------------------- cli


def _client_from_env(args: argparse.Namespace) -> ApiClient:
    return ApiClient(f"http://{args.host}:{args.port}", secret=os.environ.get("GF_SEAL_SECRET", ""))


def _emit(payload: Mapping[str, Any], as_json: bool, human: Callable[[], None]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        human()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton.app.windows_first_install",
                                     description="Native Windows first install: doctor, serve, build, play, smoke.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=int(os.environ.get("SKELETON_API_PORT") or DEFAULT_PORT))
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)
    p_doc = sub.add_parser("doctor")
    p_doc.add_argument("--no-godot", action="store_true", help="do not require Godot")
    p_srv = sub.add_parser("serve")
    p_srv.add_argument("--allow-remote", action="store_true")
    p_srv.add_argument("--no-studio", action="store_true", help="serve only the canonical API")
    for name in ("build", "smoke"):
        p = sub.add_parser(name)
        p.add_argument("brief", nargs="?", default=SAMPLE_BRIEF)
        p.add_argument("--games-dir", type=Path, default=None)
        p.add_argument("--playtest", choices=("off", "auto", "require"), default="require")
        p.add_argument("--wait", type=float, default=90.0, help="seconds to wait for the API")
    p_play = sub.add_parser("play")
    p_play.add_argument("project", nargs="?", type=Path, default=None)
    p_play.add_argument("--check", action="store_true", help="headless proof instead of a window")
    args = parser.parse_args(argv)

    try:
        if args.command == "doctor":
            report = doctor(require_godot=not args.no_godot)

            def human() -> None:
                for check in report["checks"]:
                    mark = "OK " if check["ok"] else ("FAIL" if check["required"] else "WARN")
                    print(f"[{mark}] {check['id']}: {check['detail']}")
                    if not check["ok"] and check["remediation"]:
                        print(f"       fix: {check['remediation']}")
                print("Ready." if report["ok"] else "Not ready: fix the FAIL items above.")
            _emit(report, args.json, human)
            return 0 if report["ok"] else 1
        if args.command == "serve":
            serve(args.host, args.port, allow_remote=args.allow_remote, studio=not args.no_studio)
            return 0
        if args.command in {"build", "smoke"}:
            games = args.games_dir or default_games_dir()
            games.mkdir(parents=True, exist_ok=True)
            client = _client_from_env(args)
            echo = (lambda _msg: None) if args.json else print
            echo(f"Waiting for the Skeleton API at {client.base_url} ...")
            client.wait_healthy(timeout=args.wait)
            echo("Building: " + args.brief)
            built = build_via_api(client, args.brief, games, playtest=args.playtest, echo=echo)
            if args.command == "build":
                _emit(built, args.json, lambda: print(
                    f"Built '{built['title']}' ({built['proof']}) -> {built['project_dir']}\n"
                    "Play it: scripts\\windows\\skeleton.ps1 play"))
                return 0
            godot = find_godot()
            if godot is None:
                raise FirstInstallError("Godot not found for the play check")
            played = play_check(Path(built["project_dir"]), godot)
            payload = {"schema": SMOKE_SCHEMA, "ok": bool(played["ok"]), "build": built, "play": played}
            _emit(payload, args.json, lambda: print(
                f"Smoke {'PASSED' if played['ok'] else 'FAILED'}: {built['title']} -> "
                + ", ".join(f"{s['step']}={'ok' if s['ok'] else 'FAIL'}" for s in played["steps"])))
            return 0 if played["ok"] else 1
        if args.command == "play":
            project = args.project or latest_project(default_games_dir())
            if project is None:
                raise FirstInstallError("no generated games yet", remediation="Run: skeleton.ps1 build \"<your idea>\"")
            godot = find_godot()
            if godot is None:
                raise FirstInstallError("Godot not found", remediation="Re-run bootstrap.ps1 or set SKELETON_GODOT_BIN.")
            if args.check:
                played = play_check(project, godot)
                _emit(played, args.json, lambda: print(
                    ("PLAYABLE: " if played["ok"] else "NOT PLAYABLE: ") + str(project)))
                return 0 if played["ok"] else 1
            pid = play_open(project, godot)
            _emit({"schema": PLAY_SCHEMA, "ok": True, "pid": pid, "project_dir": str(project)}, args.json,
                  lambda: print(f"Opened {project} in Godot (pid {pid})."))
            return 0
    except FirstInstallError as exc:
        payload = {"ok": False, "error": str(exc), "remediation": exc.remediation}
        _emit(payload, args.json, lambda: print(f"ERROR: {exc}" + (f"\n  fix: {exc.remediation}" if exc.remediation else ""),
                                                file=sys.stderr))
        return 2
    parser.error("unknown command")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
