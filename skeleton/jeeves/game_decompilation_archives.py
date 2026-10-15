"""Safe in-memory ZIP game-project resource inventory, not executable unpacking.

All members are CRC-checked by zipfile, with bounded uncompressed sizes,
path/symlink rejection and duplicate/name collision protection. Captured PNG
and PCM measurements are structural, never copyrighted asset promotion.
"""
from __future__ import annotations

import hashlib
import io
import stat
import zipfile
from pathlib import PurePosixPath
from typing import Any

from .game_console_assets import decode_png, decode_pcm_wav

MAX_ZIP_FILES = 96
MAX_TOTAL_INFLATED = 16 * 1024 * 1024
MAX_MEMBER = 1024 * 1024
MAX_INFLATION_RATIO = 128


def _safe_member(info: zipfile.ZipInfo) -> str:
    path = info.filename
    if (not path or len(path) > 240 or "\\" in path or "\x00" in path
        or path.startswith("/") or path.startswith(".")
        or ":" in path or "//" in path):
        raise ValueError("Archive member has an unsafe or noncanonical path")
    parts = PurePosixPath(path).parts
    if not parts or len(parts) > 16 or any(part in {".", ".."} or part.startswith(".") for part in parts):
        raise ValueError("Archive member includes hidden/traversing paths")
    mode = (info.external_attr >> 16) & 0xFFFF
    kind = stat.S_IFMT(mode)
    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise ValueError("Archive member is not an ordinary regular file/directory")
    return path


def analyze_zip_project(data: bytes) -> dict[str, Any]:
    if type(data) is not bytes or len(data) > MAX_TOTAL_INFLATED:
        raise ValueError("ZIP source exceeds bounded project scope")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("ZIP structure invalid") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_FILES:
            raise ValueError("ZIP archive exceeds per-project file bound")
        expected_total = 0
        seen: set[str] = set()
        for info in infos:
            name = _safe_member(info)
            casefold = name.casefold()
            if casefold in seen:
                raise ValueError("Archive duplicates a case-insensitive member name")
            seen.add(casefold)
            if info.is_dir():
                continue
            if (info.flag_bits & 1 or info.file_size > MAX_MEMBER
                or info.compress_size == 0 and info.file_size > 0
                or info.compress_size > 0 and info.file_size > info.compress_size * MAX_INFLATION_RATIO
                or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise ValueError("ZIP member is encrypted, oversized or dangerously compressed")
            expected_total += info.file_size
            if expected_total > MAX_TOTAL_INFLATED:
                raise ValueError("Inflated archive exceeds total resource budget")
        results = []
        for info in infos:
            if info.is_dir():
                continue
            name = _safe_member(info)
            try:
                contents = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile, EOFError, ValueError) as exc:
                raise ValueError("Archive member CRC/data could not be read") from exc
            if len(contents) != info.file_size:
                raise ValueError("Archive read size differs from validated central directory")
            result: dict[str, Any] = {
                "path": name, "bytes": len(contents),
                "sha256": hashlib.sha256(contents).hexdigest(),
                "resource_kind": "unknown_no_inference",
            }
            if contents.startswith(b"\x89PNG\r\n\x1a\n"):
                if len(contents) > MAX_MEMBER:
                    raise ValueError("PNG exceeds bounded graphic scope")
                w, h, rgba = decode_png(contents)
                result.update(resource_kind="exact_decoded_png", width=w, height=h,
                              rgba_sha256=hashlib.sha256(rgba).hexdigest(),
                              pixels=w * h, raw_pixels_exported=False)
            elif contents.startswith(b"RIFF") and contents[8:12] == b"WAVE":
                audio = decode_pcm_wav(contents)
                result.update(resource_kind="measured_pcm_wav",
                              duration_seconds=audio["duration_seconds"],
                              sample_rate=audio["sample_rate"],
                              channels=audio["channels"],
                              pcm_sha256=audio["pcm_sha256"],
                              raw_pcm_exported=False)
            elif contents.startswith(b"PK\x03\x04"):
                result["resource_kind"] = "nested_archive_not_opened"
            elif name.lower().endswith((".py", ".lua", ".cs", ".js", ".gd")):
                result["resource_kind"] = "source_code_opaque_not_executed"
            elif name.lower().endswith((".json", ".tmx", ".tsx", ".xml")):
                result["resource_kind"] = "project_metadata_opaque_not_executed"
            results.append(result)
        return {
            "schema_version": "skeleton.game.decompiled_zip_resources.v1",
            "format": "zip_game_project",
            "archive_sha256": hashlib.sha256(data).hexdigest(),
            "member_count": len(results),
            "total_inflated_bytes": expected_total,
            "resource_inventory": results,
            "archive_extracted_to_disk": False, "scripts_executed": False,
            "raw_game_assets_exported": False,
        }
