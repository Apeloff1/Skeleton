"""Export provenance manifests.

After a certified export, record what was built, from what, by which engine:
sha256 of every artifact, the project tree digest, the git head, the Godot
version line and the certification verdict. Manifests are deterministic JSON
so two runs over identical inputs produce byte-identical output, and
:func:`verify` re-hashes artifacts to detect tampering or stale builds.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .project import IGNORED_DIRS

SCHEMA = "skeleton.godot_export.provenance/v1"
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
MAX_SOURCE_FILES = 100_000
MAX_SOURCE_BYTES = 4 * 1024 * 1024 * 1024


def _relative(path: str) -> tuple[str, ...]:
    """Reject non-canonical and platform-ambiguous manifest paths."""
    if (not isinstance(path, str) or not path or len(path) > 2048
            or "\\" in path or "\x00" in path):
        raise ValueError("invalid artifact path")
    parts = PurePosixPath(path)
    if (parts.is_absolute() or parts.as_posix() != path
            or any(part in ("", ".", "..") or ":" in part for part in parts.parts)):
        raise ValueError("artifact path escapes or is non-canonical")
    return parts.parts


def _digest_beneath(root: Path, relative: str) -> tuple[str, int]:
    """Descriptor-relative, no-follow read; never dereference a manifest symlink."""
    parts = _relative(relative)
    if not all(hasattr(os, k) for k in ("O_NOFOLLOW", "O_DIRECTORY")) or os.name != "posix":
        raise ValueError("secure artifact verification unavailable on this host")
    dflags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fflags = os.O_RDONLY | os.O_NOFOLLOW
    fd = os.open(root, dflags)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, dflags, dir_fd=fd)
            os.close(fd)
            fd = nxt
        file_fd = os.open(parts[-1], fflags, dir_fd=fd)
    finally:
        os.close(fd)
    try:
        before = os.fstat(file_fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > MAX_ARTIFACT_BYTES):
            raise ValueError("artifact is not an allowed bounded regular file")
        digest = hashlib.sha256()
        size = 0
        while True:
            data = os.read(file_fd, min(1024 * 1024, MAX_ARTIFACT_BYTES + 1 - size))
            if not data:
                break
            size += len(data)
            if size > MAX_ARTIFACT_BYTES:
                raise ValueError("artifact exceeds bound")
            digest.update(data)
        after = os.fstat(file_fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or size != before.st_size:
            raise ValueError("artifact changed during digest")
        return digest.hexdigest(), size
    finally:
        os.close(file_fd)


def tree_digest(root: Path) -> str:
    """Order-independent bounded source digest; refuse linked and special files."""
    root = Path(root)
    h = hashlib.sha256()
    count = total = 0
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if p.is_symlink():
            raise ValueError("linked project source cannot be certified")
        if p.is_dir():
            continue
        if not p.is_file():
            raise ValueError("special project source cannot be certified")
        count += 1
        if count > MAX_SOURCE_FILES:
            raise ValueError("source file budget exceeded")
        digest, size = _digest_beneath(root, rel.as_posix())
        total += size
        if total > MAX_SOURCE_BYTES:
            raise ValueError("source size budget exceeded")
        h.update(rel.as_posix().encode() + b"\0" + digest.encode() + b"\n")
    return h.hexdigest()


def git_head(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and len(out) == 40 else None


@dataclass(frozen=True)
class Artifact:
    preset: str
    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        if not isinstance(self.preset, str) or not 1 <= len(self.preset) <= 256:
            raise ValueError("invalid artifact preset")
        _relative(self.path)
        if (not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in self.sha256)):
            raise ValueError("invalid artifact sha256")
        if type(self.size) is not int or not 0 <= self.size <= MAX_ARTIFACT_BYTES:
            raise ValueError("invalid artifact size")


@dataclass
class Manifest:
    project: str
    tree: str
    engine: str
    verdict: str
    git: str | None = None
    artifacts: list[Artifact] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.project, str) or not 1 <= len(self.project) <= 256:
            raise ValueError("invalid project identity")
        if not isinstance(self.engine, str) or not 1 <= len(self.engine) <= 256:
            raise ValueError("invalid engine identity")
        if not isinstance(self.tree, str) or len(self.tree) != 64 or any(
                c not in "0123456789abcdef" for c in self.tree):
            raise ValueError("invalid project source tree digest")
        if self.verdict not in ("SHIP", "NO-SHIP"):
            raise ValueError("invalid certification verdict")
        if self.git is not None and (not isinstance(self.git, str) or len(self.git) != 40
                or any(c not in "0123456789abcdef" for c in self.git)):
            raise ValueError("invalid git source pin")
        if not isinstance(self.artifacts, list) or len(self.artifacts) > 1024:
            raise ValueError("invalid artifact inventory")
        if any(not isinstance(a, Artifact) for a in self.artifacts):
            raise ValueError("untyped artifact")
        ids = [(a.preset, a.path) for a in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate artifact inventory entry")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {"schema": SCHEMA, "project": self.project, "tree": self.tree, "engine": self.engine,
                "verdict": self.verdict, "git": self.git,
                "artifacts": [a.__dict__ for a in sorted(self.artifacts, key=lambda a: (a.preset, a.path))]}

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=1, sort_keys=True) + "\n"

    @classmethod
    def loads(cls, text: str) -> "Manifest":
        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate provenance JSON key")
                result[key] = value
            return result

        d = json.loads(text, object_pairs_hook=no_duplicates,
                       parse_constant=lambda value: (_ for _ in ()).throw(
                           ValueError("nonfinite provenance JSON")))
        if not isinstance(d, dict) or d.get("schema") != SCHEMA:
            raise ValueError("unknown provenance schema")
        allowed = {"schema", "project", "tree", "engine", "verdict", "git", "artifacts"}
        if set(d) - allowed or not {"project", "tree", "engine", "verdict"}.issubset(d):
            raise ValueError("invalid provenance fields")
        artifacts = d.get("artifacts", [])
        if not isinstance(artifacts, list) or len(artifacts) > 1024:
            raise ValueError("invalid artifact inventory")
        expected = {"preset", "path", "sha256", "size"}
        if any(not isinstance(a, dict) or set(a) != expected for a in artifacts):
            raise ValueError("invalid artifact fields")
        return cls(d["project"], d["tree"], d["engine"], d["verdict"], d.get("git"),
                   [Artifact(**a) for a in artifacts])


def build(root: Path, engine: str, verdict: str, artifacts: dict[str, Path], base: Path | None = None) -> Manifest:
    root = Path(root)
    base = Path(base) if base is not None else root
    m = Manifest(root.name, tree_digest(root), engine, verdict, git_head(root))
    for preset, path in artifacts.items():
        try:
            rel = Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(base))).as_posix()
        except ValueError as exc:
            raise ValueError("artifact is outside approved base") from exc
        digest, size = _digest_beneath(base, rel)
        m.artifacts.append(Artifact(preset, rel, digest, size))
    m.__post_init__()
    return m


def verify(manifest: Manifest, base: Path, root: Path | None = None) -> list[str]:
    manifest.__post_init__()
    problems: list[str] = []
    for a in manifest.artifacts:
        try:
            digest, size = _digest_beneath(Path(base), a.path)
        except FileNotFoundError:
            problems.append(f"{a.preset}: missing {a.path}")
            continue
        except (OSError, ValueError):
            problems.append(f"{a.preset}: unsafe or unreadable {a.path}")
            continue
        if size != a.size:
            problems.append(f"{a.preset}: size mismatch for {a.path}")
        if digest != a.sha256:
            problems.append(f"{a.preset}: sha256 mismatch for {a.path}")
    if root is not None:
        try:
            same_tree = tree_digest(root) == manifest.tree
        except (OSError, ValueError):
            same_tree = False
        if not same_tree:
            problems.append("project tree changed since manifest")
    if manifest.verdict != "SHIP":
        problems.append(f"manifest verdict is {manifest.verdict}")
    if not manifest.artifacts and manifest.verdict == "SHIP":
        problems.append("no certified artifacts in manifest")
    return problems
