"""Deterministic, untrusted-input-safe offline game source archives.

This build-plane package is explicitly unsigned; it is not an installer or
release certificate. No archive member is ever extracted to the filesystem.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import re
import stat
from typing import Mapping
import zipfile

from skeleton.game.build.flgb_build_runtime import BuildContractError, PackageManifest, dig, req_id

MAX_FILES = 128
MAX_MEMBER = 1_048_576
MAX_TOTAL = 8_388_608
MAX_ARCHIVE = 10_000_000
MAX_MANIFEST = 131_072
FILE_NAME = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+){0,7}$")
ALLOWED_LICENSES = ("CC0-1.0", "CC-BY-4.0")


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BuildContractError("invalid canonical package JSON") from exc


def _path(name: object) -> str:
    if (not isinstance(name, str) or len(name.encode("utf-8")) > 240
        or not FILE_NAME.fullmatch(name) or any(segment in (".", "..") for segment in name.split("/"))
        or name == "manifest.json"):
        raise BuildContractError("unsafe or reserved archive path")
    return name


def _source(files: Mapping[str, bytes]) -> list[dict]:
    if not isinstance(files, Mapping) or not 1 <= len(files) <= MAX_FILES:
        raise BuildContractError("invalid package file count")
    entries = []
    total = 0
    for path, payload in files.items():
        name = _path(path)
        if not isinstance(payload, bytes) or len(payload) > MAX_MEMBER:
            raise BuildContractError("invalid package member")
        total += len(payload)
        if total > MAX_TOTAL:
            raise BuildContractError("package uncompressed budget exceeded")
        entries.append({"path": name, "sha256": sha256(payload).hexdigest(), "bytes": len(payload)})
    return sorted(entries, key=lambda entry: entry["path"])


def _manifest(package_id: str, author: str, license: str, entries: list[dict]) -> dict:
    req_id(package_id, "package_id")
    req_id(author, "author")
    if license not in ALLOWED_LICENSES:
        raise BuildContractError("unverified or unsupported source license")
    build_graph_digest = dig(entries)
    entry_digests = tuple(dig(entry) for entry in entries)
    package = PackageManifest(package_id, "1", entry_digests, build_graph_digest, None)
    return {
        "schema_version": 1, "package_id": package_id, "author": author,
        "license": license, "unsigned": True, "build_graph_digest": build_graph_digest,
        "package_digest": package.digest, "entries": entries,
    }


def _zip_entry(name: str, data: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.flag_bits = 0
    return info, data


def build_package(package_id: str, author: str, license: str, files: Mapping[str, bytes]) -> bytes:
    """Build a byte-identical, content-addressed, unsigned portable ZIP."""

    entries = _source(files)
    manifest = _manifest(package_id, author, license, entries)
    manifest_bytes = _canonical(manifest)
    if len(manifest_bytes) > MAX_MANIFEST:
        raise BuildContractError("manifest budget exceeded")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=False) as archive:
        archive.writestr(*_zip_entry("manifest.json", manifest_bytes))
        for entry in entries:
            archive.writestr(*_zip_entry(entry["path"], files[entry["path"]]))
    result = output.getvalue()
    if len(result) > MAX_ARCHIVE:
        raise BuildContractError("archive byte budget exceeded")
    return result


def verify_package(payload: bytes) -> dict:
    """Validate all ZIP members and source identities without extraction."""

    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_ARCHIVE:
        raise BuildContractError("invalid archive size")
    try:
        with zipfile.ZipFile(BytesIO(payload), "r", allowZip64=False) as archive:
            members = archive.infolist()
            if not 2 <= len(members) <= MAX_FILES + 1:
                raise BuildContractError("invalid archive member count")
            names = [info.filename for info in members]
            if names[0] != "manifest.json" or len(set(names)) != len(names):
                raise BuildContractError("missing manifest or duplicate member")
            total = 0
            for info in members:
                if info.filename != "manifest.json":
                    _path(info.filename)
                if (info.is_dir() or info.flag_bits & 1 or info.compress_type != zipfile.ZIP_STORED
                    or info.file_size > (MAX_MANIFEST if info.filename == "manifest.json" else MAX_MEMBER)
                    or info.compress_size != info.file_size):
                    raise BuildContractError("unsupported or unsafe archive member")
                mode = info.external_attr >> 16
                if stat.S_IFMT(mode) != stat.S_IFREG:
                    raise BuildContractError("nonregular archive member")
                total += info.file_size
                if total > MAX_TOTAL + MAX_MANIFEST:
                    raise BuildContractError("archive extraction budget exceeded")
            raw_manifest = archive.read("manifest.json")
            if len(raw_manifest) > MAX_MANIFEST:
                raise BuildContractError("manifest budget exceeded")
            manifest = json.loads(raw_manifest)
            if not isinstance(manifest, dict) or set(manifest) != {
                "schema_version", "package_id", "author", "license", "unsigned",
                "build_graph_digest", "package_digest", "entries",
            }:
                raise BuildContractError("invalid manifest fields")
            if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
                raise BuildContractError("unsupported package schema")
            if manifest["unsigned"] is not True:
                raise BuildContractError("false signature claim")
            if _canonical(manifest) != raw_manifest:
                raise BuildContractError("noncanonical manifest")
            entries = manifest["entries"]
            if not isinstance(entries, list) or len(entries) != len(members) - 1:
                raise BuildContractError("entry inventory mismatch")
            if [entry["path"] for entry in entries if isinstance(entry, dict) and "path" in entry] != names[1:]:
                raise BuildContractError("member ordering or inventory mismatch")
            files = {}
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes"}:
                    raise BuildContractError("invalid entry fields")
                name = _path(entry["path"])
                if type(entry["bytes"]) is not int or not 0 <= entry["bytes"] <= MAX_MEMBER:
                    raise BuildContractError("invalid entry size")
                data = archive.read(name)
                if len(data) != entry["bytes"] or sha256(data).hexdigest() != entry["sha256"]:
                    raise BuildContractError("member content mismatch")
                files[name] = data
            if _source(files) != entries:
                raise BuildContractError("noncanonical entries")
            expected = _manifest(manifest["package_id"], manifest["author"], manifest["license"], entries)
            if manifest != expected:
                raise BuildContractError("package manifest integrity mismatch")
            if build_package(manifest["package_id"], manifest["author"],
                             manifest["license"], files) != payload:
                raise BuildContractError("noncanonical archive representation")
            return {
                "ok": True, "package_id": manifest["package_id"],
                "package_digest": manifest["package_digest"],
                "archive_sha256": sha256(payload).hexdigest(),
                "files": len(entries), "source_bytes": sum(entry["bytes"] for entry in entries),
                "unsigned": True, "release_certified": False,
            }
    except (zipfile.BadZipFile, RuntimeError, UnicodeDecodeError, json.JSONDecodeError,
            KeyError, TypeError, ValueError, OverflowError) as exc:
        raise BuildContractError("malformed or unsafe package") from exc
