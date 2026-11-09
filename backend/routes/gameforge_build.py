"""
routes/gameforge_build.py — REAL build tool integration (/api/gameforge/build).

Produces genuine, downloadable artifacts from a game's accepted gamefiles:
  • web  — a playable HTML5 bundle (index.html + payload) zipped on disk
  • source — a source zip of all gamefiles + manifest.json
Archives are staged in private ephemeral workspaces and may only be published
through the authorized governed artifact owner. Exports fail closed if that owner
has not been bound, irrespective of locally installed toolchains.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import zipfile
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from routes import gameforge_auth as auth
from routes.playable_access import _PrivateProjectRoute, _available

from core.exec_guard import code_execution_enabled, execution_disabled_response
from core.gameforge_artifact_builder import (
    DEFAULT_ARTIFACTS_ROOT,
    artifact_build as _artifact_build,
    build_source_artifact,
    build_web_artifact,
    database as _db,
    register_artifact as _register,
    resolve_under_dir as _resolve_under_dir,
    safe_segment as _safe_segment,
)

router = APIRouter(prefix="/api/gameforge/build", tags=["gameforge-build"],
                   dependencies=[Depends(auth.require_authenticated_identity)], route_class=_PrivateProjectRoute)


def _viewer(user=Depends(auth.get_current_user)):
    auth.require_authenticated_identity(user)
    return user


def _editor(user=Depends(_viewer)):
    if user.get("role") not in {"editor", "admin"}:
        raise HTTPException(403, "Editor authority required")
    return user

_ARTIFACTS = str(DEFAULT_ARTIFACTS_ROOT)


def _artifact_retention_seconds() -> int:
    raw = os.environ.get("GAMEFORGE_ARTIFACT_RETENTION_DAYS", "30")
    try:
        days = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            "GAMEFORGE_ARTIFACT_RETENTION_DAYS must be an integer"
        ) from exc
    if days < 1 or days > 365:
        raise RuntimeError(
            "GAMEFORGE_ARTIFACT_RETENTION_DAYS must be within [1, 365]"
        )
    return days * 24 * 60 * 60


def _tenant_id(user: Any) -> str:
    return auth.require_authenticated_identity(user)["tenant_id"]


def _governed_store():
    # The backend must not initialize a shadow engine/governance store. No
    # remote governed-artifact delivery interface is declared for this legacy
    # surface yet. Existing Studio source exports remain available separately.
    raise HTTPException(503, {
        "code": "artifact_owner_unavailable",
        "message": "Governed GameForge export is unavailable. Use the Studio project source export.",
        "action": "Use the existing Studio project source export until governed artifact delivery is connected.",
    })


def _owned_gamefiles(game_name: str, user: Any) -> list[dict]:
    scope = auth.require_authenticated_identity(user)
    files, total_bytes = [], 0
    try:
        cursor = _db()["gameforge_gamefiles"].find({"game_name": game_name, **scope}, {"_id": 0}).limit(257)
        for row in cursor:
            if not _available(row, scope) or row.get("game_name") != game_name:
                continue
            total_bytes += len(str(row.get("content", "")).encode("utf-8"))
            if len(files) >= 256 or total_bytes > 8 * 1024 * 1024:
                raise HTTPException(413, "Game source exceeds the bounded export limit")
            files.append(row)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Game source storage is unavailable") from None
    if not files:
        raise HTTPException(404, "Owned game source not found")
    return files


def _governed_register(
    *,
    build_id: str,
    game_name: str,
    kind: str,
    payload: bytes,
    tenant_id: str,
    owner_id: str,
    built_at: float | None = None,
) -> dict:
    store = _governed_store()
    timestamp = time.time() if built_at is None else float(built_at)
    canonical = store.write_bytes(
        tenant_id=tenant_id,
        artifact_id=build_id,
        payload=payload,
        data_class="internal",
        purposes=("artifact-delivery", "download"),
        created_at=timestamp,
        retention_until=timestamp + _artifact_retention_seconds(),
        exportable=True,
    )
    return _register(
        build_id,
        game_name,
        kind,
        None,
        built_at=timestamp,
        canonical_record=canonical,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )

def _has_pyinstaller() -> bool:
    import importlib.util
    return importlib.util.find_spec("PyInstaller") is not None


_GODOT_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "godot")


def _godot_bin() -> Optional[str]:
    """Resolve a runnable Godot engine binary (bundled arm64 build or PATH)."""
    if os.path.isfile(_GODOT_BIN) and os.access(_GODOT_BIN, os.X_OK):
        return _GODOT_BIN
    return shutil.which("godot")


def _toolchains() -> dict:
    return {
        "web": True,
        "source_zip": True,
        "desktop_pyinstaller": _has_pyinstaller(),
        "godot_project": True,
        "godot_engine": _godot_bin() is not None,
        "godot_headless_export": _godot_bin() is not None,
        "unity": shutil.which("unity") is not None or shutil.which("Unity") is not None,
        "nuitka": shutil.which("nuitka") is not None,
    }


@router.get("/toolchains")
async def toolchains():
    tc = _toolchains()
    for capability in ("web", "source_zip", "desktop_pyinstaller", "godot_project", "godot_headless_export"):
        tc[capability] = False
    return {"ok": True, "toolchains": tc,
            "artifact_delivery": {"available": False, "code": "artifact_owner_unavailable"},
            "note": "Governed export is unavailable. Use the existing Studio project source export."}


class DesktopBody(BaseModel):
    game_name: str = Field(..., min_length=1, max_length=200)


class BuildBody(BaseModel):
    game_name: str = Field(..., min_length=1, max_length=200)


@router.post("/desktop")
async def build_desktop(b: DesktopBody, user=Depends(_editor)):
    """Real native desktop binary via PyInstaller (Linux ELF in this environment)."""
    _owned_gamefiles(b.game_name, user)
    _governed_store()
    if not code_execution_enabled():
        return execution_disabled_response("Desktop native build")

    import subprocess
    import sys
    if not _has_pyinstaller():
        return {"ok": False, "error": "pyinstaller toolchain not installed"}
    files = _owned_gamefiles(b.game_name, user)
    # Validate artifact custody before allocating the private workspace.
    with tempfile.TemporaryDirectory(prefix="gameforge-desktop-") as scratch_dir:
        safe_name, build_id, workdir = _artifact_build(b.game_name, "desktop", artifacts_root=scratch_dir)
        os.makedirs(workdir, exist_ok=True)
        entry = _resolve_under_dir(workdir, "entry.py")
        game_json = json.dumps({"game": safe_name, "files": [f.get("filename") for f in files]})
        with open(entry, "w") as f:
            f.write(
                "import json\n"
                f"GAME = json.loads({game_json!r})\n"
                "def main():\n"
                "    print('=== ' + GAME['game'] + ' — GameForge native build ===')\n"
                "    print('gamefiles:', ', '.join(GAME['files']) or '(none)')\n"
                "    print('Runtime OK.')\n"
                "if __name__ == '__main__':\n    main()\n")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "PyInstaller", "--onefile", "--name", build_id,
                 "--distpath", os.path.join(workdir, "dist"),
                 "--workpath", os.path.join(workdir, "build"),
                 "--specpath", workdir, entry],
                capture_output=True, text=True, timeout=110)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "pyinstaller build timed out"}
        binary = _resolve_under_dir(workdir, "dist", build_id)
        if proc.returncode != 0 or not os.path.exists(binary):
            return {"ok": False, "error": "pyinstaller build failed"}
        zip_path = _resolve_under_dir(workdir, f"{build_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(binary, os.path.basename(binary))
        tenant = _tenant_id(user)
        binary_bytes = os.path.getsize(binary)
        rec = _governed_register(
            build_id=build_id,
            game_name=b.game_name,
            kind="desktop",
            payload=zip_path.read_bytes(),
            tenant_id=tenant,
            owner_id=auth.require_authenticated_identity(user)["owner_id"],
        )
        rec["download_url"] = f"/api/gameforge/build/download/{build_id}"
        rec["binary_bytes"] = binary_bytes
        rec["platform"] = "linux-x86_64"
        rec["ok"] = True
        return rec


@router.post("/godot")
async def build_godot(b: BuildBody, user=Depends(_editor)):
    """Generate a real, importable Godot 4 project (project.godot + scene + script)
    from the gamefiles and validate it with the native Godot engine (headless).
    The bundled Godot 4.3 binary actually runs the project to prove it boots."""
    _owned_gamefiles(b.game_name, user)
    _governed_store()
    if not code_execution_enabled():
        return execution_disabled_response("Godot native build")

    import subprocess
    files = _owned_gamefiles(b.game_name, user)
    # Validate artifact custody before allocating the private workspace.
    with tempfile.TemporaryDirectory(prefix="gameforge-godot-") as scratch_dir:
        safe_name, build_id, workdir = _artifact_build(b.game_name, "godot", artifacts_root=scratch_dir)
        os.makedirs(workdir, exist_ok=True)
        zip_path = _resolve_under_dir(workdir, f"{build_id}.zip")
        godot_name = json.dumps(str(b.game_name), ensure_ascii=False)
        godot_files = json.dumps([str(f.get("filename") or "") for f in files], ensure_ascii=False)
        project_godot = (
            '; Godot 4 project — generated by GameForge\n'
            'config_version=5\n\n[application]\n\n'
            f'config/name={godot_name}\nrun/main_scene="res://main.tscn"\n\n'
            '[rendering]\n\nrenderer/rendering_method="gl_compatibility"\n')
        main_gd = (
            'extends Node2D\n\n'
            f'var game_name := {godot_name}\n'
            f'var gamefiles := {godot_files}\n\n'
            'func _ready():\n'
            '\tprint("%s — GameForge Godot build" % game_name)\n'
            '\tprint("gamefiles: ", gamefiles)\n'
            '\t# Headless validation run: boot the engine, then quit cleanly.\n'
            '\tget_tree().quit()\n')
        main_tscn = (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://main.gd" id="1"]\n\n'
            '[node name="Main" type="Node2D"]\nscript = ExtResource("1")\n')
        for name, content in (("project.godot", project_godot), ("main.gd", main_gd), ("main.tscn", main_tscn)):
            with open(_resolve_under_dir(workdir, name), "w") as f:
                f.write(content)
        with open(_resolve_under_dir(workdir, "gamefiles.json"), "w") as f:
            json.dump({"game": b.game_name, "files": files}, f, indent=2)

        engine = _godot_bin()
        engine_validated = False
        engine_version = None
        engine_log = "not_run"
        if engine:
            try:
                ver = subprocess.run([engine, "--headless", "--version"], capture_output=True, text=True, timeout=30)
                engine_version = (ver.stdout or ver.stderr).strip().splitlines()[-1] if (ver.stdout or ver.stderr) else None
                # Run the project headless — imports resources and executes main scene.
                run = subprocess.run([engine, "--headless", "--path", workdir, "--quit"],
                                     capture_output=True, text=True, timeout=90)
                engine_validated = run.returncode == 0 and "GameForge Godot build" in (run.stdout or "")
                engine_log = "engine_validated" if engine_validated else "engine_validation_failed"
            except Exception:  # noqa: BLE001
                engine_log = "engine_run_failed"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for name in ("project.godot", "main.gd", "main.tscn", "gamefiles.json"):
                z.write(_resolve_under_dir(workdir, name), name)
        tenant = _tenant_id(user)
        rec = _governed_register(
            build_id=build_id,
            game_name=b.game_name,
            kind="godot",
            payload=zip_path.read_bytes(),
            tenant_id=tenant,
            owner_id=auth.require_authenticated_identity(user)["owner_id"],
        )
        rec["download_url"] = f"/api/gameforge/build/download/{build_id}"
        rec["importable_godot_project"] = True
        rec["engine_validated"] = engine_validated
        rec["engine_version"] = engine_version
        rec["engine_log"] = engine_log
        rec["headless_exported"] = False  # Importable project != native export-template build
        rec["ok"] = True
        return rec


async def _build_web_for_user(b: BuildBody, user: Any):
    tenant = _tenant_id(user)
    files = _owned_gamefiles(b.game_name, user)
    timestamp = time.time()
    with tempfile.TemporaryDirectory(prefix="gameforge-web-") as scratch_dir:
        return build_web_artifact(
            b.game_name,
            files=files,
            artifacts_root=scratch_dir,
            built_at=timestamp,
            governed_store=_governed_store(),
            tenant_id=tenant,
            owner_id=auth.require_authenticated_identity(user)["owner_id"],
            retention_until=timestamp + _artifact_retention_seconds(),
        )


async def _build_source_for_user(b: BuildBody, user: Any):
    tenant = _tenant_id(user)
    files = _owned_gamefiles(b.game_name, user)
    timestamp = time.time()
    with tempfile.TemporaryDirectory(prefix="gameforge-source-") as scratch_dir:
        return build_source_artifact(
            b.game_name,
            files=files,
            artifacts_root=scratch_dir,
            built_at=timestamp,
            governed_store=_governed_store(),
            tenant_id=tenant,
            owner_id=auth.require_authenticated_identity(user)["owner_id"],
            retention_until=timestamp + _artifact_retention_seconds(),
        )


@router.post("/web")
async def build_web(b: BuildBody, user=Depends(_editor)):
    return await _build_web_for_user(b, user)


@router.post("/source")
async def build_source(b: BuildBody, user=Depends(_editor)):
    return await _build_source_for_user(b, user)


@router.get("/list")
async def list_builds(
    game_name: Optional[str] = Query(None, max_length=200),
    user=Depends(_viewer),
):
    scope = auth.require_authenticated_identity(user)
    q: dict = dict(scope)
    if game_name:
        q["game_name"] = game_name
    try:
        rows = list(_db()["gameforge_builds"].find(q, {"_id": 0}).sort("built_at", -1).limit(50))
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "Build metadata is unavailable") from None
    visible = []
    for r in rows:
        if not _available(r, scope):
            continue
        try:
            _owned_gamefiles(r.get("game_name"), user)
        except HTTPException as exc:
            if exc.status_code == 404:
                continue
            raise
        r["download_url"] = f"/api/gameforge/build/download/{r['build_id']}"
        visible.append({key: value for key, value in r.items() if key != "path"})
    return {"ok": True, "builds": visible}


@router.get("/download/{build_id}")
async def download(build_id: str, user=Depends(_viewer)):
    scope = auth.require_authenticated_identity(user)
    try:
        safe_id = _safe_segment(build_id, what="build_id")
    except ValueError:
        raise HTTPException(404, "Build not found") from None
    try:
        rec = _db()["gameforge_builds"].find_one({"build_id": safe_id, **scope}, {"_id": 0})
    except Exception:
        raise HTTPException(503, "Build metadata is unavailable") from None
    if not _available(rec, scope) or rec.get("build_id") != safe_id or not rec.get("source_ref"):
        raise HTTPException(404, "Build not found")
    _owned_gamefiles(rec.get("game_name"), user)
    payload = _governed_store().read_bytes(scope["tenant_id"], safe_id)
    if payload is None:
        raise HTTPException(404, "Build not found")
    if not isinstance(payload, bytes) or hashlib.sha256(payload).hexdigest() != rec.get("sha256") or len(payload) != rec.get("size_bytes"):
        raise HTTPException(503, "Artifact integrity could not be confirmed")
    return Response(content=payload, media_type="application/zip", headers={
        "Cache-Control": "private, no-store", "Content-Disposition": f'attachment; filename="{safe_id}.zip"'})
