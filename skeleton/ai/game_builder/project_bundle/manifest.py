"""Bundle manifest: identity, file digests, save schema and receipt seal."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from skeleton.kernel.game_save_plane import SAVE_SCHEMA_VERSION, content_digest

BUNDLE_SCHEMA_VERSION = 1
BUNDLE_SCHEMA = "skeleton.game_builder.project_bundle.v1"
_IDENT = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")


class BundleError(ValueError):
    """A project bundle failed validation, integrity or compatibility checks."""


@dataclass(frozen=True, slots=True)
class BundleFile:
    path: str
    sha256: str
    bytes: int

    def payload(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes}


@dataclass(frozen=True, slots=True)
class BundleManifest:
    project_id: str
    genre: str
    files: tuple[BundleFile, ...]
    receipt_root: str
    sequence: int
    label: str | None = None
    save_schema_version: int = SAVE_SCHEMA_VERSION
    bundle_schema_version: int = BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("project_id", "genre"):
            if not _IDENT.fullmatch(getattr(self, name) or ""):
                raise BundleError(f"{name} must be a safe identifier")
        if not _SHA.fullmatch(self.receipt_root):
            raise BundleError("receipt_root must be a sha256 hex digest")
        paths = [f.path for f in self.files]
        if paths != sorted(set(paths)):
            raise BundleError("manifest files must be unique and sorted by path")
        for f in self.files:
            if not _SHA.fullmatch(f.sha256) or f.bytes < 0:
                raise BundleError("manifest file entry malformed")
        if self.bundle_schema_version > BUNDLE_SCHEMA_VERSION:
            raise BundleError("bundle schema is newer than this runtime")
        if self.label is not None and not (isinstance(self.label, str) and 1 <= len(self.label) <= 80):
            raise BundleError("label must be 1..80 characters")

    def body(self) -> dict[str, Any]:
        return {
            "schema": BUNDLE_SCHEMA,
            "bundle_schema_version": self.bundle_schema_version,
            "save_schema_version": self.save_schema_version,
            "project_id": self.project_id,
            "genre": self.genre,
            "sequence": self.sequence,
            "label": self.label,
            "receipt_root": self.receipt_root,
            "files": [f.payload() for f in self.files],
        }

    @property
    def content_digest(self) -> str:
        return content_digest(self.body())

    def file_map(self) -> dict[str, str]:
        return {f.path: f.sha256 for f in self.files}

    def payload(self) -> dict[str, Any]:
        return {**self.body(), "content_digest": self.content_digest}

    @classmethod
    def from_payload(cls, data: Mapping[str, Any]) -> "BundleManifest":
        try:
            if data["schema"] != BUNDLE_SCHEMA:
                raise BundleError("not a project bundle manifest")
            m = cls(
                project_id=data["project_id"], genre=data["genre"],
                files=tuple(BundleFile(f["path"], f["sha256"], int(f["bytes"])) for f in data["files"]),
                receipt_root=data["receipt_root"], sequence=int(data["sequence"]),
                label=data.get("label"), save_schema_version=int(data["save_schema_version"]),
                bundle_schema_version=int(data["bundle_schema_version"]),
            )
        except (KeyError, TypeError) as exc:
            raise BundleError("malformed bundle manifest") from exc
        if "content_digest" in data and data["content_digest"] != m.content_digest:
            raise BundleError("manifest content_digest mismatch")
        return m


__all__ = ["BUNDLE_SCHEMA", "BUNDLE_SCHEMA_VERSION", "BundleError", "BundleFile", "BundleManifest"]
