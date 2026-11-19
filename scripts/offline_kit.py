"""Offline-only Skeleton wheel/model kit: stage, verify, and install without indexes.

Run on the target operating system and Python minor version. This is a
standard-library bootstrapper: installation cannot require Skeleton imports.
Release authenticity is NOT established by the unsigned SHA-256 manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import venv


SCHEMA = "skeleton.offline_kit.v1"
MAX_FILES = 2000
_HEX = re.compile(r"^[0-9a-f]{64}$")
_WHEEL = re.compile(r"^[A-Za-z0-9_.+!-]+\.whl$")
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024


class OfflineKitError(RuntimeError):
    """The offline kit is absent, incompatible, incomplete, or tampered with."""


def _canonical(data: object) -> bytes:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as inp:
        for chunk in iter(lambda: inp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(name: str) -> PurePosixPath:
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        raise OfflineKitError("invalid artifact name")
    value = PurePosixPath(name)
    if (
        not name or name.startswith("/") or
        any(part in ("", ".", "..") for part in value.parts) or
        value.as_posix() != name or ":" in name
    ):
        raise OfflineKitError("kit artifact escapes its root")
    return value


def _regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise OfflineKitError("kit contains missing, symlinked or non-file artifact")


def _files(root: Path) -> list[dict[str, object]]:
    gathered: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise OfflineKitError("kit contains symlinks")
        if path.is_dir():
            continue
        _regular(path)
        relative = path.relative_to(root).as_posix()
        if relative == "manifest.json":
            continue
        _relative(relative)
        gathered.append({
            "path": relative,
            "sha256": _hash(path),
            "size_bytes": path.stat().st_size,
        })
        if len(gathered) > MAX_FILES:
            raise OfflineKitError("too many kit files")
    return gathered


def _environment() -> dict[str, str]:
    return {
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "sys_platform": sys.platform,
        "machine": platform.machine().lower(),
        "wheel_platform": sysconfig.get_platform(),
    }


def _wheel_version(wheelhouse: Path) -> str:
    versions: set[str] = set()
    count = 0
    for path in wheelhouse.iterdir():
        if path.is_symlink() or not path.is_file() or not _WHEEL.fullmatch(path.name):
            raise OfflineKitError("wheelhouse must contain only regular .whl files")
        count += 1
        pieces = path.name.split("-")
        if len(pieces) < 5:
            raise OfflineKitError("invalid wheel filename")
        if pieces[0].replace("_", "-").lower() == "skeleton":
            versions.add(pieces[1])
    if not count or len(versions) != 1:
        raise OfflineKitError("wheelhouse must include exactly one Skeleton version")
    return versions.pop()


def pack(
    wheels: str | Path,
    destination: str | Path,
    *,
    gguf: str | Path | None = None,
    llama: str | Path | None = None,
    model_id: str = "offline-local-model",
) -> Path:
    wheelhouse = Path(wheels).expanduser().resolve(strict=True)
    if not wheelhouse.is_dir():
        raise OfflineKitError("wheelhouse must be a directory")
    target = Path(destination).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise OfflineKitError("destination already exists")
    if not target.parent.is_dir():
        raise OfflineKitError("destination parent does not exist")
    if (gguf is None) != (llama is None):
        raise OfflineKitError("GGUF and local llama.cpp executable are both required")
    if gguf is not None and (
        not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 128
    ):
        raise OfflineKitError("model ID is invalid")
    version = _wheel_version(wheelhouse)
    # The builder must not write its staging tree back into its own input.
    with tempfile.TemporaryDirectory(
        prefix=".skeleton-kit-", dir=target.parent,
    ) as temporary:
        stage = Path(temporary) / "kit"
        stage.mkdir(mode=0o700)
        wheel_dest = stage / "wheelhouse"
        wheel_dest.mkdir()
        for wheel in sorted(wheelhouse.iterdir()):
            _regular(wheel)
            shutil.copyfile(wheel, wheel_dest / wheel.name)
        shutil.copyfile(Path(__file__), stage / "offline_kit.py")
        has_model = gguf is not None
        if has_model:
            source_model = Path(gguf).expanduser()
            source_runtime = Path(llama).expanduser()
            _regular(source_model)
            _regular(source_runtime)
            (stage / "model").mkdir()
            (stage / "runtime").mkdir()
            target_model = stage / "model" / "model.gguf"
            binary_name = "llama-cli.exe" if os.name == "nt" else "llama-cli"
            target_runtime = stage / "runtime" / binary_name
            shutil.copyfile(source_model, target_model)
            shutil.copy2(source_runtime, target_runtime)
            if os.name != "nt":
                target_runtime.chmod(target_runtime.stat().st_mode | stat.S_IXUSR)
            deployment = {
                "schema_version": "skeleton.local_model.deployment.v1",
                "runtime_kind": "llama.cpp-cli",
                "model_id": model_id,
                "executable_path": "../runtime/" + binary_name,
                "executable_sha256": _hash(target_runtime),
                "model_path": "model.gguf",
                "model_sha256": _hash(target_model),
                "config": {
                    "context_size": 2048,
                    "gpu_layers": 0,
                    "temperature": 0.0,
                },
            }
            (stage / "model" / "deployment.json").write_bytes(_canonical(deployment) + b"\n")
        manifest = {
            "schema_version": SCHEMA,
            "distribution": "skeleton",
            "version": version,
            "environment": _environment(),
            "gguf_included": has_model,
            "files": _files(stage),
        }
        (stage / "manifest.json").write_bytes(_canonical(manifest) + b"\n")
        verify(stage)
        os.rename(stage, target)
    return target


def verify(root: str | Path) -> dict[str, object]:
    kit = Path(root).expanduser().resolve(strict=True)
    if not kit.is_dir():
        raise OfflineKitError("kit root must be a directory")
    manifest_path = kit / "manifest.json"
    _regular(manifest_path)
    if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise OfflineKitError("offline manifest exceeds size limit")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise OfflineKitError("invalid offline manifest") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "distribution", "version", "environment", "gguf_included", "files"}
        or data["schema_version"] != SCHEMA
        or data["distribution"] != "skeleton"
        or not isinstance(data["version"], str)
        or data["gguf_included"] not in (True, False)
        or type(data["gguf_included"]) is not bool
        or not isinstance(data["files"], list)
        or not 1 <= len(data["files"]) <= MAX_FILES
    ):
        raise OfflineKitError("invalid offline manifest schema")
    if not isinstance(data["environment"], dict) or set(data["environment"]) != set(_environment()):
        raise OfflineKitError("offline environment metadata missing")
    provided = data["files"]
    names: set[str] = set()
    for item in provided:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size_bytes"}:
            raise OfflineKitError("invalid kit file entry")
        name = _relative(item["path"]).as_posix()
        if name == "manifest.json" or name.casefold() in names:
            raise OfflineKitError("duplicate kit artifact identity")
        names.add(name.casefold())
        if (
            not isinstance(item["sha256"], str)
            or _HEX.fullmatch(item["sha256"]) is None
            or type(item["size_bytes"]) is not int
            or item["size_bytes"] < 0
        ):
            raise OfflineKitError("invalid kit artifact digest or size")
    observed = _files(kit)
    if provided != observed:
        raise OfflineKitError("offline kit files differ from pinned manifest")
    if not (kit / "offline_kit.py").is_file() or not (kit / "wheelhouse").is_dir():
        raise OfflineKitError("missing offline bootstrapper or wheelhouse")
    if _wheel_version(kit / "wheelhouse") != data["version"]:
        raise OfflineKitError("pinned Skeleton wheel version mismatch")
    if data["gguf_included"]:
        deployment = kit / "model" / "deployment.json"
        _regular(deployment)
        try:
            local = json.loads(deployment.read_text(encoding="utf-8"))
            binary = kit / "runtime" / (
                "llama-cli.exe" if data["environment"]["sys_platform"] == "win32" else "llama-cli"
            )
            if (
                local["executable_sha256"] != _hash(binary)
                or local["model_sha256"] != _hash(kit / "model" / "model.gguf")
            ):
                raise OfflineKitError("pinned local model artifacts differ")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise OfflineKitError("invalid bundled model deployment") from exc
    return data


def install(root: str | Path, destination: str | Path) -> Path:
    """Install into a new venv, rolling back incomplete local installations.

    A virtualenv is not relocatable, so the target path must remain stable
    from venv creation to first use. On failure, delete only that newly
    created target, never an existing operator installation or its parents.
    """
    kit = Path(root).expanduser().resolve(strict=True)
    manifest = verify(kit)
    if manifest["environment"] != _environment():
        raise OfflineKitError("bundle Python/OS/architecture differs from this host")
    target = Path(destination).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise OfflineKitError("installation destination already exists")
    if not target.parent.is_dir() or target == kit or kit in target.parents:
        raise OfflineKitError("install outside the verified bundle into an existing parent")

    command = [
        "-m", "pip", "--isolated", "install",
        "--no-index", "--no-input", "--no-cache-dir",
        "--disable-pip-version-check", "--only-binary=:all:",
        "--find-links", str(kit / "wheelhouse"),
        f"skeleton[local-inference]=={manifest['version']}",
    ]
    # Isolation is enforced at the package resolver, not claimed as an OS
    # egress sandbox for arbitrary executable wheel-install hooks.
    env = dict(os.environ)
    env.update({
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONNOUSERSITE": "1",
    })
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(target)
        python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), *command], check=True, env=env, shell=False)

        # The verified source bundle must remain byte-identical while pip
        # resolves it. An altered wheel or model invalidates the installation.
        if verify(kit) != manifest:
            raise OfflineKitError("offline kit changed during installation")
        if manifest["gguf_included"]:
            assets = target / "offline_model"
            assets.mkdir()
            shutil.copytree(kit / "model", assets / "model", symlinks=False)
            shutil.copytree(kit / "runtime", assets / "runtime", symlinks=False)
            # Verify copied identities, not merely the source kit hashes.
            local = json.loads((assets / "model" / "deployment.json").read_text("utf-8"))
            runtime_name = (
                "llama-cli.exe" if manifest["environment"]["sys_platform"] == "win32"
                else "llama-cli"
            )
            if (
                _hash(assets / "model" / "model.gguf") != local["model_sha256"]
                or _hash(assets / "runtime" / runtime_name) != local["executable_sha256"]
            ):
                raise OfflineKitError("copied model or local runtime digest differs")
        # Validate the actual install, not only subprocess exit code.
        if not python.is_file():
            raise OfflineKitError("offline installation created no Python runtime")
    except BaseException:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        raise
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build, verify or install a no-index Skeleton kit.")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("pack")
    make.add_argument("--wheels", required=True)
    make.add_argument("--destination", required=True)
    make.add_argument("--gguf")
    make.add_argument("--llama")
    make.add_argument("--model-id", default="offline-local-model")
    check = commands.add_parser("verify")
    check.add_argument("--kit", default=".")
    setup = commands.add_parser("install")
    setup.add_argument("--kit", default=".")
    setup.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            root = pack(args.wheels, args.destination,
                        gguf=args.gguf, llama=args.llama, model_id=args.model_id)
            print(f"Offline kit staged: {root}")
        elif args.command == "verify":
            data = verify(args.kit)
            print(f"Verified {len(data['files'])} pinned artifacts for Skeleton {data['version']}")
        else:
            target = install(args.kit, args.destination)
            print(f"Offline virtual environment installed: {target}")
            print("Start local AI: " + str(target / (
                "Scripts/python.exe" if os.name == "nt" else "bin/python"
            )) + " -m skeleton app local-ai")
            if (target / "offline_model" / "model" / "deployment.json").is_file():
                print("Select GGUF: " + str(target / "offline_model" / "model" / "deployment.json"))
    except (OfflineKitError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Offline kit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
