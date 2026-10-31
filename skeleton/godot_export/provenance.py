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
from pathlib import Path
from typing import Any

from .binary import sha256_file
from .project import IGNORED_DIRS

SCHEMA = "skeleton.godot_export.provenance/v1"


def tree_digest(root: Path) -> str:
    """Order-independent digest of project sources (path + content hash)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
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
        d = json.loads(text)
        if d.get("schema") != SCHEMA:
            raise ValueError(f"unknown provenance schema {d.get('schema')!r}")
        return cls(d["project"], d["tree"], d["engine"], d["verdict"], d.get("git"),
                   [Artifact(**a) for a in d.get("artifacts", [])])


def build(root: Path, engine: str, verdict: str, artifacts: dict[str, Path], base: Path | None = None) -> Manifest:
    base = base or root
    m = Manifest(root.name, tree_digest(root), engine, verdict, git_head(root))
    for preset, path in artifacts.items():
        rel = path.resolve().relative_to(base.resolve()).as_posix()
        m.artifacts.append(Artifact(preset, rel, sha256_file(path), path.stat().st_size))
    return m


def verify(manifest: Manifest, base: Path, root: Path | None = None) -> list[str]:
    problems = []
    for a in manifest.artifacts:
        p = base / a.path
        if not p.is_file():
            problems.append(f"{a.preset}: missing {a.path}")
        elif sha256_file(p) != a.sha256:
            problems.append(f"{a.preset}: sha256 mismatch for {a.path}")
    if root is not None and tree_digest(root) != manifest.tree:
        problems.append("project tree changed since manifest")
    if manifest.verdict != "SHIP":
        problems.append(f"manifest verdict is {manifest.verdict}")
    return problems
