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
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .binary import sha256_file
from .project import IGNORED_DIRS

SCHEMA = "skeleton.godot_export.provenance/v1"


def _safe_relative(path: object) -> PurePosixPath:
    if type(path) is not str or not path or len(path) > 4096:
        raise ValueError("unsafe artifact path")
    if any(char in path for char in (chr(92), chr(0), ":")):
        raise ValueError("unsafe artifact path")
    parts = path.split("/")
    if len(parts) > 32 or any(part in ("", ".", "..") for part in parts):
        raise ValueError("unsafe artifact path")
    rel = PurePosixPath(path)
    if rel.is_absolute():
        raise ValueError("unsafe artifact path")
    return rel


def _has_symlink(root: Path, rel: PurePosixPath) -> bool:
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def tree_digest(root: Path) -> str:
    """Order-independent digest of project sources (path + content hash)."""
    h = hashlib.sha256()
    if root.is_symlink():
        raise ValueError("project source root is a symlink")
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if p.is_symlink():
            raise ValueError("project source contains a symlink")
        if not p.is_file():
            continue
        h.update(rel.as_posix().encode() + b"\0" + sha256_file(p).encode() + b"\n")
    return h.hexdigest()


def git_head(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and len(out) == 40 else None


@dataclass
class Artifact:
    preset: str
    path: str
    sha256: str
    size: int


@dataclass
class Manifest:
    project: str
    tree: str
    engine: str
    verdict: str
    git: str | None = None
    artifacts: list[Artifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "project": self.project, "tree": self.tree, "engine": self.engine,
                "verdict": self.verdict, "git": self.git,
                "artifacts": [a.__dict__ for a in sorted(self.artifacts, key=lambda a: (a.preset, a.path))]}

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=1, sort_keys=True) + "\n"

    @classmethod
    def loads(cls, text: str) -> "Manifest":
        if type(text) is not str or len(text.encode("utf-8")) > 8 * 1024 * 1024:
            raise ValueError("provenance manifest exceeds byte bound")
        try:
            d = json.loads(text)
        except (ValueError, RecursionError) as exc:
            raise ValueError("invalid provenance JSON") from exc
        if type(d) is not dict or d.get("schema") != SCHEMA:
            raise ValueError("unknown provenance schema")
        items = d.get("artifacts")
        if type(items) is not list or len(items) > 256:
            raise ValueError("provenance artifacts exceed bound")
        artifacts: list[Artifact] = []
        seen: set[str] = set()
        for item in items:
            if type(item) is not dict or set(item) != {"preset", "path", "sha256", "size"}:
                raise ValueError("provenance artifact shape invalid")
            rel = _safe_relative(item["path"]).as_posix()
            sha, size, preset = item["sha256"], item["size"], item["preset"]
            if (rel in seen or type(preset) is not str or not 1 <= len(preset) <= 128
                    or type(sha) is not str or len(sha) != 64
                    or any(ch not in "0123456789abcdef" for ch in sha)
                    or type(size) is not int or not 0 <= size <= 16 * 1024**3):
                raise ValueError("provenance artifact identity invalid or duplicated")
            seen.add(rel)
            artifacts.append(Artifact(preset, rel, sha, size))
        for name in ("project", "tree", "engine", "verdict"):
            if type(d.get(name)) is not str or not d[name]:
                raise ValueError("provenance metadata invalid")
        return cls(d["project"], d["tree"], d["engine"], d["verdict"], d.get("git"), artifacts)


def build(root: Path, engine: str, verdict: str, artifacts: dict[str, Path], base: Path | None = None) -> Manifest:
    base = base or root
    m = Manifest(root.name, tree_digest(root), engine, verdict, git_head(root))
    for preset, path in artifacts.items():
        if base.is_symlink() or path.is_symlink():
            raise ValueError("artifact path contains a symlink")
        try:
            rel = _safe_relative(path.absolute().relative_to(base.absolute()).as_posix())
        except ValueError as exc:
            raise ValueError("artifact path escapes base") from exc
        if _has_symlink(base.absolute(), rel):
            raise ValueError("artifact path contains a symlink")
        if path.resolve().relative_to(base.resolve()).as_posix() != rel.as_posix():
            raise ValueError("artifact path resolves to a different source")
        m.artifacts.append(Artifact(preset, rel.as_posix(), sha256_file(path), path.stat().st_size))
    return m


def verify(manifest: Manifest, base: Path, root: Path | None = None) -> list[str]:
    """Reject untrusted paths before reading artifact bytes."""
    problems: list[str] = []
    if base.is_symlink() or not base.is_dir():
        return ["artifact base root is unsafe or missing"]
    trusted_base = base.resolve()
    for a in manifest.artifacts:
        try:
            rel = _safe_relative(a.path)
        except ValueError:
            problems.append(f"{a.preset}: unsafe artifact path")
            continue
        if _has_symlink(trusted_base, rel):
            problems.append(f"{a.preset}: symlink artifact path refused")
            continue
        p = trusted_base.joinpath(*rel.parts)
        if not p.is_file():
            problems.append(f"{a.preset}: missing {a.path}")
            continue
        if type(a.size) is not int or a.size < 0 or p.stat().st_size != a.size:
            problems.append(f"{a.preset}: size mismatch for {a.path}")
        if (type(a.sha256) is not str or len(a.sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in a.sha256)
                or sha256_file(p) != a.sha256):
            problems.append(f"{a.preset}: sha256 mismatch for {a.path}")
    if root is not None:
        try:
            if tree_digest(root) != manifest.tree:
                problems.append("project tree changed since manifest")
        except (OSError, ValueError):
            problems.append("project tree cannot be safely verified")
    if manifest.verdict != "SHIP":
        problems.append(f"manifest verdict is {manifest.verdict}")
    return problems
