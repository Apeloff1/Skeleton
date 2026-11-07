#!/usr/bin/env python3
"""Install the pinned headless Godot (and optionally export templates).

Everything is pinned in ``backend/godot.artifact.json`` (GB-9):

* ``archive.url`` / ``archive.sha512`` — the official Linux x86_64 zip,
  checked against Godot's published ``SHA512-SUMS.txt`` value;
* ``sha256`` / ``bytes`` — the extracted editor binary, the identity
  ``GodotLocator`` verifies at runtime;
* ``export_templates`` — the ``.tpz`` url + sha512 and the members we need.

Fails closed (exit 2) on any checksum or size mismatch. On success prints the
binary path and, under GitHub Actions, appends ``SKELETON_GODOT_BIN`` to
``$GITHUB_ENV``.

Usage::

    python scripts/install_godot.py --dest .godot-ci [--templates]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "backend" / "godot.artifact.json"
_CHUNK = 1024 * 1024


class InstallError(RuntimeError):
    pass


def _digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    if not url.startswith("https://github.com/godotengine/godot/releases/download/"):
        raise InstallError(f"refusing non-pinned download origin: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=600) as response, tmp.open("wb") as out:  # noqa: S310 - origin pinned above
        shutil.copyfileobj(response, out, _CHUNK)
    tmp.replace(dest)


def _fetch_verified(url: str, dest: Path, *, sha512: str) -> Path:
    if dest.is_file() and _digest(dest, "sha512") == sha512:
        return dest
    _download(url, dest)
    actual = _digest(dest, "sha512")
    if actual != sha512:
        dest.unlink(missing_ok=True)
        raise InstallError(f"sha512 mismatch for {dest.name}: {actual[:16]}… != {sha512[:16]}…")
    return dest


def load_manifest(path: Path = MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("sha256", "bytes", "archive"):
        if not data.get(key):
            raise InstallError(f"{path} lacks a pinned {key!r}")
    return data


def install_binary(manifest: dict, dest: Path) -> Path:
    archive = manifest["archive"]
    zpath = _fetch_verified(archive["url"], dest / Path(archive["url"]).name, sha512=archive["sha512"])
    binary = dest / archive["member"]
    if not (binary.is_file() and _digest(binary, "sha256") == manifest["sha256"]):
        with zipfile.ZipFile(zpath) as zf:
            zf.extract(archive["member"], dest)
    size = binary.stat().st_size
    if size != manifest["bytes"]:
        raise InstallError(f"binary size {size} != pinned {manifest['bytes']}")
    actual = _digest(binary, "sha256")
    if actual != manifest["sha256"]:
        raise InstallError(f"binary sha256 {actual[:16]}… != pinned {manifest['sha256'][:16]}…")
    binary.chmod(0o755)
    return binary


def install_templates(manifest: dict, dest: Path) -> Path:
    spec = manifest.get("export_templates") or {}
    if not spec.get("url") or not spec.get("sha512"):
        raise InstallError("manifest lacks export_templates url/sha512")
    tpz = _fetch_verified(spec["url"], dest / Path(spec["url"]).name, sha512=spec["sha512"])
    target = Path(os.path.expanduser(spec["install_dir"]))
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(tpz) as zf:
        for member in spec["members"]:
            with zf.open(member) as src, (target / Path(member).name).open("wb") as out:
                shutil.copyfileobj(src, out, _CHUNK)
    version = (target / "version.txt").read_text(encoding="utf-8").strip()
    expected = str(manifest.get("version", "")).replace("-", ".")
    if expected and version != expected:
        raise InstallError(f"templates version {version!r} != engine {expected!r}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", default=".godot-ci")
    parser.add_argument("--templates", action="store_true", help="also install export templates")
    parser.add_argument("--manifest", default=str(MANIFEST))
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(Path(args.manifest))
        dest = Path(args.dest).resolve()
        binary = install_binary(manifest, dest)
        print(f"godot: {binary} sha256 verified ({manifest['version']})")
        if args.templates:
            print(f"templates: {install_templates(manifest, dest)}")
            (dest / Path(manifest["export_templates"]["url"]).name).unlink(missing_ok=True)
    except (InstallError, OSError, KeyError, zipfile.BadZipFile) as exc:
        print(f"install_godot: FAILED {exc}", file=sys.stderr)
        return 2
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f"SKELETON_GODOT_BIN={binary}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
