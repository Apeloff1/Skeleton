"""Actual approved libretro cores hosted behind a bounded native subprocess.

The registry is installation authority. Game content is data, and private file
descriptors originate in the application's existing governed content owner.
The host never downloads cores/BIOS, runs uploaded Python, or silently falls
back to a reference simulation when real emulator activation fails.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import queue
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from functools import wraps
from pathlib import Path

from .game_emulator_catalog import (
    ApprovedEmulatorCore,
    GameContentBundle,
    GameEmulatorRegistry,
    load_game_content_for_core,
)
from .game_emulator_protocol import read_packet, write_packet
from .game_learning_runtime import EpisodeStep, GameEnvironmentSpec

SCHEMA = "skeleton.libretro_environment.v1"
MAX_STATE = 64 * 1024 * 1024
MAX_SNAPSHOT_JSON = 8 * 1024 * 1024
MAX_PRIVATE_CONTENT_COPY = 64 * 1024 * 1024
MAX_PIXELS = 4_194_304
MAX_CONTENT_TOTAL = 4 * 1024**3
_ACTIONS = {
    "idle": 0,
    "up": 16,
    "down": 32,
    "left": 64,
    "right": 128,
    "a": 256,
    "b": 1,
    "x": 512,
    "y": 2,
    "start": 8,
    "select": 4,
    "l": 1024,
    "r": 2048,
    "l2": 4096,
    "r2": 8192,
    "l3": 16384,
    "r3": 32768,
    "a_right": 384,
    "a_left": 320,
    "a_up": 272,
    "b_right": 129,
    "b_left": 65,
}
_KEY_ACTIONS = {
    "key_up": 273,
    "key_down": 274,
    "key_left": 276,
    "key_right": 275,
    "key_enter": 13,
    "key_space": 32,
    "key_escape": 27,
    "key_w": 119,
    "key_s": 115,
}
_EMPTY = {"buttons": 0, "axes": [0, 0, 0, 0], "keys": [], "mouse": [0, 0, 0, 0, 0, 0], "pointer": [0, 0, 0]}
_PORT_DEVICE_IDS = {"none": 0, "joypad": 1, "mouse": 2, "keyboard": 3, "analog": 5, "pointer": 6}


class EmulatorHostError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class EmulatorCancelled(EmulatorHostError):
    def __init__(self):
        super().__init__("emulator_cancelled", "Native emulator work was cancelled")


def _int(value: object, lower: int, upper: int, label: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise EmulatorHostError("invalid_emulator_input", label + " exceeds integer bounds")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise EmulatorHostError("invalid_emulator_digest", "Exact SHA256 is required")
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _system_interpreter() -> tuple[Path, str]:
    # Installation authority is this fixed system path, never a request field
    # or the managed application's arbitrary virtual-environment prefix.
    interpreter = Path("/usr/bin/python3").resolve(strict=True)
    info = interpreter.stat()
    if (
        not interpreter.is_relative_to("/usr")
        or info.st_uid != 0
        or info.st_mode & 0o022
        or not info.st_mode & 0o111
    ):
        raise EmulatorHostError(
            "emulator_runtime_unavailable", "Native sandbox requires the trusted system Python interpreter"
        )
    digest, _ = _hash_file(interpreter, 64 * 1024 * 1024)
    return interpreter, digest


def _policy_controls(action: str) -> dict[str, object]:
    result = json.loads(json.dumps(_EMPTY))
    if action in _KEY_ACTIONS:
        result["keys"] = [_KEY_ACTIONS[action]]
    else:
        result["buttons"] = _ACTIONS[action]
    return result


def _controls(value: object) -> list[dict[str, object]]:
    if not isinstance(value, (tuple, list)) or not 1 <= len(value) <= 4:
        raise EmulatorHostError("invalid_emulator_controller", "Controller port capacity differs")
    result = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != set(_EMPTY):
            raise EmulatorHostError("invalid_emulator_controller", "Controller fields differ")
        normalized = {"buttons": _int(row["buttons"], 0, 65535, "joypad mask")}
        for key, length in (("axes", 4), ("mouse", 6), ("pointer", 3)):
            items = row[key]
            if not isinstance(items, (tuple, list)) or len(items) != length:
                raise EmulatorHostError("invalid_emulator_controller", "Controller vector shape differs")
            normalized[key] = [
                (
                    _int(item, -32768, 32767, "controller displacement")
                    if key == "axes" or index < 2
                    else _int(item, 0, 1, "controller button")
                )
                for index, item in enumerate(items)
            ]
        keys = row["keys"]
        if not isinstance(keys, (tuple, list)) or len(keys) > 128:
            raise EmulatorHostError("invalid_emulator_controller", "Keyboard key capacity differs")
        normalized["keys"] = sorted({_int(key, 0, 511, "keyboard key") for key in keys})
        result.append(normalized)
    return result


def _controller_ports(value: object) -> tuple[str, ...]:
    if value is None:
        return ("joypad",) * 4
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 4:
        raise EmulatorHostError("invalid_emulator_device", "Exactly 1–4 declared controller ports are required")
    if any(type(name) is not str or name not in _PORT_DEVICE_IDS for name in value):
        raise EmulatorHostError("invalid_emulator_device", "Controller devices must use the finite supported libretro device IDs")
    return tuple(value) + ("none",) * (4 - len(value))


def _frame_metadata(value: object) -> dict[str, object]:
    fields = {
        "width",
        "height",
        "format",
        "pixel_sha256",
        "rotation",
        "video_callbacks",
        "runs",
        "audio_frames",
        "audio_sha256",
        "sample_rate",
        "fps",
        "audio_available",
        "shutdown",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value["format"] != "rgb24"
        or type(value["audio_available"]) is not bool
        or type(value["shutdown"]) is not bool
    ):
        raise EmulatorHostError("native_frame_corrupt", "Native frame metadata schema differs")
    result = dict(value)
    for key, lower, upper in (
        ("width", 1, 4096),
        ("height", 1, 4096),
        ("rotation", 0, 3),
        ("video_callbacks", 0, 2**63 - 1),
        ("runs", 0, 2**63 - 1),
        ("audio_frames", 0, 131072),
    ):
        _int(value[key], lower, upper, key)
    _sha(value["pixel_sha256"])
    _sha(value["audio_sha256"])
    for key, upper in (("sample_rate", 384000), ("fps", 1000)):
        item = value[key]
        if item is not None and (
            type(item) not in (float, int) or not math.isfinite(item) or not 0 < item <= upper
        ):
            raise EmulatorHostError("native_frame_corrupt", "Native audiovisual rate differs")
    if result["width"] * result["height"] > MAX_PIXELS:
        raise EmulatorHostError("native_frame_limit", "Native pixel count exceeds capacity")
    return result


def _name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 240
        or "\\" in value
        or ":" in value
        or "\0" in value
        or value.startswith("/")
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise EmulatorHostError("unsafe_emulator_content", "Content names must be exact safe relative paths")
    return value


def _hash_file(
    path: Path, maximum: int, *, copy_to: Path | None = None, cancelled: Callable[[], bool] | None = None
) -> tuple[str, int]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        os.close(descriptor)
        raise EmulatorHostError("emulator_file_limit", "Approved file type or size exceeds capacity")
    digest, size = hashlib.sha256(), 0
    destination = copy_to.open("xb") if copy_to is not None else None
    try:
        with os.fdopen(descriptor, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                if cancelled is not None and cancelled():
                    raise EmulatorCancelled()
                size += len(chunk)
                if size > maximum:
                    raise EmulatorHostError("emulator_file_limit", "Approved file grew beyond capacity")
                digest.update(chunk)
                if destination is not None:
                    destination.write(chunk)
            after = os.fstat(stream.fileno())
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or size != info.st_size:
            raise EmulatorHostError(
                "emulator_source_changed", "Approved file changed while it was being pinned"
            )
    finally:
        if destination is not None:
            destination.close()
    return digest.hexdigest(), size


class PreparedEmulatorContent:
    """Private materialization handle; its paths are never a browser interface."""

    def __init__(self, descriptor: Mapping[str, object], owner: tempfile.TemporaryDirectory | None = None):
        self.descriptor = dict(descriptor)
        self._owner = owner

    def as_dict(self) -> dict[str, object]:
        return json.loads(json.dumps(self.descriptor))

    def close(self) -> None:
        if self._owner is not None:
            self._owner.cleanup()
            self._owner = None


def prepare_emulator_content(
    bundle: GameContentBundle, *, reader: Callable | None = None
) -> PreparedEmulatorContent:
    if not isinstance(bundle, GameContentBundle):
        raise EmulatorHostError("unissued_emulator_content", "Canonical admitted content bundle is required")
    directory = tempfile.TemporaryDirectory(prefix="skeleton-emulator-content-")
    try:
        bundle.materialize_private(directory.name, reader)
        rows = bundle.as_dict()["files"]
        for row in rows:
            (Path(directory.name) / row["name"]).chmod(0o400)
        descriptor = {
            "root": directory.name,
            "entrypoint": bundle.entrypoint,
            "files": [
                {"name": row["name"], "size_bytes": row["size_bytes"], "sha256": row["sha256"]}
                for row in rows
            ],
            "content_digest": bundle.bundle_digest,
            "source_digest": bundle.source_digest,
            "bundle_id": bundle.bundle_digest,
        }
        return PreparedEmulatorContent(descriptor, directory)
    except (OSError, ValueError, TypeError):
        directory.cleanup()
        raise


def _prepared(
    value: Mapping[str, object], *, cancelled: Callable[[], bool] | None = None
) -> tuple[Path, str, tuple[dict[str, object], ...], str]:
    if (
        not isinstance(value, Mapping)
        or set(value)
        - {"root", "entrypoint", "files", "content_digest", "source_digest", "bundle_id", "schema_version"}
        or not {"root", "entrypoint", "files", "content_digest"} <= set(value)
    ):
        raise EmulatorHostError("invalid_emulator_content", "Prepared content descriptor schema differs")
    raw_root = value["root"]
    if not isinstance(raw_root, str) or not 1 <= len(raw_root) <= 4096:
        raise EmulatorHostError("unsafe_emulator_content", "Prepared content root is invalid")
    root = Path(raw_root)
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.resolve(strict=True) != root
        or not root.is_dir()
        or root.stat().st_uid != os.geteuid()
        or root.stat().st_mode & 0o077
    ):
        raise EmulatorHostError(
            "unsafe_emulator_content", "Prepared content root must be private and canonical"
        )
    entry = _name(value["entrypoint"])
    rows = value["files"]
    if not isinstance(rows, (tuple, list)) or not 1 <= len(rows) <= 96:
        raise EmulatorHostError("emulator_content_limit", "Prepared content file count exceeds capacity")
    normalized, names, total = [], set(), 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise EmulatorHostError("invalid_emulator_content", "Prepared file manifest is invalid")
        if set(row) == {"path", "bytes", "sha256"}:
            name, size = _name(row["path"]), _int(row["bytes"], 1, 2 * 1024**3, "content bytes")
        elif set(row) == {"name", "size_bytes", "sha256"}:
            name, size = _name(row["name"]), _int(row["size_bytes"], 1, 2 * 1024**3, "content bytes")
        else:
            raise EmulatorHostError("invalid_emulator_content", "Prepared file fields differ")
        if name in names:
            raise EmulatorHostError("invalid_emulator_content", "Prepared file name is duplicated")
        names.add(name)
        total += size
        if total > MAX_CONTENT_TOTAL:
            raise EmulatorHostError("emulator_content_limit", "Prepared content aggregate exceeds capacity")
        path = root / name
        if path.resolve(strict=True) != path or not path.is_file():
            raise EmulatorHostError("unsafe_emulator_content", "Prepared file has unsafe path components")
        observed, observed_size = _hash_file(path, size, cancelled=cancelled)
        if observed != _sha(row["sha256"]) or observed_size != size:
            raise EmulatorHostError("emulator_content_changed", "Prepared file checksum or size differs")
        normalized.append({"name": name, "size_bytes": size, "sha256": observed})
    if entry not in names:
        raise EmulatorHostError("invalid_emulator_content", "Prepared entrypoint is not a declared file")
    for count, path in enumerate(root.rglob("*"), 1):
        if (
            count > 1024
            or path.is_symlink()
            or path.is_file()
            and path.relative_to(root).as_posix() not in names
        ):
            raise EmulatorHostError(
                "unsafe_emulator_content", "Private content root contains undeclared entries"
            )
    normalized.sort(key=lambda row: row["name"])
    materialized = _digest(
        {
            "declared_content_digest": _sha(value["content_digest"]),
            "entrypoint": entry,
            "files": normalized,
            "source_digest": value.get("source_digest"),
        }
    )
    return root, entry, tuple(normalized), materialized


def _png(pixels: bytes, width: int, height: int) -> tuple[dict[str, object], bytes]:
    # Including bounded PCM and metadata, this fits the actor's 512 KiB frame.
    ratio = min(1.0, 320 / width, 320 / height)
    target_width, target_height = max(1, int(width * ratio)), max(1, int(height * ratio))
    preview = bytearray(target_width * target_height * 3)
    for y in range(target_height):
        source_y = y * height // target_height
        for x in range(target_width):
            source_x = x * width // target_width
            source = (source_y * width + source_x) * 3
            target = (y * target_width + x) * 3
            preview[target : target + 3] = pixels[source : source + 3]
    rows = b"".join(
        b"\0" + preview[y * target_width * 3 : (y + 1) * target_width * 3] for y in range(target_height)
    )

    def chunk(name: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + name
            + data
            + struct.pack(">I", binascii.crc32(name + data) & 0xFFFFFFFF)
        )

    image = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", target_width, target_height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )
    return {
        "width": target_width,
        "height": target_height,
        "pixel_digest": hashlib.sha256(preview).hexdigest(),
        "png_digest": hashlib.sha256(image).hexdigest(),
        "scaling_method": "nearest_neighbor" if ratio < 1 else "identity",
        "source_width": width,
        "source_height": height,
    }, image


def _serialized_native_operation(method):
    """Keep multi-command disk/savestate operations coherent on the same worker."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class EmulatorEnvironment:
    def __init__(
        self,
        core: ApprovedEmulatorCore,
        rom_source: bytes | None = None,
        *,
        content: PreparedEmulatorContent | Mapping[str, object] | GameContentBundle | None = None,
        filename: str = "game.bin",
        reader: Callable | None = None,
        max_steps: int = 512,
        frames_per_step: int = 1,
        controller_devices: Sequence[str] | None = None,
        timeout_seconds: float = 5,
        cancelled: Callable[[], bool] | None = None,
    ):
        self._lock = threading.RLock()
        self._process = None
        self._temporary = None
        self._prepared_owner = None
        self._closed = False
        self._sequence = 0
        self._replies = queue.Queue(maxsize=2)
        self._cancelled = cancelled
        self._registry = GameEmulatorRegistry.from_environment()
        self._interpreter, self._interpreter_sha256 = _system_interpreter()
        if not isinstance(core, ApprovedEmulatorCore):
            raise EmulatorHostError("unissued_core_binding", "Canonical approved core descriptor is required")
        self._registry.revalidate(core)
        self.core = core
        self.max_steps = _int(max_steps, 1, 4096, "episode steps")
        self.frames_per_step = _int(frames_per_step, 1, 60, "frames per step")
        self._controller_devices = _controller_ports(controller_devices)
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0.1 <= timeout_seconds <= 30
        ):
            raise EmulatorHostError("invalid_emulator_timeout", "Native command deadline is invalid")
        self.timeout_seconds = float(timeout_seconds)
        if cancelled is not None and not callable(cancelled):
            raise EmulatorHostError("invalid_emulator_cancel", "Cancellation probe must be callable")
        if content is not None and rom_source is not None:
            raise EmulatorHostError("ambiguous_emulator_content", "Select one exact content source")
        if content is None:
            if not isinstance(rom_source, bytes):
                raise EmulatorHostError("emulator_content_required", "Actual admitted content is required")
            content = load_game_content_for_core(core, rom_source, filename, registry=self._registry)
        if isinstance(content, GameContentBundle):
            self._prepared_owner = prepare_emulator_content(content, reader=reader)
            content = self._prepared_owner
        descriptor = content.as_dict() if isinstance(content, PreparedEmulatorContent) else content
        self._content_descriptor = dict(descriptor)
        self._content_root, entry, files, materialized_digest = _prepared(descriptor, cancelled=cancelled)
        self._code_bindings = {
            name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            for name in ("game_emulator_host.py", "game_emulator_worker.py", "game_emulator_protocol.py")
        }
        self._descriptor = {
            "schema_version": SCHEMA,
            "runtime_kind": "installed_libretro_emulator",
            "core_id": core.core_id,
            "core_sha256": core.library_sha256,
            "registry_digest": core.registry_digest,
            "firmware_digest": core.firmware_digest,
            "options_digest": hashlib.sha256(core.options_json.encode()).hexdigest(),
            "content_digest": descriptor["content_digest"],
            "materialized_content_digest": materialized_digest,
            "entrypoint": entry,
            "files": list(files),
            "max_episode_steps": self.max_steps,
            "frames_per_step": self.frames_per_step,
            "controller_port_devices": list(self._controller_devices),
            "source_code_digest": _digest(self._code_bindings),
            "host_python": list(sys.version_info[:3]),
            "worker_interpreter_sha256": self._interpreter_sha256,
            "worker_interpreter": str(self._interpreter),
            "reset_semantics": "actual retro_reset; episode seed labels identity and does not control a universal hardware RNG",
            "reward_semantics": "Measured visual exploration; game score, health, mastery and success are unavailable",
            "sandbox_required": True,
            "hardware_compatibility_verified": False,
        }
        bins = (0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75)
        self.spec = GameEnvironmentSpec(
            "libretro:" + core.core_id + ":" + materialized_digest[:24],
            _digest(self._descriptor),
            (*_ACTIONS, *_KEY_ACTIONS, "controller_input"),
            {key: bins for key in ("screen_mean", "visual_change", "audio_rms", "step_fraction")},
            ("visual_change",),
            self.max_steps,
        )
        self._seed = None
        self._steps = 0
        self._pixels = None
        self._frame = None
        self._audio = b""
        self._audio_total = 0
        self._audio_generation = 0
        self._observation = None
        self._controls = [json.loads(json.dumps(_EMPTY))]
        self._chain = ""
        self._disc_sequence = 0
        self._disc_receipts: list[dict[str, object]] = []
        self._disc_chain = ""
        try:
            self._start(entry)
            self.spec = replace(self.spec, environment_digest=_digest(self._descriptor))
            self._disc_chain = _digest(["native_disc_control", self.spec.environment_digest])
        except (OSError, ValueError, RuntimeError):
            self.close()
            raise

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            **self._descriptor,
            "environment_digest": self.spec.environment_digest,
            "spec": self.spec.as_dict(),
            "system_info": self._system_info,
        }

    @property
    def done(self) -> bool:
        return self._closed or self._steps >= self.max_steps

    def _start(self, entry: str) -> None:
        interpreter, digest = _system_interpreter()
        if interpreter != self._interpreter or digest != self._interpreter_sha256:
            raise EmulatorHostError(
                "emulator_runtime_changed", "System Python changed before native activation"
            )
        binary = shutil.which("bwrap")
        if binary is None or sys.platform != "linux":
            raise EmulatorHostError("emulator_sandbox_unavailable", "A Linux bubblewrap sandbox is required")
        self._temporary = tempfile.TemporaryDirectory(prefix="skeleton-emulator-host-")
        root = Path(self._temporary.name)
        pinned = root / "core.so"
        observed, _ = _hash_file(Path(self.core.library_path), 256 * 1024 * 1024, copy_to=pinned)
        if observed != self.core.library_sha256:
            raise EmulatorHostError("core_authority_changed", "Approved core changed while being pinned")
        system = root / "system"
        system.mkdir(mode=0o700)
        inventory = self._registry.system_inventory(self.core)
        copied_inventory = []
        for row in inventory:
            name = _name(row["name"])
            if not row["present"]:
                copied_inventory.append({"name": name, "present": False})
                continue
            destination = system / name
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            digest, size = _hash_file(
                Path(self.core.system_directory) / name, row["size"], copy_to=destination
            )
            if digest != row["sha256"] or size != row["size"]:
                raise EmulatorHostError(
                    "firmware_authority_changed", "Approved system asset changed while being pinned"
                )
            copied_inventory.append({"name": name, "present": True, "sha256": digest, "size": size})
        firmware_digest = hashlib.sha256(
            json.dumps(
                copied_inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
        ).hexdigest()
        if firmware_digest != self.core.firmware_digest:
            raise EmulatorHostError(
                "firmware_authority_changed", "Pinned system inventory differs from approval"
            )
        source = Path(__file__).parent
        for name in ("game_emulator_worker.py", "game_emulator_protocol.py"):
            digest, _ = _hash_file(source / name, 1024 * 1024, copy_to=root / name)
            if digest != self._code_bindings[name]:
                raise EmulatorHostError(
                    "emulator_code_changed", "Native worker source changed while being pinned"
                )
        pinned_content = root / "content"
        pinned_content.mkdir(mode=0o700)
        copied_bytes = 0
        for row in self._descriptor["files"]:
            if self._cancelled is not None and self._cancelled():
                raise EmulatorCancelled()
            destination = pinned_content / row["name"]
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            original = self._content_root / row["name"]
            before = original.stat(follow_symlinks=False)
            linked = False
            if before.st_uid == os.geteuid() and not before.st_mode & 0o222:
                try:
                    os.link(original, destination, follow_symlinks=False)
                    linked = True
                except OSError:
                    pass
            if linked:
                after = destination.stat(follow_symlinks=False)
                # Creating a hardlink changes ctime; content, inode and mode
                # must remain stable, then the pinned inode is hashed again.
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_mode,
                ):
                    raise EmulatorHostError(
                        "emulator_content_changed", "Readonly content inode changed while being pinned"
                    )
                digest, size = _hash_file(destination, row["size_bytes"], cancelled=self._cancelled)
            else:
                copied_bytes += row["size_bytes"]
                if (
                    copied_bytes > MAX_PRIVATE_CONTENT_COPY
                    or shutil.disk_usage(root).free < row["size_bytes"] + 32 * 1024 * 1024
                ):
                    raise EmulatorHostError(
                        "emulator_content_copy_capacity",
                        "Content requires a readonly same-filesystem pin or fits neither bounded copy nor current disk capacity",
                    )
                digest, size = _hash_file(
                    original, row["size_bytes"], copy_to=destination, cancelled=self._cancelled
                )
                destination.chmod(0o400)
            if digest != row["sha256"] or size != row["size_bytes"]:
                raise EmulatorHostError(
                    "emulator_content_changed", "Content changed while being privately pinned"
                )
        self._registry.revalidate(self.core)
        control = root / "cancel"
        control.write_bytes(b"0")
        self._cancel_file = control
        arguments = [
            binary,
            "--unshare-all",
            "--die-with-parent",
            "--clearenv",
            "--cap-drop",
            "ALL",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind-try",
            "/lib",
            "/lib",
            "--ro-bind-try",
            "/lib64",
            "/lib64",
            "--ro-bind-try",
            "/etc/ld.so.cache",
            "/etc/ld.so.cache",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            str(128 * 1024 * 1024),
            "--tmpfs",
            "/tmp",
            "--dir",
            "/app",
            "--dir",
            "/core",
            "--dir",
            "/control",
            "--ro-bind",
            str(pinned),
            "/core/core.so",
            "--ro-bind",
            str(system),
            "/system",
            "--ro-bind",
            str(pinned_content),
            "/content",
            "--ro-bind",
            str(control),
            "/control/cancel",
        ]
        for name in ("game_emulator_worker.py", "game_emulator_protocol.py"):
            arguments.extend(("--ro-bind", str(root / name), "/app/" + name))
        arguments.extend(
            (
                "--chdir",
                "/content",
                "--setenv",
                "LANG",
                "C.UTF-8",
                "--setenv",
                "HOME",
                "/tmp",
                "--setenv",
                "PATH",
                "/usr/local/bin:/usr/bin:/bin",
                "--setenv",
                "PYTHONDONTWRITEBYTECODE",
                "1",
                str(interpreter),
                "-I",
                "/app/game_emulator_worker.py",
            )
        )
        self._process = subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            close_fds=True,
            start_new_session=False,
        )
        threading.Thread(target=self._read_loop, daemon=True, name="libretro-native-replies").start()
        payload = {
            "library_path": "/core/core.so",
            "interpreter_sha256": self._interpreter_sha256,
            "library_sha256": self.core.library_sha256,
            "entrypoint": "/content/" + entry,
            "options": json.loads(self.core.options_json),
            "controller_port_devices": list(self._controller_devices),
        }
        metadata, blocks = self._exchange("initialize", payload, authority=False)
        if (
            blocks
            or metadata.get("actual_abi_version") != 1
            or not isinstance(metadata.get("system_info"), dict)
        ):
            raise EmulatorHostError("native_protocol_corrupt", "Native initialization evidence differs")
        runtime = metadata.get("worker_runtime")
        if (
            not isinstance(runtime, dict)
            or set(runtime) != {"implementation", "version", "executable_sha256"}
            or runtime["implementation"] != "cpython"
            or runtime["executable_sha256"] != self._interpreter_sha256
            or not isinstance(runtime["version"], list)
            or len(runtime["version"]) != 3
            or any(type(value) is not int or not 0 <= value <= 255 for value in runtime["version"])
        ):
            raise EmulatorHostError(
                "emulator_runtime_changed", "Actual native worker Python identity differs"
            )
        self._descriptor["worker_runtime"] = dict(runtime)
        self._descriptor["python"] = list(runtime["version"])
        self._system_info = metadata["system_info"]
        if self._system_info.get("controller_port_devices") != list(self._controller_devices):
            raise EmulatorHostError("native_device_mismatch", "Actual native controller routing differs from the pinned episode specification")
        self._registry.revalidate(self.core)

    def _read_loop(self) -> None:
        process = self._process
        try:
            while process is not None:
                result = read_packet(process.stdout)
                self._replies.put(result)
        except (OSError, ValueError, EOFError) as exc:
            try:
                self._replies.put_nowait(exc)
            except queue.Full:
                pass

    def _authority(self) -> None:
        if self._closed or self._process is None or self._process.poll() is not None:
            raise EmulatorHostError("emulator_worker_unavailable", "Native worker is no longer active")
        if self._cancelled is not None and self._cancelled():
            self.request_cancel()
            raise EmulatorCancelled()
        try:
            self._registry.revalidate(self.core)
        except ValueError:
            self.close()
            raise

    def _exchange(
        self,
        operation: str,
        payload: Mapping[str, object],
        blocks: Mapping[str, bytes] | None = None,
        *,
        authority: bool = True,
    ) -> tuple[dict[str, object], dict[str, bytes]]:
        with self._lock:
            if authority:
                self._authority()
            if self._closed or self._process is None:
                raise EmulatorHostError("emulator_worker_unavailable", "Native worker is closed")
            self._sequence += 1
            identity = self._sequence
            errors = queue.Queue(maxsize=1)

            process = self._process

            def send() -> None:
                try:
                    write_packet(
                        process.stdin,
                        {"request_id": identity, "operation": operation, "payload": dict(payload)},
                        blocks,
                    )
                except (OSError, ValueError) as exc:
                    errors.put(exc)

            threading.Thread(target=send, daemon=True, name="libretro-native-send").start()
            deadline = time.monotonic() + self.timeout_seconds
            try:
                while True:
                    if self._cancelled is not None and self._cancelled():
                        self.request_cancel()
                        raise EmulatorCancelled()
                    if not errors.empty():
                        raise EmulatorHostError(
                            "native_transport_failed", "Native worker input transport failed"
                        ) from errors.get_nowait()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise EmulatorHostError(
                            "emulator_timeout", "Native command exceeded its wall-clock budget"
                        )
                    try:
                        response = self._replies.get(timeout=min(0.05, remaining))
                    except queue.Empty:
                        continue
                    if isinstance(response, BaseException):
                        raise EmulatorHostError(
                            "emulator_worker_crashed", "Native worker closed or crashed"
                        ) from response
                    message, incoming = response
                    if message.get("request_id") != identity or type(message.get("ok")) is not bool:
                        raise EmulatorHostError(
                            "native_protocol_corrupt", "Native response request identity differs"
                        )
                    if not message["ok"]:
                        raise EmulatorHostError(
                            "native_operation_failed",
                            str(message.get("error", "Native operation failed"))[:512],
                        )
                    if set(message) != {"request_id", "ok", "payload"} or not isinstance(
                        message["payload"], dict
                    ):
                        raise EmulatorHostError("native_protocol_corrupt", "Native response schema differs")
                    if authority:
                        self._registry.revalidate(self.core)
                    return message["payload"], incoming
            except (OSError, ValueError):
                self.close()
                raise

    def request_cancel(self) -> None:
        if hasattr(self, "_cancel_file"):
            try:
                with self._cancel_file.open("r+b", buffering=0) as stream:
                    stream.write(b"1")
            except OSError:
                pass

    def _accept_frame(self, metadata: dict[str, object], blocks: dict[str, bytes]) -> dict[str, float]:
        metadata = _frame_metadata(metadata)
        width = _int(metadata.get("width"), 1, 4096, "native video width")
        height = _int(metadata.get("height"), 1, 4096, "native video height")
        pixels, audio = blocks.get("pixels"), blocks.get("audio")
        if (
            width * height > MAX_PIXELS
            or not isinstance(pixels, bytes)
            or len(pixels) != width * height * 3
            or hashlib.sha256(pixels).hexdigest() != _sha(metadata.get("pixel_sha256"))
            or not isinstance(audio, bytes)
            or len(audio) % 4
            or len(audio) > 131072 * 4
            or len(audio) // 4 != metadata["audio_frames"]
            or hashlib.sha256(audio).hexdigest() != metadata["audio_sha256"]
        ):
            raise EmulatorHostError("native_frame_corrupt", "Actual frame/audio geometry or checksum differs")
        change = (
            0.0
            if self._pixels is None or len(self._pixels) != len(pixels)
            else sum(left != right for left, right in zip(self._pixels, pixels, strict=True)) / len(pixels)
        )
        values = [value[0] for value in struct.iter_unpack("<h", audio)]
        rms = math.sqrt(sum(value * value for value in values) / len(values)) / 32768 if values else 0.0
        self._pixels, self._frame, self._audio = pixels, dict(metadata), audio
        self._audio_total += len(audio) // 4
        self._observation = {
            "screen_mean": sum(pixels) / (255 * len(pixels)),
            "visual_change": change,
            "audio_rms": rms,
            "step_fraction": self._steps / self.max_steps,
        }
        return dict(self._observation)

    def disc_status(self) -> dict[str, object]:
        """Report only core-registered disc counts/state, never filesystem paths."""
        value, blocks = self._exchange("disc_status", {})
        if blocks or not isinstance(value, dict) or set(value) != {
            "supported", "interface_version", "image_count", "image_index", "ejected"
        }:
            self.close()
            raise EmulatorHostError("native_disc_status_corrupt", "Disk status payload differs")
        if type(value["supported"]) is not bool:
            self.close()
            raise EmulatorHostError("native_disc_status_corrupt", "Native disk support flag differs")
        if not value["supported"]:
            if (value["interface_version"] is not None or value["image_count"] != 0
                or value["image_index"] is not None or value["ejected"] is not None):
                self.close()
                raise EmulatorHostError("native_disc_status_corrupt", "Absent disk capability claimed media")
        elif (
            type(value["interface_version"]) is not int
            or value["interface_version"] not in (0, 1)
            or type(value["image_count"]) is not int or not 1 <= value["image_count"] <= 32
            or type(value["image_index"]) is not int
            or not 0 <= value["image_index"] < value["image_count"]
            or type(value["ejected"]) is not bool
        ):
            self.close()
            raise EmulatorHostError("native_disc_status_corrupt", "Native disk geometry exceeds bounds")
        return dict(value)

    @_serialized_native_operation
    def swap_disc(self, image_index: int) -> dict[str, object]:
        """Bounded in-place user-directed swap of a preloaded, readonly disc."""
        if self._seed is None or self.done:
            raise EmulatorHostError("emulator_episode_inactive", "Reset before an active disc swap")
        wanted = _int(image_index, 0, 31, "native disc slot")
        previous = self.disc_status()
        if not previous["supported"] or previous["image_count"] < 2:
            raise EmulatorHostError("native_multiple_discs_unavailable", "Core has not registered multiple discs")
        if wanted >= previous["image_count"]:
            raise EmulatorHostError("native_disc_index_invalid", "Disc is not registered by the core")
        if previous["ejected"]:
            raise EmulatorHostError("native_disc_tray_open", "Core's disc tray is already open")
        if wanted == previous["image_index"]:
            return {
                "changed": False, "disc_status": previous,
                "event_chain_sha256": self._disc_chain,
                "native_emulation_advanced": False,
            }
        if self._disc_sequence >= 32:
            raise EmulatorHostError("native_disc_event_limit", "Session exceeds bounded disc changes")
        after, blocks = self._exchange("disc_swap", {"image_index": wanted})
        if blocks or not isinstance(after, dict) or set(after) != {
            "supported", "interface_version", "image_count", "image_index",
            "ejected", "previous_image_index", "changed",
        } or after["changed"] is not True or after["previous_image_index"] != previous["image_index"]:
            self.close()
            raise EmulatorHostError("native_disc_response_corrupt", "Native disc swap receipt differs")
        status = self.disc_status()
        if (not status["supported"] or status["ejected"]
            or status["image_count"] != previous["image_count"]
            or status["image_index"] != wanted
            or status["interface_version"] != previous["interface_version"]
            or any(after[key] != status[key] for key in status)):
            self.close()
            raise EmulatorHostError("native_disc_switch_unverified", "Disc status changed unexpectedly")
        receipt = {
            "schema_version": "skeleton.game.native_disc_swap_receipt.v1",
            "core_sha256": self.core.library_sha256,
            "content_digest": self._descriptor["content_digest"],
            "environment_digest": self.spec.environment_digest,
            "event_index": self._disc_sequence + 1,
            "episode_step_before_swap": self._steps,
            "previous_image_index": previous["image_index"],
            "selected_image_index": wanted,
            "registered_disc_count": status["image_count"],
            "interface_version": status["interface_version"],
            "previous_disc_chain_sha256": self._disc_chain,
            "prior_game_transition_sha256": self._chain,
            "rendered_frame_after_swap": False,
        }
        self._disc_chain = _digest(receipt)
        receipt["receipt_sha256"] = self._disc_chain
        self._disc_receipts.append(receipt)
        self._disc_sequence += 1
        self._chain = _digest(["native_disc_swap", self._chain, self._disc_chain])
        return {
            "changed": True, "disc_status": status, "receipt": receipt,
            "event_chain_sha256": self._disc_chain,
            "native_emulation_advanced": False,
        }

    @_serialized_native_operation
    def disc_receipts(self) -> dict[str, object]:
        """Local, bounded, content-free source provenance of disc operations."""
        return {
            "schema_version": "skeleton.game.native_disc_history.v1",
            "core_sha256": self.core.library_sha256,
            "content_digest": self._descriptor["content_digest"],
            "receipts": list(self._disc_receipts),
            "event_chain_sha256": self._disc_chain,
            "hardware_fidelity_verified": False,
            "model_weights_updated": False,
        }

    @_serialized_native_operation
    def reset(self, seed: int = 0) -> dict[str, float]:
        _int(seed, 0, 2**63 - 1, "episode seed")
        self._steps = 0
        self._audio_total = 0
        self._audio_generation += 1
        self._pixels = None
        self._controls = [json.loads(json.dumps(_EMPTY))]
        metadata, blocks = self._exchange("reset", {"controls": self._controls})
        observation = self._accept_frame(metadata, blocks)
        self._seed = seed
        disc = self.disc_status()
        self._chain = _digest(
            {
                "disc_event_chain_sha256": self._disc_chain if disc["supported"] else None,
                "environment_digest": self.spec.environment_digest,
                "seed": seed,
                "actual_native_reset": True,
                "frame_digest": metadata["pixel_sha256"],
                "observation": observation,
            }
        )
        return observation

    def step(self, action: str) -> EpisodeStep:
        if not isinstance(action, str) or action not in (*_ACTIONS, *_KEY_ACTIONS):
            raise EmulatorHostError("invalid_emulator_action", "Finite policy action is unavailable")
        controls = _policy_controls(action)
        return self._step([controls], action)

    def input_step(self, controls: Sequence[Mapping[str, object]]) -> EpisodeStep:
        if not isinstance(controls, (tuple, list)) or not 1 <= len(controls) <= 4:
            raise EmulatorHostError("invalid_emulator_controller", "Controller ports exceed capacity")
        controls = _controls(controls)
        exact = None
        if len(controls) == 1:
            for action in (*_ACTIONS, *_KEY_ACTIONS):
                wanted = _policy_controls(action)
                if dict(controls[0]) == wanted:
                    exact = action
                    break
        return self._step(list(controls), exact)

    @_serialized_native_operation
    def _step(self, controls: list[Mapping[str, object]], action: str | None) -> EpisodeStep:
        if self._seed is None or self.done:
            raise EmulatorHostError(
                "emulator_episode_inactive", "Reset an active native episode before stepping"
            )
        controls = _controls(controls)
        previous = self._chain
        metadata, blocks = self._exchange("step", {"frames": self.frames_per_step, "controls": controls})
        self._steps += 1
        observation = self._accept_frame(metadata, blocks)
        self._controls = json.loads(json.dumps(controls))
        rewards = {"visual_change": observation["visual_change"]}
        evidence = {
            "environment_digest": self.spec.environment_digest,
            "core_id": self.core.core_id,
            "core_sha256": self.core.library_sha256,
            "content_digest": self._descriptor["content_digest"],
            "episode_step": self._steps,
            "policy_action": action,
            "controller_digest": _digest(controls),
            "controller_only": action is None,
            "frame_digest": metadata["pixel_sha256"],
            "native_runs": metadata["runs"],
            "video_callbacks": metadata["video_callbacks"],
            "audio_frames": metadata["audio_frames"],
            "audio_sha256": metadata["audio_sha256"],
            "reward_components": rewards,
            "observation": observation,
            "previous_transition_digest": previous,
        }
        if self.disc_status()["supported"]:
            evidence["disc_event_chain_sha256"] = self._disc_chain
        self._chain = _digest(evidence)
        return EpisodeStep(
            observation,
            rewards,
            False,
            self._steps >= self.max_steps,
            {
                "evidence": evidence,
                "runtime_kind": "installed_libretro_emulator",
                "game_success_available": False,
            },
            self._chain,
        )

    def capture_training_trace(
        self, actions: Sequence[str], *, seed: int = 0,
        rights_evidence_digest: str | None = None,
    ) -> dict[str, object]:
        """Capture a real, bounded native rollout for offline review; never train/promote here."""
        return capture_emulator_trace(
            self, actions, seed=seed, rights_evidence_digest=rights_evidence_digest
        )

    def capture_controller_trace(
        self,
        controller_tape: Sequence[Sequence[Mapping[str, object]]],
        *,
        seed: int = 0,
        rights_evidence_digest: str | None = None,
    ) -> dict[str, object]:
        """Capture real multi-port button/axis/key/mouse/pointer combinations."""
        if not isinstance(controller_tape, (list, tuple)) or not 1 <= len(controller_tape) <= self.max_steps:
            raise EmulatorHostError("emulator_trace_budget", "Controller tape exceeds the episode horizon")
        return capture_emulator_trace(
            self,
            ["controller_input"] * len(controller_tape),
            seed=seed,
            rights_evidence_digest=rights_evidence_digest,
            controller_tape=controller_tape,
        )

    @staticmethod
    def audit_training_replays(traces: Sequence[Mapping[str, object]]) -> dict[str, object]:
        """Score 2–10 native replay receipts; never certify game success or weight promotion."""
        from .game_emulator_replay_audit import compare_emulator_replays

        return compare_emulator_replays(traces)

    def preview(self) -> dict[str, object] | None:
        self._authority()
        if self._pixels is None:
            return None
        raster, image = _png(self._pixels, self._frame["width"], self._frame["height"])
        sample = self._audio[-16384 * 4 :]
        return {
            "runtime_kind": "installed_libretro_emulator",
            "render_kind": "actual_native_frame_preview",
            "width": raster["width"],
            "height": raster["height"],
            "data_uri": "data:image/png;base64," + base64.b64encode(image).decode(),
            "pixel_digest": raster["pixel_digest"],
            "raster": raster,
            "source_pixel_digest": self._frame["pixel_sha256"],
            "native_runs": self._frame["runs"],
            "video_callbacks": self._frame["video_callbacks"],
            "rotation": self._frame["rotation"],
            "audio": {
                "format": "s16le",
                "stream_id": _digest([self.spec.environment_digest, self._seed, self._audio_generation]),
                "channels": 2,
                "sample_rate": self._frame["sample_rate"],
                "samples_base64": base64.b64encode(sample).decode(),
                "sample_frames": len(sample) // 4,
                "total_sample_frames": self._audio_total,
                "sample_start_frame": self._audio_total - len(sample) // 4,
                "sample_digest": hashlib.sha256(sample).hexdigest(),
                "truncated": len(sample) != len(self._audio),
                "source_digest": hashlib.sha256(self._audio).hexdigest(),
            },
            "core_id": self.core.core_id,
            "content_digest": self._descriptor["content_digest"],
            "hardware_compatibility_verified": False,
        }

    @_serialized_native_operation
    def snapshot(self) -> dict[str, object]:
        if self._seed is None:
            raise EmulatorHostError("emulator_episode_inactive", "Reset before snapshotting native state")
        capacity = (MAX_SNAPSHOT_JSON - 65536) * 3 // 4 - len(self._pixels)
        state_info, _ = self._exchange("state_info", {})
        state_size = _int(state_info.get("state_size"), 0, 2**63 - 1, "native state size")
        if not 1 <= state_size <= capacity:
            raise EmulatorHostError(
                "native_state_size_unavailable",
                "Native state and frame exceed the 8 MiB operational snapshot capacity",
            )
        metadata, blocks = self._exchange("snapshot", {"max_state_bytes": capacity})
        state = blocks.get("state")
        if (
            not isinstance(state, bytes)
            or len(state) != metadata.get("state_size")
            or not 1 <= len(state) <= MAX_STATE
            or hashlib.sha256(state).hexdigest() != metadata.get("state_sha256")
        ):
            raise EmulatorHostError("native_state_corrupt", "Native savestate identity differs")
        payload = {
            "schema_version": SCHEMA,
            "environment_digest": self.spec.environment_digest,
            "seed": self._seed,
            "steps": self._steps,
            "controls": self._controls,
            "observation": self._observation,
            "transition_digest": self._chain,
            "lifetime_audio_frames": self._audio_total,
            "audio_generation": self._audio_generation,
            "state_sha256": metadata["state_sha256"],
            "state_size": len(state),
            "state_base64": base64.b64encode(state).decode(),
            "frame": self._frame,
            "pixels_base64": base64.b64encode(self._pixels).decode(),
        }
        status = self.disc_status()
        if status["supported"]:
            payload["disc_context"] = {
                "status": status, "disc_event_chain_sha256": self._disc_chain,
            }
        if (
            len(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
            > MAX_SNAPSHOT_JSON - 256
        ):
            raise EmulatorHostError(
                "native_state_size_unavailable", "Operational snapshot encoding exceeds capacity"
            )
        return {**payload, "snapshot_digest": _digest(payload)}

    @_serialized_native_operation
    def restore(self, snapshot: Mapping[str, object]) -> dict[str, float]:
        fields = {
            "schema_version",
            "environment_digest",
            "seed",
            "steps",
            "controls",
            "observation",
            "transition_digest",
            "lifetime_audio_frames",
            "audio_generation",
            "state_sha256",
            "state_size",
            "state_base64",
            "frame",
            "pixels_base64",
            "snapshot_digest",
        }
        if (
            not isinstance(snapshot, Mapping)
            or set(snapshot) not in (fields, fields | {"disc_context"})
            or snapshot["schema_version"] != SCHEMA
            or snapshot["environment_digest"] != self.spec.environment_digest
        ):
            raise EmulatorHostError("native_state_foreign", "Native savestate schema or environment differs")
        status = self.disc_status()
        if status["supported"]:
            if snapshot.get("disc_context") != {
                "status": status, "disc_event_chain_sha256": self._disc_chain,
            }:
                raise EmulatorHostError("native_disc_state_foreign", "Savestate and current disc provenance differ")
        elif "disc_context" in snapshot:
            raise EmulatorHostError("native_disc_state_foreign", "Savestate claims unsupported disc controls")
        size = _int(snapshot["state_size"], 1, MAX_STATE, "native state size")
        frame = _frame_metadata(snapshot["frame"])
        controls = _controls(snapshot["controls"])
        steps = _int(snapshot["steps"], 0, self.max_steps, "native cursor")
        seed = _int(snapshot["seed"], 0, 2**63 - 1, "native episode seed")
        chain = _sha(snapshot["transition_digest"])
        lifetime_audio = _int(snapshot["lifetime_audio_frames"], 0, 2**63 - 1, "audio cursor")
        audio_generation = _int(snapshot["audio_generation"], 0, 2**63 - 1, "audio generation")
        observation = snapshot["observation"]
        if (
            not isinstance(observation, Mapping)
            or set(observation) != set(self.spec.observation_bins)
            or any(
                type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
                for value in observation.values()
            )
        ):
            raise EmulatorHostError("native_state_corrupt", "Native observation projection differs")
        if (
            not isinstance(snapshot["state_base64"], str)
            or len(snapshot["state_base64"]) != 4 * ((size + 2) // 3)
            or not isinstance(snapshot["pixels_base64"], str)
            or len(snapshot["pixels_base64"]) != 4 * ((frame["width"] * frame["height"] * 3 + 2) // 3)
        ):
            raise EmulatorHostError("native_state_limit", "Native savestate encoding exceeds capacity")
        if len(snapshot["state_base64"]) + len(snapshot["pixels_base64"]) > MAX_SNAPSHOT_JSON - 65536:
            raise EmulatorHostError("native_state_size_unavailable", "Operational snapshot exceeds capacity")
        payload = {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
        if _digest(payload) != _sha(snapshot["snapshot_digest"]):
            raise EmulatorHostError("native_state_corrupt", "Native savestate checksum differs")
        try:
            state = base64.b64decode(snapshot["state_base64"], validate=True)
            pixels = base64.b64decode(snapshot["pixels_base64"], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise EmulatorHostError("native_state_corrupt", "Native state encoding is invalid") from exc
        if len(state) != size or hashlib.sha256(state).hexdigest() != _sha(snapshot["state_sha256"]):
            raise EmulatorHostError("native_state_corrupt", "Native state binary identity differs")
        if hashlib.sha256(pixels).hexdigest() != frame["pixel_sha256"]:
            raise EmulatorHostError("native_state_corrupt", "Restored frame checksum differs")
        restore_metadata = {
            "controls": controls,
            "width": frame["width"],
            "height": frame["height"],
            "video_callbacks": frame["video_callbacks"],
            "runs": frame["runs"],
            "rotation": frame["rotation"],
        }
        self._exchange("restore", restore_metadata, {"state": state, "pixels": pixels})
        self._steps, self._seed = steps, seed
        self._audio_total = lifetime_audio
        self._audio_generation = audio_generation
        self._controls = controls
        self._pixels = None
        # Audio callback buffers are not savestate content. The restored state
        # has an empty PCM boundary even if the saved frame emitted audio.
        restored_frame = {
            **frame,
            "audio_frames": 0,
            "audio_available": False,
            "audio_sha256": hashlib.sha256(b"").hexdigest(),
        }
        self._accept_frame(restored_frame, {"pixels": pixels, "audio": b""})
        observation = snapshot["observation"]
        if (
            not isinstance(observation, Mapping)
            or set(observation) != set(self.spec.observation_bins)
            or any(
                type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
                for value in observation.values()
            )
        ):
            self.close()
            raise EmulatorHostError("native_state_corrupt", "Native observation projection differs")
        self._observation = dict(observation)
        self._chain = chain
        return dict(self._observation)

    def read_memory(self, region: int, offset: int, size: int) -> bytes:
        metadata, blocks = self._exchange(
            "read_memory",
            {
                "region": _int(region, 0, 3, "native region"),
                "offset": _int(offset, 0, 256 * 1024**2, "native offset"),
                "size": _int(size, 1, 1024**2, "native memory span"),
            },
        )
        memory = blocks.get("memory")
        if (
            not isinstance(memory, bytes)
            or len(memory) != size
            or metadata.get("size") != size
            or metadata.get("region") != region
            or metadata.get("offset") != offset
        ):
            raise EmulatorHostError("native_memory_corrupt", "Native memory response identity differs")
        return memory

    def close(self) -> None:
        with self._lock:
            self._closed = True
            process = self._process
            self._process = None
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None
            if self._prepared_owner is not None:
                self._prepared_owner.close()
                self._prepared_owner = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except (AttributeError, OSError, RuntimeError):
            pass


def capture_emulator_trace(
    environment: EmulatorEnvironment,
    actions: Sequence[str],
    *,
    seed: int = 0,
    rights_evidence_digest: str | None = None,
    controller_tape: Sequence[Sequence[Mapping[str, object]]] | None = None,
) -> dict[str, object]:
    """Record actual libretro frames, input, audio and hash-chained transitions.

    This is an evidence capture, *not* a proof of emulator correctness, gameplay
    success, legal ROM rights or a promoted weight update. Uses the canonical
    offline trace validator; no caller can inject observations or rewards.
    """
    if not isinstance(environment, EmulatorEnvironment):
        raise EmulatorHostError("emulator_trace_source", "An active native emulator environment is required")
    if not isinstance(actions, (list, tuple)) or not 1 <= len(actions) <= environment.max_steps:
        raise EmulatorHostError("emulator_trace_budget", "Trace actions exceed the bounded episode horizon")
    if not all(type(action) is str and action in environment.spec.actions for action in actions):
        raise EmulatorHostError("emulator_trace_action", "Trace controls must use declared policy actions")
    if controller_tape is None:
        if "controller_input" in actions:
            raise EmulatorHostError("emulator_trace_action", "Raw controller action requires an exact controller tape")
        normalized_tape = None
    else:
        if (not isinstance(controller_tape, (list, tuple))
            or len(controller_tape) != len(actions)
            or any(action != "controller_input" for action in actions)):
            raise EmulatorHostError("emulator_trace_action", "Controller tape requires exactly one raw-control action per step")
        # Validate the entire tape before resetting or executing the native core.
        normalized_tape = [_controls(ports) for ports in controller_tape]
        for ports in normalized_tape:
            for index, control in enumerate(ports):
                if environment._controller_devices[index] == "none" and (
                    control["buttons"] or any(control["axes"]) or control["keys"]
                    or any(control["mouse"]) or any(control["pointer"])
                ):
                    raise EmulatorHostError("invalid_emulator_controller", "Unconnected controller ports cannot carry input")
    _int(seed, 0, 2**63 - 1, "episode trace seed")
    if rights_evidence_digest is not None:
        _sha(rights_evidence_digest)
    environment._authority()
    initial = environment.reset(seed)
    previous = dict(initial)
    transitions = []
    rewards = []
    for index, action in enumerate(actions, 1):
        step = (
            environment.step(action)
            if normalized_tape is None
            else environment.input_step(normalized_tape[index - 1])
        )
        value = step.as_dict()
        evidence = value["info"].get("evidence")
        if not isinstance(evidence, dict):
            raise EmulatorHostError("emulator_trace_evidence", "Native trace is missing frame evidence")
        if (evidence.get("environment_digest") != environment.spec.environment_digest
            or evidence.get("core_sha256") != environment.core.library_sha256
            or evidence.get("episode_step") != index
            or evidence.get("frame_digest") != environment._frame["pixel_sha256"]
            or value["transition_digest"] != environment._chain):
            raise EmulatorHostError("emulator_trace_evidence", "Native frame/transition binding differs")
        reward_components = dict(value["reward_components"])
        row = {
            "sequence": index,
            "observation": previous,
            "action": action,
            "next_observation": dict(value["observation"]),
            "reward": value["reward"],
            "reward_components": reward_components,
            "terminated": bool(value["terminated"]),
            "truncated": index == len(actions) and not value["terminated"],
            "transition_digest": value["transition_digest"],
            "info": {
                "runtime_kind": "installed_libretro_emulator",
                "source": "actual_isolated_native_core",
                "frame_sha256": evidence["frame_digest"],
                "controls_sha256": evidence["controller_digest"],
                "previous_transition_digest": evidence["previous_transition_digest"],
                "native_runs": evidence["native_runs"],
                "video_callbacks": evidence["video_callbacks"],
                "audio_frames": evidence["audio_frames"],
                "audio_sha256": evidence["audio_sha256"],
            },
        }
        transitions.append(row)
        rewards.append(value["reward"])
        previous = dict(value["observation"])
        if value["terminated"] or value["truncated"]:
            if index != len(actions):
                raise EmulatorHostError("emulator_trace_incomplete", "Core episode ended before the declared action sequence")
            break
    spec = environment.spec.as_dict()
    descriptor = environment.descriptor
    lineage = {
        "runtime_kind": "installed_libretro_emulator",
        "core_id": environment.core.core_id,
        "core_sha256": environment.core.library_sha256,
        "content_digest": descriptor["content_digest"],
        "registry_digest": descriptor["registry_digest"],
        "firmware_digest": descriptor["firmware_digest"],
        "options_digest": descriptor["options_digest"],
        "source_code_digest": descriptor["source_code_digest"],
        "frames_per_step": environment.frames_per_step,
        "controller_port_devices": list(environment._controller_devices),
        "controller_tape_digest": _digest(normalized_tape) if normalized_tape is not None else None,
        "rights_evidence_digest": rights_evidence_digest,
        "capture_nonce": os.urandom(16).hex(),
        "capture_process_independently_attested": False,
        "rights_verified": False,
        "hardware_compatibility_verified": False,
        "game_success_verified": False,
        "production_training_admitted": False,
        "seed_semantics": "episode label; native core may ignore seed",
        "reward_semantics": "visual difference signal, not gameplay quality or victory",
    }
    episode_identity = _digest({
        "environment_digest": environment.spec.environment_digest,
        "seed": seed, "actions": list(actions),
        "end_transition_digest": environment._chain,
    })
    trace = {
        "schema_version": "skeleton.game.trace.v1",
        "environment": spec,
        "episode_id": "libretro-" + episode_identity,
        "seed": seed,
        "source_lineage": lineage,
        "transitions": transitions,
        "return": math.fsum(rewards),
        "steps": len(transitions),
    }
    trace["trace_digest"] = _digest(trace)
    from .game_learning_ingestion import _validate_trace

    return _validate_trace(trace)


def create_emulator_environment(
    target_id: str,
    *,
    core_id: str | None = None,
    expected_registry_digest: str | None = None,
    content: Mapping[str, object] | PreparedEmulatorContent | GameContentBundle | None = None,
    rom_source: bytes | None = None,
    filename: str = "game.bin",
    reader: Callable | None = None,
    max_steps: int = 512,
    frames_per_step: int = 1,
    controller_devices: Sequence[str] | None = None,
    timeout_seconds: float = 5,
    cancelled: Callable[[], bool] | None = None,
) -> EmulatorEnvironment:
    registry = GameEmulatorRegistry.from_environment()
    core = registry.resolve_core(core_id) if core_id is not None else registry.resolve(target_id)
    target = target_id.removeprefix("emulator:")
    if target not in core.target_ids:
        raise EmulatorHostError(
            "emulator_target_mismatch", "Approved core does not declare the requested target"
        )
    if expected_registry_digest is not None and core.registry_digest != _sha(expected_registry_digest):
        raise EmulatorHostError("core_authority_changed", "Pinned registry identity differs")
    return EmulatorEnvironment(
        core,
        rom_source,
        content=content,
        filename=filename,
        reader=reader,
        max_steps=max_steps,
        frames_per_step=frames_per_step,
        controller_devices=controller_devices,
        timeout_seconds=timeout_seconds,
        cancelled=cancelled,
    )
