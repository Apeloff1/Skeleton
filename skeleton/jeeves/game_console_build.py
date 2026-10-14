"""Bounded console builds using trusted adapters in an isolated local worker.

Source availability, installed toolchains, successful compilation and gameplay
are distinct states. No client command, environment, Python program, Makefile
or CMake program becomes host execution authority. Missing isolation fails
closed; the legacy CLI compiler is never used as an unsandboxed fallback.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import queue
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "skeleton.console_build.v1"
MAX_FILES = 256
MAX_SOURCE = 16 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
MAX_ARTIFACT = 16 * 1024 * 1024
MAX_ARTIFACTS = 8
MAX_OUTPUT = 32 * 1024 * 1024
MAX_LOG_BYTES = 256 * 1024
MAX_LOG_EVENTS = 1024
_PATH = re.compile(r"^[A-Za-z0-9_.\-/]{1,240}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_SYSTEM_BIN_DIRS = ("/usr/bin", "/usr/local/bin", "/bin")
_SDK_ROOTS = (
    "/opt/devkitpro",
    "/opt/devkitPro",
    "/opt/devkitSMS",
    "/opt/libdragon",
    "/opt/psn00bsdk",
    "/opt/sgdk",
    "/opt/pvsneslib",
    "/opt/nxdk",
    "/opt/rgbds",
    "/opt/cc65",
    "/opt/z88dk",
    "/opt/pspdev",
    "/opt/m68k-amigaos",
    "/opt/m68k-atari-mint",
    "/opt/PlaydateSDK",
)
_SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".s", ".asm"}
_BUILD_CONTROL = {"Makefile", "CMakeLists.txt"}
_BINARY_CACHE: dict[tuple[Any, ...], tuple[str, str]] = {}
_BINARY_LOCK = threading.Lock()
_SDK_PROFILES = {
    "master_system": ("/opt/devkitSMS", ("sdcc", "makesms"), {"DEVKITSMS_HOME": "/opt/devkitSMS"}, "make"),
    "game_gear": ("/opt/devkitSMS", ("sdcc", "makesms"), {"DEVKITSMS_HOME": "/opt/devkitSMS"}, "make"),
    "snes": (
        "/opt/pvsneslib",
        ("816-tcc", "wla-65816", "wlalink"),
        {"PVSNESLIB_HOME": "/opt/pvsneslib"},
        "make",
    ),
    "genesis": ("/opt/sgdk", ("m68k-elf-gcc",), {"GDK": "/opt/sgdk"}, "make"),
    "nintendo_64": ("/opt/libdragon", ("mips64-elf-gcc",), {"N64_INST": "/opt/libdragon"}, "make"),
    "nintendo_ds": (
        "/opt/devkitpro",
        ("arm-none-eabi-gcc",),
        {"DEVKITPRO": "/opt/devkitpro", "DEVKITARM": "/opt/devkitpro/devkitARM"},
        "make",
    ),
    "game_boy_advance": (
        "/opt/devkitpro",
        ("arm-none-eabi-gcc",),
        {"DEVKITPRO": "/opt/devkitpro", "DEVKITARM": "/opt/devkitpro/devkitARM"},
        "make",
    ),
    "gamecube": (
        "/opt/devkitpro",
        ("powerpc-eabi-gcc",),
        {"DEVKITPRO": "/opt/devkitpro", "DEVKITPPC": "/opt/devkitpro/devkitPPC"},
        "make",
    ),
    "wii": (
        "/opt/devkitpro",
        ("powerpc-eabi-gcc",),
        {"DEVKITPRO": "/opt/devkitpro", "DEVKITPPC": "/opt/devkitpro/devkitPPC"},
        "make",
    ),
    "nintendo_3ds": (
        "/opt/devkitpro",
        ("arm-none-eabi-gcc",),
        {"DEVKITPRO": "/opt/devkitpro", "DEVKITARM": "/opt/devkitpro/devkitARM"},
        "make",
    ),
    "nintendo_switch": (
        "/opt/devkitpro",
        ("aarch64-none-elf-gcc",),
        {"DEVKITPRO": "/opt/devkitpro", "DEVKITA64": "/opt/devkitpro/devkitA64"},
        "make",
    ),
    "wii_u": (
        "/opt/devkitpro",
        ("powerpc-eabi-gcc",),
        {"DEVKITPRO": "/opt/devkitpro", "DEVKITPPC": "/opt/devkitpro/devkitPPC"},
        "make",
    ),
    "psp": ("/opt/pspdev", ("psp-gcc",), {"PSPDEV": "/opt/pspdev"}, "make"),
    "ps1": ("/opt/psn00bsdk", ("mipsel-none-elf-gcc", "cmake"), {"PSN00BSDK": "/opt/psn00bsdk"}, "cmake"),
    "xbox_original": ("/opt/nxdk", ("clang",), {"NXDK_DIR": "/opt/nxdk"}, "make"),
}
_CC65_TARGETS = {
    "commodore_64": "c64",
    "commodore_128": "c128",
    "commodore_vic20": "vic20",
    "commodore_pet": "pet",
    "commodore_plus4": "plus4",
    "apple_ii": "apple2",
    "atari_400_800": "atari",
    "atari_5200": "atari5200",
    "lynx": "lynx",
    "bbc_micro": "bbc",
    "oric_atmos": "atmos",
}


class ConsoleBuildError(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _path(value: Any) -> str:
    if not isinstance(value, str) or not _PATH.fullmatch(value):
        raise ConsoleBuildError("build file path is not a bounded canonical relative path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or str(parsed) != value or any(part in {".", ".."} for part in parsed.parts):
        raise ConsoleBuildError("build source path escapes its project")
    return value


@dataclass(frozen=True, slots=True)
class BuildSourceFile:
    path: str
    data: bytes
    original_digest: str

    def __post_init__(self) -> None:
        _path(self.path)
        if (
            not isinstance(self.data, bytes)
            or len(self.data) > MAX_FILE
            or not _SHA.fullmatch(self.original_digest)
        ):
            raise ConsoleBuildError("build source bytes or provenance digest exceed bounds")


@dataclass(frozen=True, slots=True)
class BuildSourceTree:
    files: tuple[BuildSourceFile, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.files, tuple)
            or not 1 <= len(self.files) <= MAX_FILES
            or any(type(item) is not BuildSourceFile for item in self.files)
        ):
            raise ConsoleBuildError("build requires a bounded typed source tree")
        names = [item.path for item in self.files]
        if any(
            PurePosixPath(name).parts[0] in {"build", "out", ".git"}
            or PurePosixPath(name).name in {"CMakeCache.txt", "CMakePresets.json", "CMakeUserPresets.json"}
            for name in names
        ):
            raise ConsoleBuildError("decoded compiler output/cache paths cannot be source inputs")
        if (
            len({name.casefold() for name in names}) != len(names)
            or sum(len(item.data) for item in self.files) > MAX_SOURCE
        ):
            raise ConsoleBuildError("build source aliases or cumulative size exceed bounds")

    @classmethod
    def from_mapping(cls, files: Mapping[str, str | bytes]) -> BuildSourceTree:
        if not isinstance(files, Mapping) or not 1 <= len(files) <= MAX_FILES:
            raise ConsoleBuildError("build source must be a bounded path-to-content object")
        values = []
        for path, content in sorted(files.items()):
            _path(path)
            if PurePosixPath(path).parts[0] in {"build", "out", ".git"} or PurePosixPath(path).name in {
                "CMakeCache.txt",
                "CMakePresets.json",
                "CMakeUserPresets.json",
            }:
                raise ConsoleBuildError("compiler output/cache directories cannot be source inputs")
            if isinstance(content, str):
                data = content.encode("utf-8")
            elif isinstance(content, bytes):
                data = content
            else:
                raise ConsoleBuildError("build source content must be actual text or bytes")
            original = hashlib.sha256(data).hexdigest()
            if path.endswith(".base64"):
                if len(data) > MAX_FILE:
                    raise ConsoleBuildError("encoded source asset exceeds its limit")
                try:
                    data = base64.b64decode(data.strip(), validate=True)
                except ValueError as exc:
                    raise ConsoleBuildError("source asset is not valid explicit base64") from exc
                path = _path(path.removesuffix(".base64"))
            values.append(BuildSourceFile(path, data, original))
        return cls(tuple(values))

    @property
    def digest(self) -> str:
        return _digest(self.inventory())

    def inventory(self) -> list[dict[str, Any]]:
        return [
            {
                "path": item.path,
                "bytes": len(item.data),
                "digest": hashlib.sha256(item.data).hexdigest(),
                "original_digest": item.original_digest,
            }
            for item in sorted(self.files, key=lambda item: item.path)
        ]


@dataclass(frozen=True, slots=True)
class ConsoleBuildRequest:
    target_id: str
    sources: BuildSourceTree
    style_id: str = "arcade_score_attack"
    optimization: int = 1
    debug: bool = False
    timeout_seconds: int = 60
    expected_source_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_id, str) or not 1 <= len(self.target_id) <= 128:
            raise ConsoleBuildError("native target is invalid")
        object.__setattr__(self, "target_id", self.target_id.removeprefix("dragon_native:"))
        if (
            type(self.sources) is not BuildSourceTree
            or type(self.optimization) is not int
            or self.optimization not in (0, 1, 2)
            or type(self.debug) is not bool
            or type(self.timeout_seconds) is not int
            or not 5 <= self.timeout_seconds <= 120
        ):
            raise ConsoleBuildError("build options exceed their typed authority or limits")
        if self.expected_source_digest is not None and self.expected_source_digest != self.sources.digest:
            raise ConsoleBuildError("build source compare-and-swap identity differs")
        from skeleton.ai.webcrawler.dragon_native_targets import (
            demand_target,
            target_catalog,
        )

        demand_target(self.target_id)
        row = next(item for item in target_catalog() if item["id"] == self.target_id)
        if not isinstance(self.style_id, str) or self.style_id not in row["supported_styles"]:
            raise ConsoleBuildError("requested target has no declared source emitter for this style")


@dataclass(frozen=True, slots=True)
class BuildArtifact:
    name: str
    data: bytes
    format: str
    format_validation: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bytes": len(self.data),
            "digest": self.digest,
            "format": self.format,
            "format_validation": self.format_validation,
            "hardware_execution_verified": False,
        }


@dataclass(frozen=True, slots=True)
class ConsoleBuildResult:
    state: str
    _receipt_json: str
    artifacts: tuple[BuildArtifact, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA,
            "state": self.state,
            "receipt": json.loads(self._receipt_json),
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "binary_ready": self.state == "binary_ready" and bool(self.artifacts),
            "hardware_execution_verified": False,
        }


def _trusted_binary(name: str, sdk: tuple[str, ...] = ()) -> tuple[str, str] | None:
    candidates = [Path(directory) / name for directory in _SYSTEM_BIN_DIRS]
    for root in sdk:
        candidates.extend((Path(root) / "bin" / name, Path(root) / "tools/bin" / name))
        for directory in (
            "devkitARM/bin",
            "devkitPPC/bin",
            "devkitA64/bin",
            "mips64-elf/bin",
            "mipsel-none-elf/bin",
        ):
            candidates.append(Path(root) / directory / name)
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            allowed = tuple(Path(value).resolve() for value in (*_SYSTEM_BIN_DIRS, *sdk))
            if not any(resolved.is_relative_to(root) for root in allowed):
                continue
            info = resolved.stat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & 0o022
                or not os.access(resolved, os.X_OK)
                or info.st_size > 64 * 1024 * 1024
            ):
                continue
            signature = (str(resolved), info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            with _BINARY_LOCK:
                cached = _BINARY_CACHE.get(signature)
            if cached is not None:
                return cached
            digest = hashlib.sha256()
            with resolved.open("rb") as handle:
                for block in iter(lambda: handle.read(256 * 1024), b""):
                    digest.update(block)
            result = (str(resolved), digest.hexdigest())
            with _BINARY_LOCK:
                if len(_BINARY_CACHE) >= 128:
                    _BINARY_CACHE.clear()
                _BINARY_CACHE[signature] = result
            return result
        except OSError:
            continue
    return None


def _native_row(target_id: str) -> dict[str, Any]:
    from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

    return next(item for item in target_catalog() if item["id"] == target_id)


def _host_abi(target_id: str) -> bool:
    from skeleton.ai.webcrawler.dragon_desktop_abi import ABI_PROFILES

    system, machine = platform.system(), platform.machine().lower()
    if target_id in {"pc_linux", "steam_deck"}:
        return system == "Linux" and machine in {"x86_64", "amd64"}
    if target_id in {"pc_windows", "pc_macos"}:
        return False  # This Linux sandbox never labels its binary another OS.
    profile = ABI_PROFILES.get(target_id)
    if profile is None:
        return False
    aliases = {
        "x86_64": {"x86_64", "amd64"},
        "arm64": {"aarch64", "arm64"},
        "x86": {"i386", "i686", "x86"},
        "riscv64": {"riscv64"},
    }
    return profile.system == system and machine in aliases.get(profile.arch, {profile.arch})


def _adapter(target_id: str) -> dict[str, Any]:
    from skeleton.ai.webcrawler.dragon_desktop_abi import DESKTOP_NATIVE

    row = _native_row(target_id)
    result = {
        "target_id": target_id,
        "class": "source_only",
        "tools": [],
        "sdk": [],
        "environment": {},
        "reason": "No fixed sandboxed compiler adapter is declared for this target",
    }
    if target_id in {"game_boy", "game_boy_color"}:
        result.update({"class": "rgbds", "tools": ["rgbasm", "rgblink", "rgbfix"], "reason": None})
    elif target_id == "nes":
        result.update({"class": "nes_ca65", "tools": ["ca65", "ld65"], "reason": None})
    elif target_id in _CC65_TARGETS:
        result.update(
            {"class": "cc65", "tools": ["cl65"], "cc65_target": _CC65_TARGETS[target_id], "reason": None}
        )
    elif target_id == "atari_2600":
        result.update({"class": "dasm", "tools": ["dasm"], "reason": None})
    elif target_id in DESKTOP_NATIVE:
        result.update(
            {
                "class": "desktop_sdl",
                "tools": ["gcc"],
                "reason": (
                    None
                    if _host_abi(target_id)
                    else "A trusted runner for the exact target OS/CPU ABI is required"
                ),
            }
        )
    elif target_id in _SDK_PROFILES:
        root, tools, environment, recipe = _SDK_PROFILES[target_id]
        result.update(
            {
                "class": "canonical_sdk_" + recipe,
                "tools": [*tools, "make" if recipe == "make" else "cmake"],
                "sdk": [root],
                "environment": environment,
                "reason": None,
            }
        )
    result["output_extension"] = row["output"]
    return result


def console_build_catalog() -> list[dict[str, Any]]:
    """Report every declared profile, with observed fixed-adapter readiness."""
    from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

    sandbox = _trusted_binary("bwrap")
    rows = []
    for target in target_catalog():
        adapter = _adapter(target["id"])
        sdk = tuple(adapter["sdk"])
        missing = [name for name in dict.fromkeys(adapter["tools"]) if _trusted_binary(name, sdk) is None]
        missing.extend(root for root in sdk if not Path(root).is_dir())
        if adapter["class"] == "desktop_sdl" and not Path("/usr/include/SDL2/SDL.h").is_file():
            missing.append("SDL2 development headers/libraries")
        status = (
            "source_only"
            if adapter["class"] == "source_only" or adapter["reason"]
            else (
                "toolchain_missing"
                if missing
                else (
                    "sandbox_unavailable"
                    if sandbox is None or platform.system() != "Linux"
                    else "build_available_unexecuted"
                )
            )
        )
        rows.append(
            {
                "target_id": target["id"],
                "family": target["family"],
                "toolchain": target["toolchain"],
                "output_extension": target["output"],
                "supported_styles": list(target["supported_styles"]),
                "compiler_class": adapter["class"],
                "options": {
                    "optimization": adapter["class"] in {"desktop_sdl", "cc65"},
                    "debug": adapter["class"] in {"desktop_sdl", "cc65", "nes_ca65", "canonical_sdk_cmake"},
                },
                "state": status,
                "missing_dependencies": missing,
                "reason": adapter["reason"],
                "execution_checked": False,
                "hardware_execution_verified": False,
            }
        )
    return rows


def _prepare(request: ConsoleBuildRequest) -> dict[str, Any]:
    adapter = _adapter(request.target_id)
    missing = []
    binaries = {}
    for name in dict.fromkeys(["bwrap", *adapter["tools"]]):
        binding = _trusted_binary(name, tuple(adapter["sdk"]))
        if binding is None:
            missing.append(name)
        else:
            binaries[name] = {"path": binding[0], "digest": binding[1]}
    missing.extend(root for root in adapter["sdk"] if not Path(root).is_dir())
    if adapter["class"] == "desktop_sdl" and not Path("/usr/include/SDL2/SDL.h").is_file():
        missing.append("SDL2 development headers/libraries")
    sources = {item.path: item.data for item in request.sources.files}
    # Generated projects retain their native source bundle under a namespaced
    # path. Extract that exact target subtree, never unrelated assets/code.
    prefix = "game/generated/native/" + request.target_id + "/"
    if any(path.startswith(prefix) for path in sources):
        sources = {
            path.removeprefix(prefix): data for path, data in sources.items() if path.startswith(prefix)
        }
    commands: list[list[str]] = []
    expected_outputs: list[str] = []
    recipe_files: dict[str, bytes] = {}
    kind = adapter["class"]
    if kind not in {"desktop_sdl", "cc65"} and request.optimization != 1:
        raise ConsoleBuildError("this fixed toolchain recipe does not expose optimization overrides")
    if kind not in {"desktop_sdl", "cc65", "nes_ca65", "canonical_sdk_cmake"} and request.debug:
        raise ConsoleBuildError("this fixed toolchain recipe does not expose debug overrides")
    optimization = "-O" + str(request.optimization)
    debug = ["-g"] if request.debug else []
    if kind == "rgbds":
        asm = sorted(
            path for path in sources if Path(path).suffix.lower() == ".asm" and path.startswith("src/")
        )
        for index, path in enumerate(asm):
            commands.append(["rgbasm", "-I", "/work/", "-o", f"build/source_{index}.o", path])
        output = "build/game.gbc" if request.target_id == "game_boy_color" else "build/game.gb"
        expected_outputs = [output]
        commands.append(["rgblink", "-o", output, *[f"build/source_{index}.o" for index in range(len(asm))]])
        commands.append(
            [
                "rgbfix",
                "-v",
                "-p",
                "0",
                *(["-C"] if request.target_id == "game_boy_color" else []),
                "-t",
                "JEEVESBUILD",
                output,
            ]
        )
    elif kind == "nes_ca65":
        expected_outputs = ["build/game.nes"]
        asm = sorted(
            path
            for path in sources
            if Path(path).suffix.lower() in {".s", ".asm"} and path.startswith("src/")
        )
        for index, path in enumerate(asm):
            commands.append(["ca65", *debug, "-I", "/work/", "-o", f"build/source_{index}.o", path])
        commands.append(
            [
                "ld65",
                "-C",
                "nes.cfg",
                "-o",
                "build/game.nes",
                *[f"build/source_{index}.o" for index in range(len(asm))],
            ]
        )
    elif kind == "cc65":
        expected_outputs = ["build/game." + adapter["output_extension"]]
        c = sorted(
            path for path in sources if Path(path).suffix.lower() in {".c", ".s"} and path.startswith("src/")
        )
        commands.append(
            [
                "cl65",
                "-t",
                adapter["cc65_target"],
                *([] if request.optimization == 0 else ["-O" if request.optimization == 1 else "-Oirs"]),
                *debug,
                "-I",
                "/work/include",
                "-o",
                "build/game." + adapter["output_extension"],
                *c,
            ]
        )
    elif kind == "dasm":
        expected_outputs = ["build/game.bin"]
        commands.append(["dasm", "src/main.asm", "-f3", "-obuild/game.bin"])
    elif kind == "desktop_sdl":
        expected_outputs = ["build/game.elf"]
        c = sorted(path for path in sources if Path(path).suffix.lower() == ".c" and path.startswith("src/"))
        commands.append(
            [
                "gcc",
                "-std=c99",
                optimization,
                *debug,
                "-I/work/include",
                "-I/usr/include/SDL2",
                "-o",
                "build/game.elf",
                *c,
                "-lSDL2",
                "-lm",
            ]
        )
    elif kind.startswith("canonical_sdk_"):
        from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
        from skeleton.ai.webcrawler.dragon_native_projects import render_native_project

        canonical = render_native_project(
            title="Jeeves Console Build",
            target_id=request.target_id,
            style=request.style_id,
            candidate_id=request.sources.digest,
            mechanics=(Mechanic.MOVEMENT, Mechanic.EXPLORATION),
            authorized=True,
        )
        # The compiler can execute ONLY build-control files re-emitted from the
        # trusted owner. Edited source/assets/linker data are preserved.
        for path, content in canonical.files.items():
            if PurePosixPath(path).name in _BUILD_CONTROL or path.endswith((".cmake", ".mk", ".py", ".sh")):
                recipe_files[_path(path)] = content.encode()
        if kind.endswith("make") and "Makefile" in recipe_files:
            commands = [["make", "-j1", "-f", "/work/Makefile"]]
            expected_outputs = _canonical_make_outputs(recipe_files["Makefile"].decode())
        elif kind.endswith("cmake") and "CMakeLists.txt" in recipe_files:
            commands = [
                [
                    "cmake",
                    "-S",
                    "/work",
                    "-B",
                    "/work/build",
                    "-DCMAKE_BUILD_TYPE=Debug" if request.debug else "-DCMAKE_BUILD_TYPE=Release",
                ],
                ["cmake", "--build", "/work/build", "--parallel", "1"],
            ]
            targets = re.findall(
                r"(?:add_executable|psn00bsdk_add_executable)\(\s*([A-Za-z0-9_]+)",
                recipe_files["CMakeLists.txt"].decode(),
            )
            expected_outputs = ["build/" + name + "." + adapter["output_extension"] for name in targets]
        else:
            adapter["reason"] = "Canonical target source has no supported fixed SDK build recipe"
    if commands and not expected_outputs:
        adapter["reason"] = "Canonical build recipe has no statically bound output path"
    for path in expected_outputs:
        _path(path)
        if path in sources:
            raise ConsoleBuildError("pre-existing compiler output cannot be submitted as source")
    if sum(len(value) for value in recipe_files.values()) > MAX_FILE or len(recipe_files) > MAX_FILES:
        raise ConsoleBuildError("canonical build recipe exceeds its bounded control budget")
    if not any(Path(path).suffix.lower() in _SOURCE_SUFFIXES for path in sources):
        raise ConsoleBuildError("project has no actual native program source for this target")
    if any(len(command) > 300 for command in commands) or len(commands) > 258:
        raise ConsoleBuildError("compiler command count exceeds bounds")
    prepared = {
        "schema_version": SCHEMA,
        "target_id": request.target_id,
        "style_id": request.style_id,
        "source_digest": request.sources.digest,
        "source_inventory": request.sources.inventory(),
        "adapter": adapter,
        "tools": binaries,
        "commands": commands,
        "expected_outputs": expected_outputs,
        "recipe_digest": _digest(
            {path: hashlib.sha256(data).hexdigest() for path, data in sorted(recipe_files.items())}
        ),
        "missing_dependencies": missing,
        "timeout_seconds": request.timeout_seconds,
        "runtime_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    prepared["plan_digest"] = _digest(prepared)
    prepared["sources"] = sources
    prepared["recipe_files"] = recipe_files
    return prepared


def _canonical_make_outputs(text: str) -> list[str]:
    values = dict(re.findall(r"(?m)^([A-Za-z0-9_]+)\s*(?::=|\?=|=)\s*([A-Za-z0-9_.\-/]+)\s*$", text))
    match = re.search(r"(?m)^all\s*:\s*([^\n#]+)", text)
    if match is None:
        return []
    result = match.group(1)
    for _ in range(8):
        changed = re.sub(
            r"\$\(([A-Za-z0-9_]+)\)", lambda item: values.get(item.group(1), item.group(0)), result
        )
        if changed == result:
            break
        result = changed
    return [_path(path) for path in result.split() if _PATH.fullmatch(path)]


def _public_plan(prepared: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in prepared.items() if key not in {"sources", "recipe_files"}}


def _stop_group(process: subprocess.Popen) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)


def _sandbox_argv(prepared: Mapping[str, Any], work: Path, command: list[str]) -> list[str]:
    tools = prepared["tools"]
    name = command[0]
    if name not in tools:
        raise ConsoleBuildError("compiler command does not have an exact trusted binary binding")
    expected = tools[name]
    actual = _trusted_binary(name, tuple(prepared["adapter"]["sdk"]))
    if actual != (expected["path"], expected["digest"]):
        raise ConsoleBuildError("trusted compiler changed before dispatch")
    sandbox = tools["bwrap"]
    if _trusted_binary("bwrap") != (sandbox["path"], sandbox["digest"]):
        raise ConsoleBuildError("trusted sandbox changed before dispatch")
    argv = [
        tools["bwrap"]["path"],
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--cap-drop",
        "ALL",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    for directory in ("/lib", "/lib64", "/bin"):
        if Path(directory).exists():
            argv.extend(("--ro-bind", directory, directory))
    argv.extend(("--dir", "/etc"))
    if Path("/etc/ld.so.cache").is_file():
        argv.extend(("--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"))
    for root in prepared["adapter"]["sdk"]:
        if root not in _SDK_ROOTS:
            raise ConsoleBuildError("undeclared SDK root cannot enter compiler sandbox")
        argv.extend(("--ro-bind", root, root))
    argv.extend(
        (
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            "16777216",
            "--tmpfs",
            "/tmp",
            "--bind",
            str(work),
            "/work",
            "--chdir",
            "/work",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "LC_ALL",
            "C",
            "--setenv",
            "PATH",
            ":".join(dict.fromkeys([str(Path(value["path"]).parent) for value in tools.values()])),
        )
    )
    for name, value in sorted(prepared["adapter"]["environment"].items()):
        argv.extend(("--setenv", name, value))
    return [*argv, "--", expected["path"], *command[1:]]


def _format(target: str, data: bytes, extension: str) -> tuple[str, str]:
    if (
        extension in {"gb", "gbc", "nes", "sfc", "smc", "gba", "z64", "n64", "v64"}
        or target == "genesis"
        and extension in {"bin", "md"}
    ):
        from .game_learning_ingestion import _parse_rom

        metadata = _parse_rom(data, "compiled." + extension)
        if extension == "gbc" and data[0x143] not in (0x80, 0xC0):
            raise ConsoleBuildError("compiled cartridge does not have its declared CGB header")
        if any(
            metadata.get(key) is False
            for key in ("header_checksum_valid", "global_checksum_valid", "checksum_valid")
        ):
            raise ConsoleBuildError("compiled cartridge failed an implemented structural checksum")
        return metadata["format"], "structural_cartridge_metadata_only:" + _digest(metadata)
    if extension in {"elf", "mach_o", "exe"}:
        if extension == "elf" and (len(data) < 64 or data[:4] != b"\x7fELF"):
            raise ConsoleBuildError("compiler did not produce an ELF program")
        if extension == "elf":
            endian = "little" if data[5] == 1 else "big" if data[5] == 2 else None
            machines = {
                "x86_64": 62,
                "amd64": 62,
                "aarch64": 183,
                "arm64": 183,
                "riscv64": 243,
                "i386": 3,
                "i686": 3,
            }
            if endian is None or int.from_bytes(data[18:20], endian) != machines.get(
                platform.machine().lower()
            ):
                raise ConsoleBuildError("ELF artifact does not match the declared native runner CPU")
        if extension == "exe" and target == "ps1":
            if len(data) < 2048 or data[:8] != b"PS-X EXE":
                raise ConsoleBuildError("compiler did not produce a PS-X executable")
        elif extension == "exe" and (len(data) < 64 or data[:2] != b"MZ"):
            raise ConsoleBuildError("compiler did not produce a PE program")
        return extension, "structural_executable_header_only"
    if extension == "lnx" and (len(data) < 64 or data[:4] != b"LYNX"):
        raise ConsoleBuildError("compiler did not produce a Lynx cartridge header")
    if extension == "prg" and len(data) < 3:
        raise ConsoleBuildError("compiler did not produce a load-address program")
    return extension, "compiler_output_bytes_only_no_hardware_claim"


def _collect(prepared: Mapping[str, Any], work: Path) -> tuple[BuildArtifact, ...]:
    extension = prepared["adapter"]["output_extension"]
    if prepared["adapter"]["class"] == "desktop_sdl":
        extension = "elf"
    artifacts = []
    total = 0
    for name in prepared["expected_outputs"]:
        path = work / _path(name)
        if not path.is_file():
            raise ConsoleBuildError("compiler did not produce the exact declared artifact path")
        if (
            path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents if parent != work.parent)
            or not path.resolve().is_relative_to(work)
        ):
            raise ConsoleBuildError("compiler artifact escaped its private workspace")
        info = path.stat()
        if not 1 <= info.st_size <= MAX_ARTIFACT or total + info.st_size > MAX_OUTPUT:
            raise ConsoleBuildError("compiler artifacts exceed the admitted byte budget")
        name = path.relative_to(work).as_posix()
        if any(item.name == name for item in artifacts):
            continue
        data = path.read_bytes()
        if len(data) != info.st_size:
            raise ConsoleBuildError("compiler artifact changed while collecting")
        kind, validation = _format(prepared["target_id"], data, extension)
        artifacts.append(BuildArtifact(name, data, kind, validation))
        total += len(data)
        if len(artifacts) > MAX_ARTIFACTS:
            raise ConsoleBuildError("compiler artifact count exceeds bounds")
    if not artifacts:
        raise ConsoleBuildError("compiler completed without the declared target artifact")
    return tuple(artifacts)


def _resource_usage(root_pid: int, work: Path) -> None:
    """Bound observed aggregate descendants and private compiler disk usage."""
    pending, seen, memory = [root_pid], set(), 0
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        if len(seen) > 64:
            raise ConsoleBuildError("compiler descendant process count exceeds its budget")
        try:
            status = Path(f"/proc/{pid}/status").read_text()[:16_384]
            match = re.search(r"(?m)^VmRSS:\s*([0-9]+)\s*kB", status)
            memory += int(match.group(1)) * 1024 if match else 0
            children = Path(f"/proc/{pid}/task/{pid}/children").read_text()[:8192]
            pending.extend(int(value) for value in children.split())
        except (OSError, ValueError):
            continue
    if memory > 1024**3:
        raise ConsoleBuildError("compiler aggregate resident memory exceeds its budget")
    total, count = 0, 0
    stack = [work]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > 4096:
                    raise ConsoleBuildError("compiler private file count exceeds its budget")
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if stat.S_ISDIR(info.st_mode):
                    stack.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    total += info.st_size
                elif not stat.S_ISLNK(info.st_mode):
                    raise ConsoleBuildError("compiler created an undeclared special file")
                if total > MAX_SOURCE + MAX_OUTPUT + MAX_FILE:
                    raise ConsoleBuildError("compiler private disk bytes exceed their budget")


def _worker(prepared: dict[str, Any], channel, cancelled) -> None:
    process = None
    started = time.monotonic()
    total_log = events = 0
    exits = []
    try:
        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(
            resource.RLIMIT_CPU, (prepared["timeout_seconds"], prepared["timeout_seconds"] + 2)
        )
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_ARTIFACT, MAX_ARTIFACT))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        with nullcontext(prepared["_work_directory"]) as directory:
            work = Path(directory)
            os.chmod(work, 0o700)
            for path, data in {**prepared["sources"], **prepared["recipe_files"]}.items():
                destination = work / _path(path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            (work / "build").mkdir(exist_ok=True)
            for index, command in enumerate(prepared["commands"], 1):
                if cancelled.is_set():
                    channel.send({"kind": "terminal", "state": "cancelled", "exits": exits})
                    return
                argv = _sandbox_argv(prepared, work, command)
                channel.send({"kind": "command", "sequence": index, "tool": command[0]})
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                    start_new_session=True,
                    close_fds=True,
                )
                selector = selectors.DefaultSelector()
                diagnostic = bytearray()
                last_budget_check = 0.0
                selector.register(process.stdout, selectors.EVENT_READ)
                try:
                    while selector.get_map():
                        now = time.monotonic()
                        if now - last_budget_check >= 0.2:
                            _resource_usage(process.pid, work)
                            last_budget_check = now
                        if cancelled.is_set() or time.monotonic() - started >= prepared["timeout_seconds"]:
                            _stop_group(process)
                            channel.send(
                                {
                                    "kind": "terminal",
                                    "state": "cancelled" if cancelled.is_set() else "timed_out",
                                    "exits": exits,
                                }
                            )
                            return
                        for key, _ in selector.select(0.1):
                            data = os.read(key.fd, 4096)
                            if not data:
                                selector.unregister(key.fileobj)
                                continue
                            diagnostic.extend(data[: max(0, 4096 - len(diagnostic))])
                            retained = data[: max(0, MAX_LOG_BYTES - total_log)]
                            if retained and events < MAX_LOG_EVENTS:
                                events += 1
                                total_log += len(retained)
                                channel.send(
                                    {
                                        "kind": "log",
                                        "sequence": events,
                                        "text": retained.decode("utf-8", errors="replace"),
                                        "bytes_digest": hashlib.sha256(retained).hexdigest(),
                                        "bytes": len(retained),
                                    }
                                )
                    process.wait(timeout=max(0.1, prepared["timeout_seconds"] - (time.monotonic() - started)))
                finally:
                    selector.close()
                    process.stdout.close()
                exits.append({"sequence": index, "tool": command[0], "returncode": process.returncode})
                if process.returncode:
                    channel.send(
                        {
                            "kind": "terminal",
                            "state": (
                                "sandbox_unavailable"
                                if index == 1
                                and (
                                    b"bwrap:" in diagnostic
                                    or b"namespace" in diagnostic
                                    and b"Permission denied" in diagnostic
                                )
                                else "compile_failed"
                            ),
                            "exits": exits,
                        }
                    )
                    return
                process = None
            artifacts = _collect(prepared, work)
            for artifact in artifacts:
                channel.send({"kind": "artifact_start", **artifact.as_dict()})
                for offset in range(0, len(artifact.data), 65536):
                    channel.send(
                        {
                            "kind": "artifact_chunk",
                            "name": artifact.name,
                            "offset": offset,
                            "data": artifact.data[offset : offset + 65536],
                        }
                    )
                channel.send({"kind": "artifact_end", "name": artifact.name})
            channel.send(
                {
                    "kind": "terminal",
                    "state": "binary_ready",
                    "exits": exits,
                    "log_bytes": total_log,
                    "log_events": events,
                    "duration_seconds": round(time.monotonic() - started, 6),
                }
            )
    except BaseException as exc:  # noqa: BLE001
        try:
            channel.send(
                {"kind": "terminal", "state": "build_rejected", "reason": str(exc)[:512], "exits": exits}
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        if process is not None:
            _stop_group(process)
        channel.close()


class ConsoleBuildRunner:
    """Local execution handle; durable authorization stays with its caller."""

    def __init__(self, max_workers: int = 2):
        if type(max_workers) is not int or not 1 <= max_workers <= 4:
            raise ConsoleBuildError("local compiler concurrency must be within [1,4]")
        self._slots = threading.BoundedSemaphore(max_workers)
        self._cleanup_lock = threading.Lock()
        self._quarantined = []

    def _reap_quarantined(self):
        with self._cleanup_lock:
            index = 0
            while index < len(self._quarantined):
                process, writer, directory = self._quarantined[index]
                if process.poll() is None or writer is not None and writer.is_alive():
                    index += 1
                    continue
                for stream in (process.stdin, process.stdout):
                    if stream is not None and not stream.closed:
                        stream.close()
                directory.cleanup()
                self._quarantined.pop(index)
                self._slots.release()

    def plan(self, request: ConsoleBuildRequest) -> dict[str, Any]:
        return _public_plan(_prepare(request))

    def run(
        self,
        request: ConsoleBuildRequest,
        *,
        cancel: Callable[[], bool] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> ConsoleBuildResult:
        prepared = _prepare(request)
        receipt = _public_plan(prepared)
        if prepared["adapter"]["reason"]:
            return ConsoleBuildResult("source_only", _json(receipt))
        if prepared["missing_dependencies"]:
            return ConsoleBuildResult("toolchain_missing", _json(receipt))
        if platform.system() != "Linux":
            return ConsoleBuildResult("sandbox_unavailable", _json(receipt))
        self._reap_quarantined()
        if not self._slots.acquire(blocking=False):
            return ConsoleBuildResult("capacity_unavailable", _json(receipt))
        directory = tempfile.TemporaryDirectory(prefix="jeeves-build-")
        prepared["_work_directory"] = directory.name
        cancellation = threading.Event()
        worker = None
        writer = None
        write_errors = queue.Queue(maxsize=1)
        reader = selectors.DefaultSelector()
        pending = bytearray()
        deadline = time.monotonic() + request.timeout_seconds + 5
        terminal = None
        buffers: dict[str, bytearray] = {}
        metadata: dict[str, dict[str, Any]] = {}
        artifacts = []
        completed = set()
        log_chain = "0" * 64
        try:
            worker = subprocess.Popen(
                [sys.executable, "-I", str(Path(__file__).resolve()), "--build-worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                start_new_session=True,
                close_fds=True,
            )
            wire = {
                **prepared,
                "sources": {
                    path: base64.b64encode(data).decode("ascii") for path, data in prepared["sources"].items()
                },
                "recipe_files": {
                    path: base64.b64encode(data).decode("ascii")
                    for path, data in prepared["recipe_files"].items()
                },
            }
            request_bytes = _json(wire).encode() + b"\n"
            input_pipe = worker.stdin

            def send_request():
                try:
                    input_pipe.write(request_bytes)
                    input_pipe.close()
                except (BrokenPipeError, OSError, ValueError) as exc:
                    write_errors.put_nowait(exc)

            writer = threading.Thread(target=send_request, daemon=True, name="console-build-input")
            writer.start()
            reader.register(worker.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                if not write_errors.empty():
                    raise ConsoleBuildError("worker source transfer failed") from write_errors.get_nowait()
                if cancel is not None and cancel() and not cancellation.is_set():
                    cancellation.set()
                    try:
                        worker.send_signal(signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                if b"\n" not in pending:
                    for key, _ in reader.select(0.1):
                        block = os.read(key.fd, 65536)
                        if not block:
                            reader.unregister(key.fileobj)
                        else:
                            pending.extend(block)
                    if len(pending) > 256 * 1024:
                        raise ConsoleBuildError("worker message exceeds protocol byte bound")
                if b"\n" in pending:
                    line, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    message = json.loads(line)
                    if message.get("kind") == "artifact_chunk":
                        message["data"] = base64.b64decode(message["data"], validate=True)
                    kind = message.get("kind")
                    if kind in {"log", "command"}:
                        log_chain = _digest({"parent_digest": log_chain, "event": message})
                        if on_event is not None:
                            on_event({**message, "event_digest": log_chain})
                    elif kind == "artifact_start":
                        name = _path(message["name"])
                        if (
                            name in buffers
                            or name not in prepared["expected_outputs"]
                            or len(buffers) >= MAX_ARTIFACTS
                            or type(message["bytes"]) is not int
                            or not 1 <= message["bytes"] <= MAX_ARTIFACT
                        ):
                            raise ConsoleBuildError("worker artifact declaration exceeds bounds")
                        buffers[name], metadata[name] = bytearray(), message
                    elif kind == "artifact_chunk":
                        name, data = message["name"], message["data"]
                        if (
                            name not in buffers
                            or name in completed
                            or not isinstance(data, bytes)
                            or len(data) > 65536
                            or type(message["offset"]) is not int
                            or message["offset"] != len(buffers[name])
                            or len(buffers[name]) + len(data) > metadata[name]["bytes"]
                            or sum(len(value) for value in buffers.values()) + len(data) > MAX_OUTPUT
                        ):
                            raise ConsoleBuildError("worker artifact stream violates exact bounds")
                        buffers[name].extend(data)
                    elif kind == "artifact_end":
                        name = message["name"]
                        if (
                            name not in buffers
                            or name in completed
                            or len(buffers[name]) != metadata[name]["bytes"]
                            or hashlib.sha256(buffers[name]).hexdigest() != metadata[name]["digest"]
                        ):
                            raise ConsoleBuildError("worker artifact bytes fail their exact receipt")
                        item = metadata[name]
                        extension = prepared["adapter"]["output_extension"]
                        if prepared["adapter"]["class"] == "desktop_sdl":
                            extension = "elf"
                        kind, validation = _format(prepared["target_id"], bytes(buffers[name]), extension)
                        if (item["format"], item["format_validation"]) != (kind, validation):
                            raise ConsoleBuildError("artifact format differs from its actual bytes")
                        artifacts.append(
                            BuildArtifact(
                                name, bytes(buffers[name]), item["format"], item["format_validation"]
                            )
                        )
                        completed.add(name)
                    elif kind == "terminal":
                        terminal = message
                        break
                    else:
                        raise ConsoleBuildError("worker emitted an unknown protocol message")
                elif worker.poll() is not None and not reader.get_map():
                    break
            if terminal is None:
                cancellation.set()
                terminal = {"state": "cancelled" if cancel is not None and cancel() else "worker_interrupted"}
            if terminal["state"] == "binary_ready" and (
                not artifacts
                or completed != set(prepared["expected_outputs"])
                or len(artifacts) != len(metadata)
                or cancellation.is_set()
            ):
                terminal = {"state": "cancelled" if cancellation.is_set() else "worker_protocol_rejected"}
            if terminal["state"] == "binary_ready":
                exits = terminal.get("exits")
                if not isinstance(exits, list) or len(exits) != len(prepared["commands"]):
                    raise ConsoleBuildError("compiler exit receipt coverage differs")
                for index, (exit_row, command) in enumerate(zip(exits, prepared["commands"], strict=True), 1):
                    if (
                        not isinstance(exit_row, dict)
                        or set(exit_row) != {"sequence", "tool", "returncode"}
                        or type(exit_row["sequence"]) is not int
                        or exit_row["sequence"] != index
                        or exit_row["tool"] != command[0]
                        or type(exit_row["returncode"]) is not int
                        or exit_row["returncode"] != 0
                    ):
                        raise ConsoleBuildError("compiler command exit receipt differs")
            receipt.update(
                {
                    "execution": terminal,
                    "log_chain_digest": log_chain,
                    "artifact_digest": _digest([item.as_dict() for item in artifacts]),
                }
            )
            state = terminal["state"]
            return ConsoleBuildResult(
                state, _json(receipt), tuple(artifacts) if state == "binary_ready" else ()
            )
        finally:
            cancellation.set()
            cleanup_error = None
            quarantined = False
            try:
                if worker is not None:
                    try:
                        _stop_group(worker)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        cleanup_error = exc
                    if writer is not None:
                        writer.join(timeout=2)
                        if writer.is_alive():
                            cleanup_error = ConsoleBuildError("compiler input transfer did not quiesce")
                    if worker.poll() is None or writer is not None and writer.is_alive():
                        with self._cleanup_lock:
                            self._quarantined.append((worker, writer, directory))
                        quarantined = True
                    if not quarantined and not worker.stdin.closed:
                        worker.stdin.close()
                    if not quarantined:
                        worker.stdout.close()
            finally:
                reader.close()
                try:
                    if not quarantined:
                        directory.cleanup()
                finally:
                    if not quarantined:
                        self._slots.release()
            if cleanup_error is not None:
                raise ConsoleBuildError("compiler worker cleanup did not quiesce") from cleanup_error


build_runner = ConsoleBuildRunner()


class _WorkerChannel:
    def send(self, message: dict[str, Any]) -> None:
        if message.get("kind") == "artifact_chunk":
            message = {**message, "data": base64.b64encode(message["data"]).decode("ascii")}
        encoded = _json(message).encode()
        if len(encoded) > 128 * 1024:
            raise ConsoleBuildError("worker message exceeds its transport bound")
        sys.stdout.buffer.write(encoded + b"\n")
        sys.stdout.buffer.flush()

    def close(self) -> None:
        sys.stdout.buffer.flush()


def _worker_cli() -> None:
    cancellation = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signal, _frame: cancellation.set())
    line = sys.stdin.buffer.readline(32 * 1024 * 1024 + 1)
    if not line.endswith(b"\n") or len(line) > 32 * 1024 * 1024:
        raise ConsoleBuildError("worker request exceeds its bounded transport")
    prepared = json.loads(line)
    if prepared.get("runtime_digest") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ConsoleBuildError("compiler worker runtime changed before dispatch")
    for key in ("sources", "recipe_files"):
        prepared[key] = {
            path: base64.b64decode(value, validate=True) for path, value in prepared[key].items()
        }
    # Only this fixed package location is imported when a structural format
    # verifier needs its existing sibling owner; no backend __main__ is loaded.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    global __package__
    __package__ = "skeleton.jeeves"
    _worker(prepared, _WorkerChannel(), cancellation)


if __name__ == "__main__":
    if sys.argv[1:] != ["--build-worker"]:
        raise SystemExit("This module is the owned isolated compiler worker; use its typed API.")
    _worker_cli()
