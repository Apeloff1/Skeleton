"""Local Studio: a same-origin browser UI for the native (Docker-free) install.

``python -m skeleton.app.windows_first_install serve`` mounts this beside the
canonical Skeleton API. Requests under ``/studio`` are dispatched here; every
other request (including ASGI lifespan) goes to the unchanged canonical app,
so its seal gate, charter and routes are not modified or bypassed.

Authentication follows the local-notebook pattern: ``serve`` generates a
random launch token, writes the Studio URL (token in the URL *fragment*, so it
never reaches a server log or Referer) to an owner-only file, and the
launcher opens it. Every ``/studio/api`` call must carry the token in
``x-skeleton-studio-token``. The seal secret never leaves the server: the
Studio backend calls the canonical ``/api/v1/game/build`` route through the
sealed :class:`~skeleton.app.windows_first_install.ApiClient`.

Defences: loopback ``Host`` allow-list (DNS rebinding), cross-origin
``Origin`` rejection, strict CSP with no inline script, ``nosniff``,
``frame-ancestors 'none'``, bounded bodies, and path-checked project I/O.
"""

from __future__ import annotations

import hmac
import io
import json
import re
import secrets
import threading
import time
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from skeleton.app import windows_first_install as wfi

STUDIO_PREFIX = "/studio"
TOKEN_HEADER = "x-skeleton-studio-token"
SIDECAR = ".skeleton-build.json"
STATUS_SCHEMA = "skeleton.local_studio.status.v1"
EDITABLE_SUFFIXES = frozenset({".gd", ".tscn", ".tres", ".json", ".cfg", ".godot", ".md", ".txt", ".gdshader"})
MAX_EDIT_BYTES = 512 * 1024
MAX_BRIEF_CHARS = 2000
_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")
_ASSET_DIR = Path(__file__).with_name("local_studio_assets")
_ASSETS = {
    "app.js": "text/javascript; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
}
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "content-security-policy": CSP,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


@dataclass
class StudioSettings:
    """Everything the Studio needs; built once by ``serve``."""

    port: int
    games_dir: Path
    seal_secret: str
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    api_base: str | None = None
    godot: Callable[[], Path | None] = wfi.find_godot
    client_factory: Callable[["StudioSettings"], wfi.ApiClient] | None = None
    runner: Callable[..., Any] | None = None
    opener: Callable[[Path, Path], int] = wfi.play_open

    @property
    def base(self) -> str:
        return self.api_base or f"http://127.0.0.1:{self.port}"

    def client(self) -> wfi.ApiClient:
        if self.client_factory is not None:
            return self.client_factory(self)
        return wfi.ApiClient(self.base, secret=self.seal_secret, timeout=30.0)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}{STUDIO_PREFIX}/#token={self.token}"


def write_studio_url(settings: StudioSettings, run_dir: Path) -> Path:
    """Persist the tokenised Studio URL for the launcher (owner-only on POSIX)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "studio.url"
    tmp = run_dir / "studio.url.tmp"
    tmp.write_text(settings.url + "\n", encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:  # pragma: no cover - Windows ACLs come from the run dir
        pass
    tmp.replace(target)
    return target


# --------------------------------------------------------------------------- projects


def _project_dir(settings: StudioSettings, name: str) -> Path:
    if not _PROJECT_RE.fullmatch(name or ""):
        raise LookupError("unknown project")
    path = settings.games_dir / name
    if not (path / "project.godot").is_file():
        raise LookupError("unknown project")
    return path


def _project_file(project: Path, rel: str) -> Path:
    safe = wfi._safe_relative(rel)  # raises FirstInstallError on traversal
    target = project.joinpath(*safe.parts)
    if not target.resolve().is_relative_to(project.resolve()):
        raise wfi.FirstInstallError("path escapes the project")
    return target


def _sidecar(project: Path) -> dict[str, Any]:
    try:
        data = json.loads((project / SIDECAR).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def list_projects(settings: StudioSettings) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not settings.games_dir.is_dir():
        return rows
    for marker in settings.games_dir.glob("*/project.godot"):
        project = marker.parent
        if not _PROJECT_RE.fullmatch(project.name):
            continue
        meta = _sidecar(project)
        rows.append({
            "name": project.name,
            "title": meta.get("title") or project.name,
            "genre": meta.get("genre"),
            "proof": meta.get("proof"),
            "created": meta.get("created") or project.stat().st_mtime,
            "last_playtest": meta.get("last_playtest"),
        })
    rows.sort(key=lambda row: float(row["created"] or 0), reverse=True)
    return rows


def project_files(project: Path) -> list[dict[str, Any]]:
    files = []
    for path in sorted(project.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(project).as_posix()
        if rel == SIDECAR or rel.startswith(".godot/") or "/." in f"/{rel}":
            continue
        files.append({"path": rel, "bytes": path.stat().st_size,
                      "editable": path.suffix.lower() in EDITABLE_SUFFIXES})
    return files


def export_zip(project: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in project_files(project):
            archive.write(project / item["path"], f"{project.name}/{item['path']}")
    return buffer.getvalue()


# --------------------------------------------------------------------------- builds


class BuildTracker:
    """Maps Studio build ids to canonical executions and persists finished projects once."""

    def __init__(self, settings: StudioSettings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._builds: dict[str, dict[str, Any]] = {}

    def start(self, brief: str, playtest: str) -> dict[str, Any]:
        client = self._settings.client()
        status, ack = client.request("POST", "/api/v1/game/build", {
            "brief": brief, "playtest": playtest, "deadline_s": 120.0, "include_files": True,
        })
        if status != 202 or not isinstance(ack, Mapping) or not ack.get("execution_id"):
            detail = ack.get("detail") if isinstance(ack, Mapping) else None
            raise wfi.FirstInstallError(f"the build was not accepted (HTTP {status}): {detail or 'see API log'}")
        execution = str(ack["execution_id"])
        with self._lock:
            self._builds[execution] = {"brief": brief, "playtest": playtest, "project": None,
                                       "started": time.time()}
        return {"build_id": execution, "status": "queued"}

    def view(self, build_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._builds.get(build_id)
        if record is None:
            raise LookupError("unknown build")
        status, view = self._settings.client().request("GET", f"/api/v1/game/build/{build_id}")
        if status != 200 or not isinstance(view, Mapping):
            raise wfi.FirstInstallError(f"build status unavailable (HTTP {status})")
        state = str(view.get("status") or "queued")
        result = view.get("result") if isinstance(view.get("result"), Mapping) else {}
        out: dict[str, Any] = {
            "build_id": build_id, "status": state,
            "progress": float(view.get("progress") or 0.0), "message": str(view.get("message") or state),
            "elapsed_s": round(time.time() - record["started"], 1),
        }
        if state == "failed":
            error = view.get("error")
            out["error"] = (error.get("message") if isinstance(error, Mapping) else None) or "the build failed"
        if state == "succeeded":
            if not result.get("ok"):
                out["status"] = "failed"
                out["error"] = str(result.get("error") or "the build did not prove its core loop")
                return out
            with self._lock:
                project = record.get("project")
                if project is None:
                    project = self._persist(record, result)
                    record["project"] = project
            spec = result.get("spec") if isinstance(result.get("spec"), Mapping) else {}
            out.update({
                "project": project,
                "title": spec.get("title"), "genre": spec.get("genre"),
                "proof": result.get("proof"),
                "playtest": (result.get("playtest") or {}).get("status") if isinstance(result.get("playtest"), Mapping) else None,
                "stubbed": list(result.get("stubbed") or []),
            })
        return out

    def _persist(self, record: Mapping[str, Any], result: Mapping[str, Any]) -> str:
        files = result.get("files")
        if not isinstance(files, Mapping):
            raise wfi.FirstInstallError("the API omitted project files")
        spec = result.get("spec") if isinstance(result.get("spec"), Mapping) else {}
        title = str(spec.get("title") or "game")
        dest = wfi.unique_project_dir(self._settings.games_dir, title)
        wfi.write_project_files(files, dest)
        (dest / SIDECAR).write_text(json.dumps({
            "schema": "skeleton.local_studio.build.v1",
            "title": title, "genre": spec.get("genre"), "brief": record["brief"],
            "proof": result.get("proof"), "execution_id": result.get("execution_id"),
            "created": time.time(), "stubbed": list(result.get("stubbed") or []),
        }, indent=2), encoding="utf-8")
        return dest.name


# --------------------------------------------------------------------------- app


def _allowed_hosts(port: int) -> frozenset[str]:
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"})


def create_studio_app(settings: StudioSettings) -> Any:
    from fastapi import Body, FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    app = FastAPI(title="Skeleton Local Studio", docs_url=None, redoc_url=None, openapi_url=None)
    tracker = BuildTracker(settings)
    hosts = _allowed_hosts(settings.port)
    origins = frozenset(f"http://{host}" for host in hosts)
    settings.games_dir.mkdir(parents=True, exist_ok=True)

    @app.middleware("http")
    async def guard(request: Request, call_next: Callable[..., Any]) -> Any:
        host = request.headers.get("host", "")
        if host not in hosts:
            return JSONResponse({"error": "host not allowed"}, status_code=403, headers=SECURITY_HEADERS)
        origin = request.headers.get("origin")
        if origin is not None and origin not in origins:
            return JSONResponse({"error": "cross-origin request refused"}, status_code=403, headers=SECURITY_HEADERS)
        if request.url.path.startswith(f"{STUDIO_PREFIX}/api/"):
            supplied = request.headers.get(TOKEN_HEADER, "")
            if not supplied or not hmac.compare_digest(supplied.encode(), settings.token.encode()):
                return JSONResponse({"error": "studio token required"}, status_code=401, headers=SECURITY_HEADERS)
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    def fail(exc: Exception) -> HTTPException:
        if isinstance(exc, LookupError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, wfi.FirstInstallError):
            return HTTPException(status_code=422, detail=str(exc))
        return HTTPException(status_code=502, detail=f"{type(exc).__name__}")

    @app.get(STUDIO_PREFIX, include_in_schema=False)
    def studio_root() -> Response:
        return Response(status_code=308, headers={"location": f"{STUDIO_PREFIX}/"})

    @app.get(f"{STUDIO_PREFIX}/", include_in_schema=False)
    def studio_index() -> HTMLResponse:
        return HTMLResponse((_ASSET_DIR / "index.html").read_text(encoding="utf-8"))

    @app.get(STUDIO_PREFIX + "/{asset}", include_in_schema=False)
    def studio_asset(asset: str) -> Response:
        if asset not in _ASSETS:
            raise HTTPException(status_code=404)
        return Response((_ASSET_DIR / asset).read_bytes(), media_type=_ASSETS[asset])

    @app.get(f"{STUDIO_PREFIX}/api/status")
    def status() -> dict[str, Any]:
        report = wfi.doctor(require_godot=False)
        checks = {c["id"]: {"ok": c["ok"], "detail": c["detail"], "remediation": c["remediation"]}
                  for c in report["checks"]}
        api_ok = True
        try:
            code, body = settings.client().request("GET", "/api/v1/health")
            api_ok = code == 200 and isinstance(body, Mapping) and body.get("status") == "healthy"
        except Exception:
            api_ok = False
        return {"schema": STATUS_SCHEMA, "api_healthy": api_ok, "godot_ready": bool(checks.get("godot", {}).get("ok")),
                "checks": checks, "games_dir": str(settings.games_dir), "projects": len(list_projects(settings))}

    @app.get(f"{STUDIO_PREFIX}/api/projects")
    def projects() -> dict[str, Any]:
        return {"projects": list_projects(settings)}

    @app.post(f"{STUDIO_PREFIX}/api/builds", status_code=202)
    def create_build(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        brief = payload.get("brief")
        playtest = payload.get("playtest", "auto")
        if not isinstance(brief, str) or not brief.strip():
            raise HTTPException(status_code=422, detail="Describe the game you want to build.")
        if len(brief) > MAX_BRIEF_CHARS:
            raise HTTPException(status_code=422, detail=f"Keep the description under {MAX_BRIEF_CHARS} characters.")
        if playtest not in {"off", "auto", "require"}:
            raise HTTPException(status_code=422, detail="playtest must be off, auto or require")
        try:
            return tracker.start(" ".join(brief.split()), playtest)
        except Exception as exc:
            raise fail(exc) from None

    @app.get(STUDIO_PREFIX + "/api/builds/{build_id}")
    def build_status(build_id: str) -> dict[str, Any]:
        try:
            return tracker.view(build_id)
        except Exception as exc:
            raise fail(exc) from None

    @app.get(STUDIO_PREFIX + "/api/projects/{name}")
    def project_detail(name: str) -> dict[str, Any]:
        try:
            project = _project_dir(settings, name)
        except LookupError as exc:
            raise fail(exc) from None
        return {"name": name, "meta": _sidecar(project), "files": project_files(project)}

    @app.get(STUDIO_PREFIX + "/api/projects/{name}/file")
    def read_file(name: str, path: str) -> dict[str, Any]:
        try:
            target = _project_file(_project_dir(settings, name), path)
            if not target.is_file():
                raise LookupError("unknown file")
            if target.stat().st_size > MAX_EDIT_BYTES:
                raise wfi.FirstInstallError("file is too large to open here")
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=415, detail="binary file") from None
        except Exception as exc:
            raise fail(exc) from None
        return {"path": path, "content": text, "editable": target.suffix.lower() in EDITABLE_SUFFIXES}

    @app.put(STUDIO_PREFIX + "/api/projects/{name}/file")
    def write_file(name: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        rel, content = payload.get("path"), payload.get("content")
        if not isinstance(rel, str) or not isinstance(content, str):
            raise HTTPException(status_code=422, detail="path and content are required")
        if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
            raise HTTPException(status_code=413, detail="file is too large")
        try:
            target = _project_file(_project_dir(settings, name), rel)
            if not target.is_file():
                raise LookupError("only existing project files can be edited")
            if target.suffix.lower() not in EDITABLE_SUFFIXES or PurePosixPath(rel).name == SIDECAR:
                raise wfi.FirstInstallError("this file type cannot be edited here")
            tmp = target.with_name(target.name + ".studio-tmp")
            tmp.write_text(content, encoding="utf-8", newline="\n")
            tmp.replace(target)
        except Exception as exc:
            raise fail(exc) from None
        return {"path": rel, "bytes": len(content.encode("utf-8")), "saved": True}

    @app.post(STUDIO_PREFIX + "/api/projects/{name}/playtest")
    def playtest(name: str) -> dict[str, Any]:
        try:
            project = _project_dir(settings, name)
            godot = settings.godot()
            if godot is None:
                raise wfi.FirstInstallError("Godot is not installed; re-run bootstrap.ps1")
            kwargs: dict[str, Any] = {}
            if settings.runner is not None:
                kwargs["runner"] = settings.runner
            result = wfi.play_check(project, godot, **kwargs)
        except Exception as exc:
            raise fail(exc) from None
        meta = _sidecar(project)
        meta["last_playtest"] = {"ok": result["ok"], "at": time.time()}
        (project / SIDECAR).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return result

    @app.post(STUDIO_PREFIX + "/api/projects/{name}/open")
    def open_in_godot(name: str) -> dict[str, Any]:
        try:
            project = _project_dir(settings, name)
            godot = settings.godot()
            if godot is None:
                raise wfi.FirstInstallError("Godot is not installed; re-run bootstrap.ps1")
            pid = settings.opener(project, godot)
        except Exception as exc:
            raise fail(exc) from None
        return {"opened": True, "pid": pid}

    @app.get(STUDIO_PREFIX + "/api/projects/{name}/export.zip")
    def export(name: str) -> Response:
        try:
            project = _project_dir(settings, name)
        except Exception as exc:
            raise fail(exc) from None
        return Response(export_zip(project), media_type="application/zip",
                        headers={"content-disposition": f'attachment; filename="{name}.zip"'})

    return app


def compose(canonical: Any, studio: Any) -> Callable[..., Any]:
    """ASGI dispatcher: ``/studio`` to the Studio, everything else (and lifespan) to the canonical app."""

    async def app(scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        path = scope.get("path", "") if scope.get("type") in {"http", "websocket"} else ""
        if path == STUDIO_PREFIX or path.startswith(STUDIO_PREFIX + "/"):
            await studio(scope, receive, send)
        else:
            await canonical(scope, receive, send)

    return app
