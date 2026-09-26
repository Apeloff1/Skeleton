"""Shared GameForge artifact builder for HTTP and governed product execution.

This module owns the real web/source ZIP build path without importing FastAPI.
It keeps build output rooted under the backend artifact directory, sanitizes
archive member names, escapes generated HTML, and supports deterministic build
tokens for replay-safe governed operations.
"""
from __future__ import annotations

from html import escape
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import zipfile
from typing import Any, Iterable, Protocol


class ArtifactUsageMeter(Protocol):
    """Structural metering contract; backend stays independent of Skeleton imports."""

    def meter_artifact(
        self,
        operation_id: str,
        artifact_id: str,
        write_id: str,
        byte_count: int,
        *,
        now_wall: float | None = None,
    ) -> Any:
        ...


class GovernedArtifactStore(Protocol):
    """Structural lifecycle store contract; avoids a hard backend->Skeleton import."""

    def write_bytes(
        self,
        *,
        tenant_id: str,
        artifact_id: str,
        payload: bytes,
        data_class: str = "internal",
        purposes: tuple[str, ...] = ("artifact-delivery",),
        created_at: float | None = None,
        retention_until: float | None = None,
        exportable: bool = True,
    ) -> Any:
        ...

    def read_bytes(
        self,
        tenant_id: str,
        artifact_id: str,
    ) -> bytes | None:
        ...


DEFAULT_ARTIFACTS_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "builds"

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _built_at(value: float | int | None) -> float:
    if value is None:
        return time.time()
    if isinstance(value, bool):
        raise ValueError("built_at must be a finite timestamp")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("built_at must be a finite timestamp") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError("built_at must be a finite non-negative timestamp")
    return parsed


def _zip_write(archive: zipfile.ZipFile, name: str, data: str | bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    payload = data.encode("utf-8") if isinstance(data, str) else data
    archive.writestr(info, payload)


def safe_segment(value: str, *, what: str = "path") -> str:
    """Reject path traversal and absolute path fragments."""

    normalized = str(value or "").strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or ".." in normalized
        or "/" in normalized
        or "\\" in normalized
        or normalized.startswith(("~", "/", "\\"))
        or "\x00" in normalized
    ):
        raise ValueError(f"invalid {what}: {value!r}")
    return normalized


def resolve_under_dir(root: str | os.PathLike[str], *parts: str) -> Path:
    root_path = Path(root).resolve()
    candidate = root_path.joinpath(*parts).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        raise ValueError("path escapes build sandbox")
    return candidate


def _build_token(value: str | None) -> str:
    if value is None:
        return str(time.time_ns())
    return safe_segment(value, what="build_token")[:160]


def artifact_build(
    game_name: str,
    kind: str,
    *,
    artifacts_root: str | os.PathLike[str] = DEFAULT_ARTIFACTS_ROOT,
    build_token: str | None = None,
) -> tuple[str, str, Path]:
    safe_name = safe_segment(str(game_name).replace(" ", "_"), what="game_name")
    safe_kind = safe_segment(kind, what="kind")
    build_id = f"{safe_name}-{safe_kind}-{_build_token(build_token)}"
    root = Path(artifacts_root)
    root.mkdir(parents=True, exist_ok=True)
    return safe_name, build_id, resolve_under_dir(root, build_id)


def database():
    from core.databases import get_sync_db

    return get_sync_db()


def gamefiles(game_name: str) -> list[dict[str, Any]]:
    try:
        return list(
            database()["gameforge_gamefiles"].find(
                {"game_name": game_name},
                {"_id": 0},
            )
        )
    except Exception:  # noqa: BLE001
        return []


def register_artifact(
    build_id: str,
    game_name: str,
    kind: str,
    path: str | os.PathLike[str] | None,
    *,
    artifacts_root: str | os.PathLike[str] = DEFAULT_ARTIFACTS_ROOT,
    built_at: float | int | None = None,
    canonical_record: Any | None = None,
) -> dict[str, Any]:
    if canonical_record is None:
        if path is None:
            raise ValueError("path is required for unmanaged artifacts")
        root = Path(artifacts_root).resolve()
        real = Path(path).resolve()
        if real != root and root not in real.parents:
            raise ValueError("path escapes artifacts sandbox")
        size = real.stat().st_size
        digest = hashlib.sha256(real.read_bytes()).hexdigest()
        filename = real.name
        path_value: str | None = str(real)
        source_ref = None
        governance_record_id = None
    else:
        size = int(canonical_record.size_bytes)
        digest = str(canonical_record.sha256)
        filename = f"{build_id}.zip"
        path_value = None
        source_ref = str(canonical_record.source_ref)
        governance_record_id = str(canonical_record.record_id)

    record: dict[str, Any] = {
        "build_id": build_id,
        "game_name": game_name,
        "kind": kind,
        "path": path_value,
        "filename": filename,
        "size_bytes": size,
        "sha256": digest,
        "built_at": _built_at(built_at),
    }
    if source_ref is not None:
        record["source_ref"] = source_ref
        record["governance_record_id"] = governance_record_id
    try:
        database()["gameforge_builds"].update_one(
            {"build_id": build_id},
            {"$set": dict(record)},
            upsert=True,
        )
    except Exception:  # noqa: BLE001
        pass
    return record


def _archive_member_name(value: Any, *, fallback: str) -> str:
    raw = str(value or "").replace("\\", "/").split("/")[-1].strip()
    if not raw or raw in {".", ".."} or "\x00" in raw:
        raw = fallback
    # Keep filenames human-readable while preventing nested/archive traversal.
    return raw[:240]


def _commit_metered_archive(
    pending_path: Path,
    final_path: Path,
    *,
    usage_meter: ArtifactUsageMeter | None,
    operation_id: str | None,
    artifact_id: str,
    write_id: str,
    governed_store: GovernedArtifactStore | None = None,
    tenant_id: str | None = None,
    data_class: str = "internal",
    purposes: tuple[str, ...] = ("artifact-delivery",),
    created_at: float | None = None,
    retention_until: float | None = None,
    exportable: bool = True,
) -> Any | None:
    if usage_meter is not None:
        operation = str(operation_id or "").strip()
        if not operation:
            raise ValueError(
                "operation_id is required when artifact usage metering is enabled"
            )
        usage_meter.meter_artifact(
            operation,
            artifact_id,
            write_id,
            pending_path.stat().st_size,
        )
    if governed_store is not None:
        tenant = str(tenant_id or "").strip()
        if not tenant:
            raise ValueError(
                "tenant_id is required when governed artifact storage is enabled"
            )
        return governed_store.write_bytes(
            tenant_id=tenant,
            artifact_id=artifact_id,
            payload=pending_path.read_bytes(),
            data_class=data_class,
            purposes=purposes,
            created_at=created_at,
            retention_until=retention_until,
            exportable=exportable,
        )
    os.replace(pending_path, final_path)
    return None


def _pending_archive_path(final_path: Path) -> Path:
    fd, raw = tempfile.mkstemp(
        prefix=final_path.name + ".",
        suffix=".pending",
        dir=final_path.parent,
    )
    os.close(fd)
    return Path(raw)


def _materialize_files(
    supplied: Iterable[dict[str, Any]] | None,
    game_name: str,
) -> list[dict[str, Any]]:
    if supplied is None:
        return gamefiles(game_name)
    files: list[dict[str, Any]] = []
    for index, item in enumerate(supplied):
        if not isinstance(item, dict):
            raise ValueError(f"gamefile {index} must be an object")
        files.append(dict(item))
    return files


def build_web_artifact(
    game_name: str,
    *,
    files: Iterable[dict[str, Any]] | None = None,
    artifacts_root: str | os.PathLike[str] = DEFAULT_ARTIFACTS_ROOT,
    build_token: str | None = None,
    built_at: float | int | None = None,
    usage_meter: ArtifactUsageMeter | None = None,
    operation_id: str | None = None,
    write_id: str | None = None,
    governed_store: GovernedArtifactStore | None = None,
    tenant_id: str | None = None,
    data_class: str = "internal",
    retention_until: float | None = None,
    exportable: bool = True,
) -> dict[str, Any]:
    source_files = _materialize_files(files, game_name)
    safe_name, build_id, workdir = artifact_build(
        game_name,
        "web",
        artifacts_root=artifacts_root,
        build_token=build_token,
    )
    workdir.mkdir(parents=True, exist_ok=True)

    timestamp = _built_at(built_at)
    payload = {"game": safe_name, "files": source_files, "built_at": timestamp}
    data_path = resolve_under_dir(workdir, "game_data.json")
    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    manifest = "".join(
        "<li><b>"
        + escape(str(item.get("filename", "?")))
        + "</b> — "
        + escape(str((item.get("metadata") or {}).get("kind", "artifact")))
        + "</li>"
        for item in source_files
    )
    display_name = escape(str(game_name))
    js_name = (
        json.dumps(str(game_name))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{display_name} — GameForge Build</title>
<style>body{{margin:0;font-family:system-ui;background:#0b1220;color:#e2e8f0}}
.wrap{{max-width:820px;margin:0 auto;padding:24px}}h1{{color:#22c55e}}
.card{{background:#111827;border-radius:14px;padding:16px;margin:12px 0}}
canvas{{width:100%;height:320px;background:#0f1830;border-radius:10px;display:block}}</style></head>
<body><div class="wrap"><h1>🎮 {display_name}</h1>
<div class="card"><canvas id="stage"></canvas></div>
<div class="card"><h3>Gamefiles ({len(source_files)})</h3><ul>{manifest or '<li>none yet</li>'}</ul></div>
<script>
const c=document.getElementById('stage'),x=c.getContext('2d');c.width=c.clientWidth;c.height=320;
let t=0;(function loop(){{x.fillStyle='#0f1830';x.fillRect(0,0,c.width,c.height);
x.fillStyle='#22c55e';const px=(c.width/2)+Math.cos(t/20)*120,py=(c.height/2)+Math.sin(t/15)*80;
x.beginPath();x.arc(px,py,18,0,7);x.fill();x.fillStyle='#3b82f6';x.font='16px system-ui';
x.fillText({js_name} + ' — web build running',20,30);t++;requestAnimationFrame(loop);}})();
fetch('game_data.json').then(r=>r.json()).then(d=>console.log('gamefiles',d));
</script></div></body></html>"""
    index_path = resolve_under_dir(workdir, "index.html")
    index_path.write_text(html, encoding="utf-8")

    zip_path = resolve_under_dir(artifacts_root, f"{build_id}.zip")
    pending_path = _pending_archive_path(zip_path)
    try:
        with zipfile.ZipFile(pending_path, "w", zipfile.ZIP_DEFLATED) as archive:
            _zip_write(archive, "index.html", index_path.read_bytes())
            _zip_write(archive, "game_data.json", data_path.read_bytes())
        canonical_record = _commit_metered_archive(
            pending_path,
            zip_path,
            usage_meter=usage_meter,
            operation_id=operation_id,
            artifact_id=build_id,
            write_id=write_id or build_id,
            governed_store=governed_store,
            tenant_id=tenant_id,
            data_class=data_class,
            purposes=("artifact-delivery", "download"),
            created_at=timestamp,
            retention_until=retention_until,
            exportable=exportable,
        )
    finally:
        pending_path.unlink(missing_ok=True)

    record = register_artifact(
        build_id,
        safe_name,
        "web",
        None if canonical_record is not None else zip_path,
        artifacts_root=artifacts_root,
        built_at=timestamp,
        canonical_record=canonical_record,
    )
    record["download_url"] = f"/api/gameforge/build/download/{build_id}"
    record["ok"] = True
    return record


def build_source_artifact(
    game_name: str,
    *,
    files: Iterable[dict[str, Any]] | None = None,
    artifacts_root: str | os.PathLike[str] = DEFAULT_ARTIFACTS_ROOT,
    build_token: str | None = None,
    built_at: float | int | None = None,
    usage_meter: ArtifactUsageMeter | None = None,
    operation_id: str | None = None,
    write_id: str | None = None,
    governed_store: GovernedArtifactStore | None = None,
    tenant_id: str | None = None,
    data_class: str = "internal",
    retention_until: float | None = None,
    exportable: bool = True,
) -> dict[str, Any]:
    source_files = _materialize_files(files, game_name)
    safe_name, build_id, _workdir = artifact_build(
        game_name,
        "src",
        artifacts_root=artifacts_root,
        build_token=build_token,
    )
    zip_path = resolve_under_dir(artifacts_root, f"{build_id}.zip")
    timestamp = _built_at(built_at)
    manifest = {
        "game": safe_name,
        "file_count": len(source_files),
        "built_at": timestamp,
        "files": [
            _archive_member_name(item.get("filename"), fallback=f"file-{index}.txt")
            for index, item in enumerate(source_files)
        ],
    }

    pending_path = _pending_archive_path(zip_path)
    try:
        with zipfile.ZipFile(pending_path, "w", zipfile.ZIP_DEFLATED) as archive:
            _zip_write(archive, "manifest.json", json.dumps(manifest, indent=2))
            used: set[str] = set()
            for index, item in enumerate(source_files):
                name = _archive_member_name(
                    item.get("filename"),
                    fallback=f"file-{index}.txt",
                )
                candidate = name
                suffix = 1
                while candidate in used:
                    stem, dot, extension = name.partition(".")
                    candidate = (
                        f"{stem}-{suffix}{dot}{extension}"
                        if dot
                        else f"{name}-{suffix}"
                    )
                    suffix += 1
                used.add(candidate)
                _zip_write(
                    archive,
                    f"gamefiles/{candidate}",
                    str(item.get("content", "")),
                )
        canonical_record = _commit_metered_archive(
            pending_path,
            zip_path,
            usage_meter=usage_meter,
            operation_id=operation_id,
            artifact_id=build_id,
            write_id=write_id or build_id,
            governed_store=governed_store,
            tenant_id=tenant_id,
            data_class=data_class,
            purposes=("artifact-delivery", "download"),
            created_at=timestamp,
            retention_until=retention_until,
            exportable=exportable,
        )
    finally:
        pending_path.unlink(missing_ok=True)

    record = register_artifact(
        build_id,
        safe_name,
        "source",
        None if canonical_record is not None else zip_path,
        artifacts_root=artifacts_root,
        built_at=timestamp,
        canonical_record=canonical_record,
    )
    record["download_url"] = f"/api/gameforge/build/download/{build_id}"
    record["ok"] = True
    return record
