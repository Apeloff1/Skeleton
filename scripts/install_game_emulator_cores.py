"""Explicit reproducible local build/install of pinned open-source libretro cores.

This operator command compiles and inspects libraries; it never runs a core,
game, test, ROM or BIOS. Installed approvals remain isolated-host candidates.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

PINNED_CORES = {
    "gambatte": {
        "repository": "https://github.com/libretro/gambatte-libretro.git",
        "revision": "d9d6cd06382d1ced30de34d56d3609452323dab1",
        "artifact": "gambatte_libretro.so",
        "targets": ["game_boy", "game_boy_color", "game_boy_pocket", "game_boy_light"],
        "license": "COPYING",
    },
    "fceumm": {
        "repository": "https://github.com/libretro/libretro-fceumm.git",
        "revision": "ac0d00a7fc01166f84c7bac01d1084ebfd2b865e",
        "artifact": "fceumm_libretro.so",
        "targets": ["nes"],
        "license": "Copying",
    },
    "genesis_plus_gx": {
        "repository": "https://github.com/libretro/Genesis-Plus-GX.git",
        "revision": "393f70cd64c7334564c19a424c383f53986c13f4",
        "artifact": "genesis_plus_gx_libretro.so",
        "targets": ["genesis", "master_system", "sega_mark_iii", "sega_sg1000", "game_gear"],
        "license": "LICENSE.txt",
    },
    "snes9x": {
        "repository": "https://github.com/libretro/snes9x.git",
        "revision": "fae2fea08f74180759ef540ee94259213f503480",
        "artifact": "libretro/snes9x_libretro.so",
        "targets": ["snes"],
        "license": "LICENSE",
        "build_directory": "libretro",
        "makefile": "Makefile",
    },
    "mgba": {
        "repository": "https://github.com/mgba-emu/mgba.git",
        "revision": "143adf5aa2a60c6036810b0cd72445e13d74b0e6",
        "artifact": "core-build/mgba_libretro.so",
        "license": "LICENSE",
        "build_kind": "cmake",
        "targets": ["game_boy", "game_boy_color", "game_boy_advance", "game_boy_micro", "game_boy_player"],
    },
    "pcsx_rearmed": {
        "repository": "https://github.com/libretro/pcsx_rearmed.git",
        "revision": "c8816799b50388e61cfe237fe2cdbb7d8175f20a",
        "artifact": "pcsx_rearmed_libretro.so",
        "license": "COPYING",
        "targets": ["ps1"],
        "options": {"pcsx_rearmed_bios": "HLE"},
    },
}


def _environment():
    # No inherited provider/Mongo credentials, user git configuration, dynamic
    # loader overrides, compiler injection flags or credential helpers.
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "SOURCE_DATE_EPOCH": "0",
    }


def _run(command: list[str], *, cwd: Path, log: Path, timeout: int) -> str:
    with log.open("ab") as stream:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=_environment(),
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    if result.returncode:
        raise RuntimeError("Pinned operator command failed; see the private installation log")
    return " ".join(command)


def _git(command: list[str], directory: Path) -> str:
    result = subprocess.run(
        ["/usr/bin/git", *command],
        cwd=directory,
        env=_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
        check=True,
    )
    if len(result.stdout) > 1024 * 1024:
        raise ValueError("Source identity output exceeds its bound")
    return result.stdout.decode("utf-8").strip()


def _private_directory(path: Path):
    from skeleton.jeeves.game_emulator_catalog import _safe_path

    if not path.is_absolute():
        raise ValueError("Operator install/source directories require absolute paths")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _safe_path(str(path))
    details = path.stat()
    if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.geteuid():
        raise ValueError("Operator directory must be owned by the current user")
    path.chmod(0o700)


def _write_once(path: Path, data: bytes):
    from skeleton.jeeves.game_emulator_catalog import _read_file

    if path.exists():
        if _read_file(path, max(1, len(data)), trusted=True) != data:
            raise ValueError("Existing immutable installed artifact differs from the pinned bytes")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".install-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        path.chmod(0o400)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _licenses(source: Path, destination: Path, mandatory: str):
    from skeleton.jeeves.game_emulator_catalog import _read_file

    _private_directory(destination)
    if not (source / mandatory).is_file():
        raise ValueError("Pinned upstream core license is missing")
    candidates, total = [], 0
    for folder, directories, files in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name != ".git"]
        for filename in files:
            if filename.casefold().startswith(("license", "copying", "copyright")):
                candidates.append(Path(folder) / filename)
                if len(candidates) > 256:
                    raise ValueError("Upstream license inventory exceeds its bound")
    copied = []
    for path in sorted(candidates):
        data = _read_file(path, 1024 * 1024)
        total += len(data)
        if total > 8 * 1024 * 1024:
            raise ValueError("Upstream license bytes exceed their aggregate bound")
        relative = str(path.relative_to(source))
        name = hashlib.sha256(relative.encode()).hexdigest()[:16] + "-" + path.name
        _write_once(destination / name, data)
        copied.append(
            {"source_path": relative, "installed_name": name, "sha256": hashlib.sha256(data).hexdigest()}
        )
    return copied


def install(args):
    from skeleton.jeeves.game_emulator_catalog import (
        MAX_LIBRARY_BYTES,
        GameEmulatorRegistry,
        _read_file,
        inspect_libretro_library,
    )
    from skeleton.jeeves.game_emulator_catalog import (
        main as configure_registry,
    )

    if sys.platform != "linux" or not Path("/usr/bin/make").is_file() or not Path("/usr/bin/git").is_file():
        raise ValueError("Pinned core bootstrap currently requires Linux, git, make and a C/C++ toolchain")
    _private_directory(args.source_root)
    _private_directory(args.install_root)
    for name in ("cores", "system", "licenses", "logs", "identities"):
        _private_directory(args.install_root / name)
    records = []
    selected = args.core or list(PINNED_CORES)
    if len(selected) != len(set(selected)):
        raise ValueError("Core selection cannot repeat")
    for identity in selected:
        pin = PINNED_CORES[identity]
        directory = args.source_root / identity
        log = args.install_root / "logs" / (identity + ".log")
        if not directory.exists():
            if not args.fetch_sources:
                raise ValueError(
                    "Pinned source is absent; explicitly select --fetch-sources to acquire public source"
                )
            _run(
                ["/usr/bin/git", "clone", "--no-checkout", "--", pin["repository"], str(directory)],
                cwd=args.source_root,
                log=log,
                timeout=args.timeout,
            )
            _run(
                ["/usr/bin/git", "checkout", "--detach", pin["revision"]], cwd=directory, log=log, timeout=60
            )
        from skeleton.jeeves.game_emulator_catalog import _safe_path

        _safe_path(str(directory))
        if _git(["rev-parse", "HEAD"], directory) != pin["revision"]:
            raise ValueError("Source checkout differs from the exact pinned upstream revision")
        if _git(["remote", "get-url", "origin"], directory) != pin["repository"]:
            raise ValueError("Source checkout origin differs from the declared upstream repository")
        if _git(["status", "--porcelain", "--untracked-files=no"], directory):
            raise ValueError("Pinned source checkout contains tracked modifications")
        build_directory = directory / pin.get("build_directory", "")
        recipe = pin.get("makefile", "Makefile.libretro")
        build_command = [
            "/usr/bin/make",
            "-f",
            recipe,
            "platform=unix",
            "CC=/usr/bin/cc",
            "CXX=/usr/bin/g++",
            "-j" + str(args.jobs),
        ]
        configuration_command = None
        if pin.get("build_kind") == "cmake":
            cmake = args.cmake_binary or Path("/usr/bin/cmake")
            if not args.adopt_built:
                _safe_path(str(cmake))
                if not cmake.is_file() or not os.access(cmake, os.X_OK):
                    raise ValueError(
                        "mGBA compilation requires an explicitly installed CMake binary; this command never installs build tools"
                    )
            build_directory = directory
            configuration_command = [
                str(cmake),
                "-S",
                str(directory),
                "-B",
                str(directory / "core-build"),
                "-DBUILD_LIBRETRO=ON",
                "-DBUILD_QT=OFF",
                "-DBUILD_SDL=OFF",
                "-DBUILD_TEST=OFF",
                "-DUSE_FFMPEG=OFF",
                "-DUSE_LIBZIP=OFF",
                "-DUSE_SQLITE3=OFF",
            ]
            build_command = [
                str(cmake),
                "--build",
                str(directory / "core-build"),
                "--target",
                "mgba_libretro",
                "-j",
                str(args.jobs),
            ]
        if not args.adopt_built:
            if configuration_command:
                _run(configuration_command, cwd=directory, log=log, timeout=args.timeout)
            else:
                _run(
                    ["/usr/bin/make", "-f", recipe, "platform=unix", "clean"],
                    cwd=build_directory,
                    log=log,
                    timeout=60,
                )
            _run(build_command, cwd=build_directory, log=log, timeout=args.timeout)
        artifact = directory / pin["artifact"]
        observed = inspect_libretro_library(artifact)
        immutable_name = identity + "-" + observed["library_sha256"] + ".so"
        installed = args.install_root / "cores" / immutable_name
        _write_once(installed, _read_file(artifact, MAX_LIBRARY_BYTES, trusted=True))
        system = args.install_root / "system" / identity
        _private_directory(system)
        licenses = _licenses(directory, args.install_root / "licenses" / identity, pin["license"])
        record = {
            "schema_version": "skeleton.game.emulator_installation.v1",
            "core_id": identity,
            "source_repository": pin["repository"],
            "source_revision": pin["revision"],
            "source_commit_tree": _git(["rev-parse", "HEAD^{tree}"], directory),
            "build_command": build_command,
            "configuration_command": configuration_command,
            "build_performed_by_this_command": not args.adopt_built,
            "compiler": (
                "/usr/bin/cc"
                if not args.adopt_built
                else "adopted_compiled_artifact_compiler_not_independently_attested"
            ),
            "library_sha256": observed["library_sha256"],
            "library_bytes": observed["library_bytes"],
            "architecture": observed["architecture"],
            "installed_library": str(installed),
            "target_ids": pin["targets"],
            "licenses": licenses,
            "bios_installed": False,
            "sega_cd_available": False,
            "execution_checked": False,
            "sandbox_readiness": "requires_bwrap_user_namespace_admission_at_execution",
            "production_promotion_authorized": False,
        }
        encoded = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
        identity_path = (
            args.install_root
            / "identities"
            / (identity + "-" + hashlib.sha256(encoded).hexdigest() + ".json")
        )
        _write_once(identity_path, encoded)
        invocation = [
            "--registry",
            str(args.install_root / "cores.json"),
            "approve",
            "--core-id",
            identity,
            "--library",
            str(installed),
            "--system-directory",
            str(system),
        ]
        for target in pin["targets"]:
            invocation.extend(["--target", target])
        for key, value in pin.get("options", {}).items():
            invocation.extend(["--option", key + "=" + value])
        with contextlib.redirect_stdout(io.StringIO()):
            admission_code = configure_registry(invocation)
        if admission_code != 0:
            raise ValueError("Compiled core was not admitted to the explicit operator registry")
        records.append(record)
    registry = GameEmulatorRegistry(args.install_root / "cores.json")
    return {
        "status": "compiled_artifacts_installed",
        "registry_digest": registry.registry_digest,
        "registry_path": str(args.install_root / "cores.json"),
        "environment_variable": "SKL_GAME_EMULATOR_REGISTRY",
        "cores": records,
        "execution_checked": False,
        "tests_run": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--core", action="append", choices=sorted(PINNED_CORES))
    parser.add_argument("--fetch-sources", action="store_true")
    parser.add_argument(
        "--adopt-built", action="store_true", help="Inspect/install already compiled pinned source artifacts"
    )
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--cmake-binary",
        type=Path,
        help="Explicit operator-installed native CMake binary, only needed when compiling mGBA",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= 8 or not 30 <= args.timeout <= 1200:
        parser.error("jobs must be1..8 and command timeout30..1200 seconds")
    try:
        print(json.dumps(install(args), indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "installation_rejected", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
