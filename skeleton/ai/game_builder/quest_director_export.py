"""Fail-closed atomic publication of verified original quest and scene sources."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
import tempfile

from .contracts import canonical_json, canonical_digest
from .quest_director_studio import DirectorStudioProduct
from .quest_scene_engine import DirectorError


def export_director_studio(product: DirectorStudioProduct, destination: str | Path,
                           *, authorized: bool) -> Path:
    if not authorized:
        raise PermissionError("original game publication requires explicit authority")
    if not isinstance(product, DirectorStudioProduct):
        raise DirectorError("typed, reviewed original source product required")
    if (not product.mirror.passed
            or product.mirror.digest != product.manifest["mirror_digest"]):
        raise DirectorError("adversarial proof is absent or changed")
    if set(product.files) != set(product.manifest["files"]) | {"release.json"}:
        raise DirectorError("manifest and authored source paths differ")
    for relative, digest in product.manifest["files"].items():
        path = Path(relative)
        if (path.is_absolute() or ".." in path.parts or not all(
                part.isascii() and part.replace("_", "").replace(".", "")
                .replace("-", "").isalnum() for part in path.parts
        )):
            raise DirectorError("untrusted output name")
        if sha256(product.files[relative]).hexdigest() != digest:
            raise DirectorError("modified original scene asset detected")
    expected = (canonical_json(product.manifest) + "\n").encode("utf-8")
    if product.files["release.json"] != expected:
        raise DirectorError("release manifest bytes changed")
    body = {k: v for k, v in product.manifest.items() if k != "manifest_digest"}
    if canonical_digest(body) != product.manifest["manifest_digest"]:
        raise DirectorError("source release hash chain does not reproduce")
    target = Path(destination)
    if target.exists() or target.is_symlink() or target.name in {"", ".", ".."}:
        raise DirectorError("original game outputs cannot overwrite other projects")
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise DirectorError("existing real export parent required")
    temporary = Path(tempfile.mkdtemp(prefix=".quest-director-", dir=target.parent))
    try:
        for relative, payload in product.files.items():
            final = temporary / relative
            final.parent.mkdir(parents=True, exist_ok=True)
            final.write_bytes(payload)
        if target.exists() or target.is_symlink():
            raise DirectorError("destination appeared while building original game")
        os.rename(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


__all__ = ["export_director_studio"]
