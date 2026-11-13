"""Content-addressed artifact manifests for release packaging.

A manifest binds a release to an immutable source commit and lists every
artifact with its size and sha256 digest. The manifest digest is computed
over the canonical JSON body, so any change to an entry changes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from skeleton.build.delivery._util import (
    DeliveryError,
    canonical_json,
    normalize_relpath,
    require_id,
    require_non_negative_int,
    require_sha1,
    require_sha256,
    require_text,
    sha256_json,
)
from skeleton.build.delivery.version import Version

MANIFEST_SCHEMA = 1
MAX_ARTIFACTS = 2048
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024  # repository policy: no file over 50 MB
ARTIFACT_KINDS = frozenset({"wheel", "sdist", "tarball", "zip", "container-layer", "binary", "config", "sbom", "other"})


@dataclass(frozen=True)
class ArtifactEntry:
    path: str
    kind: str
    size: int
    sha256: str
    platform: str = "any"

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", normalize_relpath(self.path, field="artifact.path"))
        if self.kind not in ARTIFACT_KINDS:
            raise DeliveryError(f"unknown artifact kind {self.kind!r}")
        require_non_negative_int(self.size, field="artifact.size", maximum=MAX_ARTIFACT_BYTES)
        require_sha256(self.sha256, field="artifact.sha256")
        require_id(self.platform, field="artifact.platform")

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "kind": self.kind, "size": self.size, "sha256": self.sha256, "platform": self.platform}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactEntry":
        if not isinstance(data, Mapping):
            raise DeliveryError("artifact entry must be an object")
        extra = set(data) - {"path", "kind", "size", "sha256", "platform"}
        if extra:
            raise DeliveryError(f"unknown artifact fields: {sorted(extra)}")
        return cls(data.get("path"), data.get("kind"), data.get("size"), data.get("sha256"), data.get("platform", "any"))


@dataclass(frozen=True)
class ArtifactManifest:
    release_id: str
    version: str
    source_commit: str
    artifacts: tuple[ArtifactEntry, ...]
    metadata: tuple[tuple[str, str], ...] = field(default=())

    def __post_init__(self) -> None:
        require_id(self.release_id, field="release_id")
        Version.parse(self.version)
        require_sha1(self.source_commit, field="source_commit")
        if not self.artifacts:
            raise DeliveryError("manifest requires at least one artifact")
        if len(self.artifacts) > MAX_ARTIFACTS:
            raise DeliveryError("too many artifacts")
        ordered = tuple(sorted(self.artifacts, key=lambda a: a.path))
        paths = [a.path for a in ordered]
        if len(paths) != len(set(paths)):
            raise DeliveryError("duplicate artifact path")
        object.__setattr__(self, "artifacts", ordered)
        meta = tuple(sorted(dict(self.metadata).items()))
        for key, value in meta:
            require_id(key, field="metadata key")
            require_text(value, field=f"metadata[{key}]", maximum=512, allow_empty=True)
        object.__setattr__(self, "metadata", meta)

    @property
    def total_bytes(self) -> int:
        return sum(a.size for a in self.artifacts)

    def body(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "release_id": self.release_id,
            "version": self.version,
            "source_commit": self.source_commit,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "metadata": dict(self.metadata),
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.body())

    def to_dict(self) -> dict[str, Any]:
        body = self.body()
        body["digest"] = self.digest
        return body

    def serialize(self) -> str:
        return canonical_json(self.to_dict())

    def find(self, path: str) -> ArtifactEntry | None:
        norm = normalize_relpath(path)
        for entry in self.artifacts:
            if entry.path == norm:
                return entry
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, verify_digest: bool = True) -> "ArtifactManifest":
        if not isinstance(data, Mapping):
            raise DeliveryError("manifest must be an object")
        if data.get("schema") != MANIFEST_SCHEMA:
            raise DeliveryError("unsupported manifest schema")
        artifacts = data.get("artifacts")
        if not isinstance(artifacts, list):
            raise DeliveryError("artifacts must be a list")
        meta = data.get("metadata", {})
        if not isinstance(meta, Mapping):
            raise DeliveryError("metadata must be an object")
        manifest = cls(
            data.get("release_id"),
            data.get("version"),
            data.get("source_commit"),
            tuple(ArtifactEntry.from_dict(a) for a in artifacts),
            tuple(meta.items()),
        )
        if verify_digest:
            if data.get("digest") != manifest.digest:
                raise DeliveryError("manifest digest mismatch")
        return manifest


def build_manifest(
    *,
    release_id: str,
    version: str,
    source_commit: str,
    artifacts: Iterable[ArtifactEntry | Mapping[str, Any]],
    metadata: Mapping[str, str] | None = None,
) -> ArtifactManifest:
    entries = tuple(a if isinstance(a, ArtifactEntry) else ArtifactEntry.from_dict(a) for a in artifacts)
    return ArtifactManifest(release_id, version, source_commit, entries, tuple((metadata or {}).items()))


@dataclass(frozen=True)
class ManifestDiff:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def diff_manifests(old: ArtifactManifest, new: ArtifactManifest) -> ManifestDiff:
    old_map = {a.path: a for a in old.artifacts}
    new_map = {a.path: a for a in new.artifacts}
    added = tuple(sorted(set(new_map) - set(old_map)))
    removed = tuple(sorted(set(old_map) - set(new_map)))
    changed = tuple(sorted(p for p in set(old_map) & set(new_map) if old_map[p] != new_map[p]))
    return ManifestDiff(added, removed, changed)


def verify_files(manifest: ArtifactManifest, observed: Mapping[str, bytes]) -> tuple[str, ...]:
    """Return a sorted tuple of problems comparing ``observed`` file bytes to the manifest."""
    problems: list[str] = []
    from skeleton.build.delivery._util import sha256_bytes

    seen: set[str] = set()
    for raw_path, data in observed.items():
        path = normalize_relpath(raw_path)
        seen.add(path)
        entry = manifest.find(path)
        if entry is None:
            problems.append(f"unexpected:{path}")
            continue
        if len(data) != entry.size:
            problems.append(f"size:{path}")
        elif sha256_bytes(data) != entry.sha256:
            problems.append(f"digest:{path}")
    for entry in manifest.artifacts:
        if entry.path not in seen:
            problems.append(f"missing:{entry.path}")
    return tuple(sorted(problems))
