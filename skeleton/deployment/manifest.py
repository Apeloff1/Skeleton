"""Reproducible packaging manifest for self-hosted Skeleton installs.

A :class:`PackageManifest` pins exactly what a self-host install ships: every
file (path, size, SHA-256, executable bit), the project identity and
dependency pins from ``pyproject.toml``, the process entrypoints, and —
optionally — the redacted deployment profile with its fingerprint.

The file set defaults to the sources the production ``Dockerfile`` copies
into the image (parsed from its ``COPY`` instructions), so the manifest and
the container cannot silently drift. ``root_digest`` is a SHA-256 over the
sorted ``path\\0sha256`` records: two installs are byte-identical iff their
root digests match. :func:`verify_manifest` reports missing, modified and
unexpected files against a tree on disk.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shlex
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - requires-python >= 3.11
    tomllib = None  # type: ignore[assignment]

from .profile import SelfHostProfile

__all__ = [
    "DEFAULT_EXCLUDES",
    "FALLBACK_SOURCES",
    "MANIFEST_KIND",
    "MANIFEST_SCHEMA_VERSION",
    "FileEntry",
    "ManifestDiff",
    "ManifestError",
    "PackageManifest",
    "build_manifest",
    "dockerfile_copy_sources",
    "load_manifest",
    "verify_manifest",
    "write_manifest",
]

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_KIND = "skeleton_selfhost_package_manifest"
DEFAULT_EXCLUDES: Tuple[str, ...] = (
    "*/__pycache__/*",
    "__pycache__/*",
    "*.pyc",
    "*.pyo",
    "*/.pytest_cache/*",
    "*/.mypy_cache/*",
    "*/.ruff_cache/*",
    "*.DS_Store",
    "*.swp",
)
#: Used when no Dockerfile is present (e.g. an sdist without one).
FALLBACK_SOURCES: Tuple[str, ...] = ("pyproject.toml", "README.md", "skeleton")
ENTRYPOINTS: Dict[str, List[str]] = {
    "server": ["uvicorn", "skeleton.api.server:create_app", "--factory"],
    "cli": ["python", "-m", "skeleton"],
    "boot": ["python", "-m", "skeleton", "deploy", "boot"],
}
_CHUNK = 1024 * 1024


class ManifestError(ValueError):
    """Raised for malformed manifests or unsafe manifest paths."""


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    sha256: str
    executable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256, "executable": self.executable}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FileEntry":
        path = _safe_relpath(str(data.get("path", "")))
        digest = str(data.get("sha256", ""))
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ManifestError(f"bad sha256 for {path!r}")
        size = data.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ManifestError(f"bad size for {path!r}")
        return cls(path=path, size=size, sha256=digest, executable=bool(data.get("executable", False)))


def _safe_relpath(path: str) -> str:
    """Normalize a manifest path and reject anything that could escape the root."""

    if not path or "\x00" in path or "\\" in path or "//" in path or path.endswith("/"):
        raise ManifestError(f"unsafe manifest path {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in ("..", "") for part in pure.parts) or path.startswith("./"):
        raise ManifestError(f"unsafe manifest path {path!r}")
    return pure.as_posix()


def _root_digest(files: Sequence[FileEntry]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(files, key=lambda item: item.path):
        digest.update(entry.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


@dataclass
class PackageManifest:
    name: str
    version: str
    requires_python: str
    dependencies: List[str]
    files: List[FileEntry]
    sources: List[str]
    entrypoints: Dict[str, List[str]] = field(default_factory=lambda: {k: list(v) for k, v in ENTRYPOINTS.items()})
    profile: Optional[Dict[str, Any]] = None
    git_sha: str = ""
    skipped: List[str] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for entry in self.files)

    @property
    def root_digest(self) -> str:
        return _root_digest(self.files)

    def file_map(self) -> Dict[str, FileEntry]:
        return {entry.path: entry for entry in self.files}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "kind": MANIFEST_KIND,
            "name": self.name,
            "version": self.version,
            "requires_python": self.requires_python,
            "dependencies": list(self.dependencies),
            "entrypoints": {k: list(v) for k, v in sorted(self.entrypoints.items())},
            "sources": list(self.sources),
            "git_sha": self.git_sha,
            "profile": self.profile,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "root_digest": self.root_digest,
            "skipped": list(self.skipped),
            "files": [entry.to_dict() for entry in sorted(self.files, key=lambda item: item.path)],
        }

    def to_json(self, *, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False) + ("\n" if indent else "")

    def summary(self) -> Dict[str, Any]:
        payload = self.to_dict()
        payload.pop("files")
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PackageManifest":
        if data.get("kind") != MANIFEST_KIND:
            raise ManifestError(f"not a {MANIFEST_KIND} document")
        if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise ManifestError(f"unsupported schema_version {data.get('schema_version')!r}")
        raw_files = data.get("files")
        if not isinstance(raw_files, list):
            raise ManifestError("files must be a list")
        files = [FileEntry.from_dict(item) for item in raw_files]
        paths = [entry.path for entry in files]
        if len(paths) != len(set(paths)):
            raise ManifestError("duplicate file paths in manifest")
        manifest = cls(
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            requires_python=str(data.get("requires_python", "")),
            dependencies=[str(item) for item in data.get("dependencies", [])],
            files=files,
            sources=[str(item) for item in data.get("sources", [])],
            entrypoints={str(k): [str(x) for x in v] for k, v in dict(data.get("entrypoints", {})).items()},
            profile=data.get("profile"),
            git_sha=str(data.get("git_sha", "")),
            skipped=[str(item) for item in data.get("skipped", [])],
        )
        declared = data.get("root_digest")
        if declared is not None and declared != manifest.root_digest:
            raise ManifestError("root_digest does not match the file list (manifest tampered or truncated)")
        return manifest


@dataclass
class ManifestDiff:
    missing: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    unexpected: List[str] = field(default_factory=list)
    mode_changed: List[str] = field(default_factory=list)
    expected_digest: str = ""
    actual_digest: str = ""

    @property
    def ok(self) -> bool:
        return not (self.missing or self.modified or self.unexpected)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "deployment_manifest_verification",
            "ok": self.ok,
            "expected_digest": self.expected_digest,
            "actual_digest": self.actual_digest,
            "missing": self.missing,
            "modified": self.modified,
            "unexpected": self.unexpected,
            "mode_changed": self.mode_changed,
        }


# ------------------------------------------------------------------ helpers
def dockerfile_copy_sources(text: str) -> List[str]:
    """Return the build-context sources of every ``COPY`` instruction.

    Handles line continuations, ``--chown``/``--chmod``/``--link`` flags and
    the JSON-array form; skips multi-stage ``--from=`` copies (those are not
    build-context files).
    """

    logical: List[str] = []
    buffer = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not buffer and line.lstrip().startswith("#"):
            continue
        if line.endswith("\\"):
            buffer += line[:-1] + " "
            continue
        logical.append(buffer + line)
        buffer = ""
    if buffer:
        logical.append(buffer)
    sources: List[str] = []
    for line in logical:
        stripped = line.strip()
        if not stripped.upper().startswith(("COPY ", "ADD ")):
            continue
        body = stripped.split(None, 1)[1] if " " in stripped else ""
        if body.lstrip().startswith("["):
            try:
                tokens = [str(item) for item in json.loads(body)]
            except json.JSONDecodeError:
                continue
        else:
            try:
                tokens = shlex.split(body)
            except ValueError:
                continue
        if any(token.startswith("--from=") for token in tokens):
            continue
        tokens = [token for token in tokens if not token.startswith("--")]
        if len(tokens) < 2:
            continue
        for source in tokens[:-1]:
            if "://" in source:
                continue
            normalized = source.strip().rstrip("/") or "."
            if normalized.startswith("./"):
                normalized = normalized[2:]
            if normalized not in sources:
                sources.append(normalized)
    return sources


def _excluded(relpath: str, excludes: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(relpath, pattern) for pattern in excludes)


def _hash_file(path: Path) -> Tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _iter_source_files(root: Path, sources: Sequence[str], excludes: Sequence[str],
                       skipped: List[str]) -> Iterator[Tuple[str, Path]]:
    resolved_root = root.resolve()
    seen: set[str] = set()
    for source in sources:
        relsource = _safe_relpath(source) if source != "." else "."
        base = root / relsource
        if base.is_symlink():
            skipped.append(f"{relsource} (symlink)")
            continue
        if base.is_file():
            candidates: Iterable[Path] = [base]
        elif base.is_dir():
            candidates = sorted(base.rglob("*"))
        else:
            skipped.append(f"{relsource} (missing)")
            continue
        for candidate in candidates:
            rel = candidate.relative_to(root).as_posix()
            if rel in seen or _excluded(rel, excludes):
                continue
            if candidate.is_symlink():
                skipped.append(f"{rel} (symlink)")
                continue
            if not candidate.is_file():
                continue
            if not str(candidate.resolve()).startswith(str(resolved_root) + os.sep):
                skipped.append(f"{rel} (outside root)")
                continue
            seen.add(rel)
            yield rel, candidate


def _read_pyproject(root: Path) -> Dict[str, Any]:
    path = root / "pyproject.toml"
    if tomllib is None or not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return dict(tomllib.load(handle).get("project", {}))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(f"cannot parse {path}: {exc}") from exc


def build_manifest(
    root: str | os.PathLike[str] = ".",
    *,
    sources: Optional[Sequence[str]] = None,
    excludes: Sequence[str] = DEFAULT_EXCLUDES,
    profile: Optional[SelfHostProfile] = None,
    git_sha: str = "",
) -> PackageManifest:
    """Hash the install file set under ``root``.

    ``sources`` defaults to the ``Dockerfile`` ``COPY`` sources, falling back
    to :data:`FALLBACK_SOURCES` when no Dockerfile exists.
    """

    root_path = Path(root)
    if not root_path.is_dir():
        raise ManifestError(f"{root_path} is not a directory")
    if sources is None:
        dockerfile = root_path / "Dockerfile"
        if dockerfile.is_file():
            sources = dockerfile_copy_sources(dockerfile.read_text(encoding="utf-8")) or list(FALLBACK_SOURCES)
        else:
            sources = list(FALLBACK_SOURCES)
    skipped: List[str] = []
    files: List[FileEntry] = []
    for rel, path in _iter_source_files(root_path, list(sources), excludes, skipped):
        sha, size = _hash_file(path)
        mode = path.stat().st_mode
        files.append(FileEntry(rel, size, sha, bool(mode & stat.S_IXUSR)))
    project = _read_pyproject(root_path)
    profile_payload = None
    if profile is not None:
        profile_payload = {"fingerprint": profile.fingerprint(), **profile.to_dict(redact=True)}
    return PackageManifest(
        name=str(project.get("name", "skeleton")),
        version=str(project.get("version", "")),
        requires_python=str(project.get("requires-python", "")),
        dependencies=[str(item) for item in project.get("dependencies", [])],
        files=files,
        sources=list(sources),
        profile=profile_payload,
        git_sha=git_sha,
        skipped=skipped,
    )


def verify_manifest(
    manifest: PackageManifest,
    root: str | os.PathLike[str] = ".",
    *,
    excludes: Sequence[str] = DEFAULT_EXCLUDES,
) -> ManifestDiff:
    """Compare ``manifest`` against the tree under ``root``."""

    root_path = Path(root)
    actual = build_manifest(root_path, sources=manifest.sources, excludes=excludes)
    expected_map = manifest.file_map()
    actual_map = actual.file_map()
    diff = ManifestDiff(expected_digest=manifest.root_digest, actual_digest=actual.root_digest)
    for path, entry in sorted(expected_map.items()):
        found = actual_map.get(path)
        if found is None:
            diff.missing.append(path)
        elif found.sha256 != entry.sha256 or found.size != entry.size:
            diff.modified.append(path)
        elif found.executable != entry.executable:
            diff.mode_changed.append(path)
    diff.unexpected = sorted(set(actual_map) - set(expected_map))
    return diff


def write_manifest(manifest: PackageManifest, path: str | os.PathLike[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(manifest.to_json())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def load_manifest(path: str | os.PathLike[str]) -> PackageManifest:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")
    return PackageManifest.from_dict(data)
