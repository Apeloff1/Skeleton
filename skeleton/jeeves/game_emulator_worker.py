"""Standalone sandboxed libretro worker. Only the approved core uses native ABI.

This file uses only the standard library and its adjacent wire module. Native
stdout/stdin never share the protocol descriptors. A core crash is a process
failure; Python callbacks never pretend that unsupported hardware succeeded.
"""

from __future__ import annotations

import array
import ctypes as C
import hashlib
import math
import os
import resource
import sys
from pathlib import Path

if __package__:
    from .game_emulator_protocol import read_packet, write_packet
else:
    # -I deliberately excludes both cwd and the script directory. Admit only
    # this readonly directory containing the two hash-pinned worker sources.
    sys.path.insert(0, str(Path(__file__).parent))
    from game_emulator_protocol import read_packet, write_packet

MAX_PIXELS = 4_194_304
MAX_DIMENSION = 4096
MAX_RAW_VIDEO = 32 * 1024 * 1024
MAX_AUDIO_FRAMES = 131072
MAX_STATE = 64 * 1024 * 1024
MAX_ROM = 32 * 1024 * 1024
MAX_MEMORY_READ = 1024 * 1024
REQUIRED_SYMBOLS = (
    "retro_api_version",
    "retro_set_environment",
    "retro_set_video_refresh",
    "retro_set_audio_sample",
    "retro_set_audio_sample_batch",
    "retro_set_input_poll",
    "retro_set_input_state",
    "retro_init",
    "retro_deinit",
    "retro_get_system_info",
    "retro_get_system_av_info",
    "retro_set_controller_port_device",
    "retro_reset",
    "retro_run",
    "retro_serialize_size",
    "retro_serialize",
    "retro_unserialize",
    "retro_load_game",
    "retro_unload_game",
    "retro_get_memory_data",
    "retro_get_memory_size",
)
ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
BATCH = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
POLL = C.CFUNCTYPE(None)
INPUT = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
KEYBOARD = C.CFUNCTYPE(None, C.c_bool, C.c_uint, C.c_uint32, C.c_uint16)


class SystemInfo(C.Structure):
    _fields_ = [
        ("library_name", C.c_void_p),
        ("library_version", C.c_void_p),
        ("valid_extensions", C.c_void_p),
        ("need_fullpath", C.c_bool),
        ("block_extract", C.c_bool),
    ]


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_void_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_void_p)]


class InputDescriptor(C.Structure):
    """Upstream libretro retro_input_descriptor ABI, no pointer retained."""
    _fields_ = [
        ("port", C.c_uint), ("device", C.c_uint),
        ("index", C.c_uint), ("id", C.c_uint),
        ("description", C.c_void_p),
    ]


class DiskControlCallbacks(C.Structure):
    """Stable first seven pointers in libretro v0 and v1 disk control ABI.

    The v1 struct appends three fields. We intentionally read only the
    compatible subset: no dynamic paths, replacing discs, or adding content.
    """
    _fields_ = [
        ("set_eject_state", C.c_void_p),
        ("get_eject_state", C.c_void_p),
        ("get_image_index", C.c_void_p),
        ("set_image_index", C.c_void_p),
        ("get_num_images", C.c_void_p),
        ("replace_image_index", C.c_void_p),
        ("add_image_index", C.c_void_p),
    ]


class Geometry(C.Structure):
    _fields_ = [
        ("base_width", C.c_uint),
        ("base_height", C.c_uint),
        ("max_width", C.c_uint),
        ("max_height", C.c_uint),
        ("aspect_ratio", C.c_float),
    ]


class Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class AvInfo(C.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


class Variable(C.Structure):
    _fields_ = [("key", C.c_void_p), ("value", C.c_void_p)]


def _integer(value: object, lower: int, upper: int, label: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(label + " is outside its integer bounds")
    return value


def _text(pointer: int | None, maximum: int = 4096) -> str:
    if not pointer:
        return ""
    data = bytearray()
    for index in range(maximum):
        item = C.string_at(pointer + index, 1)
        if item == b"\0":
            return data.decode("utf-8", "replace")
        data.extend(item)
    raise ValueError("native text exceeds capacity")


def _hash_file(path: Path, maximum: int) -> str:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > maximum:
                raise ValueError("native file exceeds capacity")
            digest.update(chunk)
    return digest.hexdigest()


def _controls(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        raise ValueError("controller port capacity differs")
    result = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {"buttons", "axes", "keys", "mouse", "pointer"}:
            raise ValueError("controller schema differs")
        buttons = _integer(row["buttons"], 0, 65535, "joypad mask")
        axes = row["axes"]
        keys = row["keys"]
        mouse = row["mouse"]
        pointer = row["pointer"]
        if (
            not isinstance(axes, list)
            or len(axes) != 4
            or not isinstance(keys, list)
            or len(keys) > 128
            or not isinstance(mouse, list)
            or len(mouse) != 6
            or not isinstance(pointer, list)
            or len(pointer) != 3
        ):
            raise ValueError("controller input shape differs")
        axes = [_integer(item, -32768, 32767, "analog axis") for item in axes]
        keys = sorted({_integer(item, 0, 511, "keyboard key") for item in keys})
        mouse = [
            (
                _integer(item, -32768, 32767, "mouse displacement")
                if index < 2
                else _integer(item, 0, 1, "mouse button")
            )
            for index, item in enumerate(mouse)
        ]
        pointer = [
            (
                _integer(item, -32768, 32767, "pointer coordinate")
                if index < 2
                else _integer(item, 0, 1, "pointer press")
            )
            for index, item in enumerate(pointer)
        ]
        result.append({"buttons": buttons, "axes": axes, "keys": keys, "mouse": mouse, "pointer": pointer})
    return result


class NativeCore:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        library = Path(config["library_path"])
        if library.is_symlink() or _hash_file(library, 256 * 1024 * 1024) != config["library_sha256"]:
            raise ValueError("approved native core checksum differs")
        self.core = C.CDLL(str(library), mode=os.RTLD_LOCAL | os.RTLD_NOW)
        if any(not hasattr(self.core, name) for name in REQUIRED_SYMBOLS):
            raise ValueError("native core lacks required libretro symbols")
        self.pixel_format = 0
        self.rotation = 0
        self.raw_video: bytes | None = None
        self.restored_rgb: bytes | None = None
        self.video_shape = (0, 0, 0, 0)
        self.video_calls = 0
        self.runs = 0
        self.audio = bytearray()
        self.audio_frames = 0
        self.error: str | None = None
        self.shutdown = False
        self.options = dict(config["options"])
        declared_ports = config.get("controller_port_devices", ["joypad"] * 4)
        allowed_ports = {"none": 0, "joypad": 1, "mouse": 2, "keyboard": 3, "analog": 5, "pointer": 6}
        if (not isinstance(declared_ports, list) or len(declared_ports) != 4
            or any(type(item) is not str or item not in allowed_ports for item in declared_ports)):
            raise ValueError("Native controller port topology is not a supported bounded declaration")
        self.controller_port_devices = tuple(declared_ports)
        self.input_descriptors: list[dict[str, object]] = []
        self.disk_callbacks: dict[str, int] | None = None
        self.disk_interface_version: int | None = None
        self.buffers: dict[str, object] = {}
        self.keys_previous: set[int] = set()
        self.keyboard = None
        self.controls = _controls(
            [
                {
                    "buttons": 0,
                    "axes": [0, 0, 0, 0],
                    "keys": [],
                    "mouse": [0, 0, 0, 0, 0, 0],
                    "pointer": [0, 0, 0],
                }
            ]
        )
        self._loaded = False
        self._initialized = False
        self._content = None
        self._callbacks = (
            ENV(self._environment),
            VIDEO(self._video),
            AUDIO(self._sample),
            BATCH(self._batch),
            POLL(lambda: None),
            INPUT(self._input),
        )
        signatures = {
            "retro_api_version": ([], C.c_uint),
            "retro_set_environment": ([ENV], None),
            "retro_set_video_refresh": ([VIDEO], None),
            "retro_set_audio_sample": ([AUDIO], None),
            "retro_set_audio_sample_batch": ([BATCH], None),
            "retro_set_input_poll": ([POLL], None),
            "retro_set_input_state": ([INPUT], None),
            "retro_init": ([], None),
            "retro_deinit": ([], None),
            "retro_get_system_info": ([C.POINTER(SystemInfo)], None),
            "retro_get_system_av_info": ([C.POINTER(AvInfo)], None),
            "retro_set_controller_port_device": ([C.c_uint, C.c_uint], None),
            "retro_reset": ([], None),
            "retro_run": ([], None),
            "retro_serialize_size": ([], C.c_size_t),
            "retro_serialize": ([C.c_void_p, C.c_size_t], C.c_bool),
            "retro_unserialize": ([C.c_void_p, C.c_size_t], C.c_bool),
            "retro_load_game": ([C.POINTER(GameInfo)], C.c_bool),
            "retro_unload_game": ([], None),
            "retro_get_memory_data": ([C.c_uint], C.c_void_p),
            "retro_get_memory_size": ([C.c_uint], C.c_size_t),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.core, name)
            function.argtypes, function.restype = args, result
        if self.core.retro_api_version() != 1:
            raise ValueError("unsupported libretro API version")
        for name, callback in zip(
            (
                "retro_set_environment",
                "retro_set_video_refresh",
                "retro_set_audio_sample",
                "retro_set_audio_sample_batch",
                "retro_set_input_poll",
                "retro_set_input_state",
            ),
            self._callbacks,
            strict=True,
        ):
            getattr(self.core, name)(callback)
        self.system = SystemInfo()
        self.core.retro_get_system_info(C.byref(self.system))
        self.info = {
            "library_name": _text(self.system.library_name),
            "library_version": _text(self.system.library_version),
            "valid_extensions": _text(self.system.valid_extensions),
            "need_fullpath": bool(self.system.need_fullpath),
            "block_extract": bool(self.system.block_extract),
            "controller_port_devices": list(self.controller_port_devices),
        }
        self.core.retro_init()
        self._initialized = True
        entry = Path(config["entrypoint"])
        extension = entry.suffix.removeprefix(".").lower()
        if extension in {"zip", "dosz"} and not self.system.block_extract:
            raise ValueError("actual core does not declare opaque native archive loading")
        extensions = self.info["valid_extensions"].lower().split("|")
        if extensions != [""] and extension not in extensions:
            raise ValueError("content extension is not supported by the actual core")
        path = self._buffer("game_path", str(entry))
        if self.system.need_fullpath:
            game = GameInfo(path, None, 0, None)
        else:
            if entry.stat().st_size > MAX_ROM:
                raise ValueError("memory-loading core cannot admit this large content")
            data = entry.read_bytes()
            self._content = C.create_string_buffer(data)
            game = GameInfo(path, C.addressof(self._content), len(data), None)
        if not self.core.retro_load_game(C.byref(game)):
            raise ValueError("native core rejected the supplied content")
        self._loaded = True
        for port, device in enumerate(self.controller_port_devices):
            self.core.retro_set_controller_port_device(port, allowed_ports[device])
        self.av = AvInfo()
        self.core.retro_get_system_av_info(C.byref(self.av))
        self._check_av()
        # libretro cores may send descriptions before and after load_game;
        # snapshot them into wire-safe metadata only after both phases.
        self.info["core_input_descriptors"] = list(self.input_descriptors)
        self.info["core_input_descriptors_are_user_defined"] = True
        self.info["disk_control_interface_version"] = self.disk_interface_version
        self._check()

    def _buffer(self, key: str, value: str) -> int:
        if not isinstance(value, str) or len(value.encode()) > 8192 or "\0" in value:
            raise ValueError("native string capacity differs")
        previous = self.buffers.get(key)
        if previous is not None and previous.value == value.encode():
            return C.addressof(previous)
        buffer = C.create_string_buffer(value.encode())
        self.buffers[key] = buffer
        return C.addressof(buffer)

    def _check_av(self) -> None:
        timing = self.av.timing
        for value in (timing.fps, timing.sample_rate, self.av.geometry.aspect_ratio):
            if not math.isfinite(value) or value < 0:
                raise ValueError("native audiovisual metadata is not finite")
        if timing.fps > 1000 or timing.sample_rate > 384000:
            raise ValueError("native audiovisual rate exceeds capacity")

    def _check(self) -> None:
        if self.error:
            raise ValueError(self.error)
        if self.shutdown:
            raise ValueError("native core requested shutdown")

    def _environment(self, command: int, data: int) -> bool:
        try:
            command &= 0xFFFF
            if command == 7:
                self.shutdown = True
                return True
            if command in (13, 58):
                # libretro allows deregistration with NULL, e.g. on unload.
                if not data:
                    self.disk_callbacks = None
                    self.disk_interface_version = None
                    return True
                table = C.cast(data, C.POINTER(DiskControlCallbacks)).contents
                mandatory = ("set_eject_state", "get_eject_state", "get_image_index",
                             "set_image_index", "get_num_images")
                if any(not getattr(table, name) for name in mandatory):
                    return False
                self.disk_callbacks = {name: int(getattr(table, name)) for name in mandatory}
                self.disk_interface_version = 1 if command == 58 else 0
                return True
            if not data:
                return False
            if command == 57:
                C.cast(data, C.POINTER(C.c_uint))[0] = 1
                return True
            if command == 1:
                rotation = C.cast(data, C.POINTER(C.c_uint))[0]
                if rotation > 3:
                    return False
                self.rotation = rotation
                return True
            if command in (2, 3, 17, 51):
                C.cast(data, C.POINTER(C.c_bool))[0] = command in (3, 51)
                return True
            if command in (9, 19, 30, 31):
                directory = {9: "/system", 19: "/core/core.so", 30: "/core", 31: "/tmp/saves"}[command]
                C.cast(data, C.POINTER(C.c_void_p))[0] = self._buffer("directory_" + str(command), directory)
                return True
            if command == 11:
                # RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS. Observe labels,
                # never interpret them as proof of controller compatibility.
                values=C.cast(data,C.POINTER(InputDescriptor))
                descriptions=[]
                seen=set()
                for index in range(129):
                    row=values[index]
                    if not row.description:
                        break
                    if index==128:
                        return False
                    if not (row.port<4 and row.device in (1,2,3,5,6)
                            and row.index<=3 and row.id<=511):
                        return False
                    label=_text(row.description,96)
                    if not label or any(ord(c)<32 for c in label):
                        return False
                    key=(int(row.port),int(row.device),int(row.index),int(row.id))
                    if key in seen:
                        return False
                    seen.add(key)
                    descriptions.append({
                        "port":int(row.port),"device":int(row.device),
                        "index":int(row.index),"id":int(row.id),
                        "description":label,
                    })
                else:
                    return False
                self.input_descriptors=descriptions
                return True
            if command == 10:
                pixel_format = C.cast(data, C.POINTER(C.c_int))[0]
                if pixel_format not in (0, 1, 2):
                    return False
                self.pixel_format = pixel_format
                return True
            if command == 12:
                pointer = C.cast(data, C.POINTER(C.c_void_p))[0]
                if pointer:
                    self.keyboard = KEYBOARD(pointer)
                    return True
                return False
            if command == 15:
                variable = C.cast(data, C.POINTER(Variable)).contents
                key = _text(variable.key, 256)
                if key not in self.options:
                    variable.value = None
                    return False
                variable.value = self._buffer("option_" + key, self.options[key])
                return True
            if command == 16:
                variables = C.cast(data, C.POINTER(Variable))
                for index in range(129):
                    if not variables[index].key:
                        return True
                    if index == 128:
                        return False
                    key = _text(variables[index].key, 256)
                    declaration = _text(variables[index].value, 8192)
                    _, separator, choices = declaration.partition(";")
                    if not separator:
                        return False
                    values = choices.strip().split("|")
                    if key in self.options and self.options[key] not in values:
                        self.error = "operator core option is outside the actual core's choices"
                        return False
                    self.options.setdefault(key, values[0])
                # RETRO_ENVIRONMENT_SET_VARIABLES succeeded: core options are
                # now available to subsequent RETRO_ENVIRONMENT_GET_VARIABLE.
                return True
            if command == 24:
                C.cast(data, C.POINTER(C.c_uint64))[0] = sum(1 << device for device in (1, 2, 3, 5, 6))
                return True
            if command == 37:
                self.av = AvInfo()
                C.memmove(C.byref(self.av), data, C.sizeof(AvInfo))
                self._check_av()
                return True
            if command == 39:
                C.cast(data, C.POINTER(C.c_uint))[0] = 0
                return True
            return False
        except (
            ValueError,
            TypeError,
            OSError,
            OverflowError,
            KeyError,
            AttributeError,
            MemoryError,
            C.ArgumentError,
        ) as exc:
            self.error = str(exc)[:512]
            return False

    def _disk_call(self, name: str, restype, *arguments):
        if self.disk_callbacks is None or name not in self.disk_callbacks:
            raise ValueError("native_disk_control_unavailable")
        return C.CFUNCTYPE(restype, *arguments)(self.disk_callbacks[name])

    def disk_status(self) -> dict[str, object]:
        if self.disk_callbacks is None:
            return {
                "supported": False, "interface_version": None,
                "image_count": 0, "image_index": None, "ejected": None,
            }
        # Do not trust an arbitrary native library's declared capacity.
        count = int(self._disk_call("get_num_images", C.c_uint)())
        if not 1 <= count <= 32:
            raise ValueError("native_disk_count_outside_bound")
        index = int(self._disk_call("get_image_index", C.c_uint)())
        if not 0 <= index < count:
            raise ValueError("native_disk_index_outside_bound")
        ejected = bool(self._disk_call("get_eject_state", C.c_bool)())
        return {
            "supported": True, "interface_version": self.disk_interface_version,
            "image_count": count, "image_index": index, "ejected": ejected,
        }

    def swap_disc(self, index: int) -> dict[str, object]:
        """Eject -> select a core-preloaded image -> insert; abort on any error.

        There is deliberately no replace_image_index/add_image_index facility:
        all media was pinned readonly when the sandbox started. On a partial
        callback failure the worker returns an error and is torn down by host.
        """
        previous = self.disk_status()
        if not previous["supported"] or previous["image_count"] < 2:
            raise ValueError("native_multiple_discs_unavailable")
        wanted = _integer(index, 0, previous["image_count"] - 1, "selected disc index")
        if previous["ejected"]:
            raise ValueError("native_disc_tray_unexpectedly_open")
        if wanted == previous["image_index"]:
            return {**previous, "previous_image_index": wanted, "changed": False}
        eject = self._disk_call("set_eject_state", C.c_bool, C.c_bool)
        select = self._disk_call("set_image_index", C.c_bool, C.c_uint)
        if not eject(True):
            raise ValueError("native_disc_eject_rejected")
        if not self.disk_status()["ejected"]:
            raise ValueError("native_disc_eject_not_confirmed")
        if not select(wanted):
            raise ValueError("native_disc_select_rejected")
        if not eject(False):
            raise ValueError("native_disc_insert_rejected")
        current = self.disk_status()
        if current["ejected"] or current["image_index"] != wanted or current["image_count"] != previous["image_count"]:
            raise ValueError("native_disc_switch_unverified")
        self._check()
        return {**current, "previous_image_index": previous["image_index"], "changed": True}

    def _video(self, pointer: int, width: int, height: int, pitch: int) -> None:
        try:
            self.video_calls += 1
            if not pointer:
                return
            if pointer == C.c_void_p(-1).value:
                raise ValueError("hardware-rendered libretro frames are unsupported")
            bpp = 4 if self.pixel_format == 1 else 2
            if (
                not 1 <= width <= MAX_DIMENSION
                or not 1 <= height <= MAX_DIMENSION
                or width * height > MAX_PIXELS
                or not width * bpp <= pitch <= width * bpp + 8192
                or pitch * height > MAX_RAW_VIDEO
            ):
                raise ValueError("native video geometry or pitch exceeds capacity")
            self.raw_video = C.string_at(pointer, pitch * height)
            self.restored_rgb = None
            self.video_shape = (width, height, pitch, self.pixel_format)
        except (
            ValueError,
            TypeError,
            OSError,
            OverflowError,
            KeyError,
            AttributeError,
            MemoryError,
            C.ArgumentError,
        ) as exc:
            self.error = str(exc)[:512]

    def _sample(self, left: int, right: int) -> None:
        try:
            if self.audio_frames >= MAX_AUDIO_FRAMES:
                raise ValueError("native audio callback exceeds command capacity")
            self.audio.extend(int(left).to_bytes(2, "little", signed=True))
            self.audio.extend(int(right).to_bytes(2, "little", signed=True))
            self.audio_frames += 1
        except (
            ValueError,
            TypeError,
            OSError,
            OverflowError,
            KeyError,
            AttributeError,
            MemoryError,
            C.ArgumentError,
        ) as exc:
            self.error = str(exc)[:512]

    def _batch(self, pointer: object, frames: int) -> int:
        try:
            if frames > MAX_AUDIO_FRAMES - self.audio_frames or frames and not pointer:
                raise ValueError("native audio batch exceeds command capacity")
            data = C.string_at(pointer, frames * 4) if frames else b""
            if sys.byteorder != "little":
                values = array.array("h", data)
                values.byteswap()
                data = values.tobytes()
            self.audio.extend(data)
            self.audio_frames += frames
            return frames
        except (
            ValueError,
            TypeError,
            OSError,
            OverflowError,
            KeyError,
            AttributeError,
            MemoryError,
            C.ArgumentError,
        ) as exc:
            self.error = str(exc)[:512]
            return 0

    def _input(self, port: int, device: int, index: int, identity: int) -> int:
        if port < 0 or index < 0 or identity < 0 or port >= len(self.controls):
            return 0
        device &= 255
        selected = self.controller_port_devices[port]
        requested = {1: "joypad", 2: "mouse", 3: "keyboard", 5: "analog", 6: "pointer"}.get(device)
        if requested is None or selected == "none":
            return 0
        # Retro keyboard events are global, not bound to a joypad port.
        # Preserve the legacy keyboard callback path for port zero.
        if requested != selected and not (requested == "keyboard" and port == 0 and self.keyboard):
            # Analog devices may expose digital joypad buttons as well.
            if not (selected == "analog" and requested == "joypad"):
                return 0
        control = self.controls[port]
        if device == 1:
            if identity == 256:
                return C.c_int16(control["buttons"]).value
            return int(bool(control["buttons"] & (1 << identity))) if identity < 16 else 0
        if device == 5 and index < 2 and identity < 2:
            return control["axes"][index * 2 + identity]
        if device == 3:
            return int(identity in control["keys"])
        if device == 2 and identity < 6:
            return control["mouse"][identity]
        if device == 6 and index == 0 and identity < 3:
            return control["pointer"][identity]
        return 0

    def rgb(self) -> bytes:
        if self.raw_video is None:
            if self.restored_rgb is not None:
                return self.restored_rgb
            raise ValueError("actual native video is unavailable")
        width, height, pitch, pixel_format = self.video_shape
        output = bytearray(width * height * 3)
        for y in range(height):
            offset = y * width * 3
            if pixel_format == 1:
                row = self.raw_video[y * pitch : y * pitch + width * 4]
                r, g, b = (2, 1, 0) if sys.byteorder == "little" else (1, 2, 3)
                output[offset : offset + width * 3 : 3] = row[r::4]
                output[offset + 1 : offset + width * 3 : 3] = row[g::4]
                output[offset + 2 : offset + width * 3 : 3] = row[b::4]
            else:
                row = array.array("H", self.raw_video[y * pitch : y * pitch + width * 2])
                for x, value in enumerate(row):
                    red = (value >> (11 if pixel_format == 2 else 10)) & 31
                    green = (value >> 5) & (63 if pixel_format == 2 else 31)
                    blue = value & 31
                    start = offset + x * 3
                    output[start : start + 3] = bytes(
                        (red * 255 // 31, green * 255 // (63 if pixel_format == 2 else 31), blue * 255 // 31)
                    )
        return bytes(output)

    def frame(self) -> tuple[dict[str, object], dict[str, bytes]]:
        pixels = self.rgb()
        width, height, _, _ = self.video_shape
        metadata = {
            "width": width,
            "height": height,
            "format": "rgb24",
            "pixel_sha256": hashlib.sha256(pixels).hexdigest(),
            "rotation": self.rotation,
            "video_callbacks": self.video_calls,
            "runs": self.runs,
            "audio_frames": self.audio_frames,
            "audio_sha256": hashlib.sha256(self.audio).hexdigest(),
            "sample_rate": self.av.timing.sample_rate or None,
            "fps": self.av.timing.fps or None,
            "audio_available": self.audio_frames > 0,
            "shutdown": self.shutdown,
        }
        audio = bytes(self.audio)
        if len(audio) != self.audio_frames * 4:
            raise ValueError("native PCM bytes differ from libretro callback frame count")
        return metadata, {"pixels": pixels, "audio": audio}

    def command(
        self, operation: str, payload: dict[str, object], blocks: dict[str, bytes]
    ) -> tuple[dict[str, object], dict[str, bytes]]:
        if operation in ("reset", "step"):
            self.audio = bytearray()
            self.audio_frames = 0
            if operation == "reset":
                self.core.retro_reset()
                self.raw_video = None
                self.restored_rgb = None
                self.video_calls = self.runs = 0
                count = 1
                self.controls = _controls(payload["controls"])
            else:
                count = _integer(payload["frames"], 1, 60, "native frame budget")
                self.controls = _controls(payload["controls"])
            keys = set(self.controls[0]["keys"])
            if self.keyboard:
                for key in sorted(keys ^ self.keys_previous):
                    self.keyboard(key in keys, key, 0, 0)
            self.keys_previous = keys
            for _ in range(32 if operation == "reset" else count):
                if Path("/control/cancel").read_bytes()[:1] == b"1":
                    raise ValueError("emulator_cancelled")
                self.core.retro_run()
                self.runs += 1
                self._check()
                if operation == "reset" and self.raw_video is not None:
                    break
            return self.frame()
        if operation == "disc_status":
            if payload or blocks:
                raise ValueError("native_disc_status_request_requires_no_arguments")
            return self.disk_status(), {}
        if operation == "disc_swap":
            if set(payload) != {"image_index"} or blocks:
                raise ValueError("native_disc_swap_request_invalid")
            return self.swap_disc(payload["image_index"]), {}
        if operation == "state_info":
            size = self.core.retro_serialize_size()
            return {"state_size": size}, {}
        if operation == "snapshot":
            size = self.core.retro_serialize_size()
            maximum = _integer(payload["max_state_bytes"], 1, MAX_STATE, "native operational state capacity")
            if not 1 <= size <= maximum:
                raise ValueError("native_state_size_unavailable")
            buffer = C.create_string_buffer(size)
            if not self.core.retro_serialize(buffer, size):
                raise ValueError("native savestate serialization failed")
            self._check()
            return {"state_size": size, "state_sha256": hashlib.sha256(buffer.raw).hexdigest()}, {
                "state": buffer.raw
            }
        if operation == "restore":
            state = blocks.get("state", b"")
            pixels = blocks.get("pixels", b"")
            width = _integer(payload["width"], 1, MAX_DIMENSION, "restored frame width")
            height = _integer(payload["height"], 1, MAX_DIMENSION, "restored frame height")
            if width * height > MAX_PIXELS or len(pixels) != width * height * 3:
                raise ValueError("restored frame geometry differs")
            if not 1 <= len(state) <= MAX_STATE:
                raise ValueError("native restore state exceeds capacity")
            buffer = C.create_string_buffer(state)
            if not self.core.retro_unserialize(buffer, len(state)):
                raise ValueError("native savestate was rejected")
            self.controls = _controls(payload["controls"])
            self.keys_previous = set(self.controls[0]["keys"])
            self.raw_video = None
            self.restored_rgb = pixels
            self.video_shape = (width, height, width * 3, 3)
            self.video_calls = _integer(payload["video_callbacks"], 0, 2**63 - 1, "restored video cursor")
            self.runs = _integer(payload["runs"], 0, 2**63 - 1, "restored run cursor")
            self.rotation = _integer(payload["rotation"], 0, 3, "restored video rotation")
            self._check()
            return {"unserialize_succeeded": True}, {}
        if operation == "read_memory":
            region = _integer(payload["region"], 0, 3, "memory region")
            offset = _integer(payload["offset"], 0, 256 * 1024 * 1024, "memory offset")
            size = _integer(payload["size"], 1, MAX_MEMORY_READ, "memory read size")
            available = self.core.retro_get_memory_size(region)
            pointer = self.core.retro_get_memory_data(region)
            if not pointer or available > 256 * 1024 * 1024 or offset + size > available:
                raise ValueError("native memory region is unavailable or out of bounds")
            data = C.string_at(pointer + offset, size)
            return {"region": region, "offset": offset, "size": size, "region_size": available}, {
                "memory": data
            }
        if operation == "close":
            self.close()
            return {"closed": True}, {}
        raise ValueError("unsupported native operation")

    def close(self) -> None:
        if self._loaded:
            self.core.retro_unload_game()
            self._loaded = False
        if self._initialized:
            self.core.retro_deinit()
            self._initialized = False


def main() -> None:
    transport_in = os.fdopen(os.dup(0), "rb", buffering=0)
    transport_out = os.fdopen(os.dup(1), "wb", buffering=0)
    with open(os.devnull, "r+b", buffering=0) as null:
        os.dup2(null.fileno(), 0)
        os.dup2(null.fileno(), 1)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (3600, 3600))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    Path("/tmp/saves").mkdir(mode=0o700, exist_ok=True)
    core = None
    try:
        message, blocks = read_packet(transport_in)
        if (
            set(message) != {"request_id", "operation", "payload"}
            or message["request_id"] != 1
            or message["operation"] != "initialize"
            or blocks
        ):
            raise ValueError("native initialization request differs")
        interpreter_digest = _hash_file(Path(sys.executable).resolve(strict=True), 64 * 1024 * 1024)
        if interpreter_digest != message["payload"]["interpreter_sha256"]:
            raise ValueError("actual worker interpreter checksum differs")
        worker_runtime = {
            "implementation": sys.implementation.name,
            "version": list(sys.version_info[:3]),
            "executable_sha256": interpreter_digest,
        }
        core = NativeCore(message["payload"])
        write_packet(
            transport_out,
            {
                "request_id": 1,
                "ok": True,
                "payload": {
                    "system_info": core.info,
                    "actual_abi_version": 1,
                    "worker_runtime": worker_runtime,
                },
            },
        )
        sequence = 1
        while True:
            message, blocks = read_packet(transport_in)
            sequence += 1
            if (
                set(message) != {"request_id", "operation", "payload"}
                or type(message["request_id"]) is not int
                or message["request_id"] != sequence
                or not isinstance(message["payload"], dict)
            ):
                raise ValueError("native command identity/schema differs")
            payload, outgoing = core.command(message["operation"], message["payload"], blocks)
            write_packet(transport_out, {"request_id": sequence, "ok": True, "payload": payload}, outgoing)
            if message["operation"] == "close":
                break
    except EOFError:
        pass
    except (
        ValueError,
        TypeError,
        OSError,
        OverflowError,
        KeyError,
        AttributeError,
        MemoryError,
        C.ArgumentError,
    ) as exc:
        try:
            write_packet(
                transport_out,
                {"request_id": locals().get("sequence", 1), "ok": False, "error": str(exc)[:512]},
            )
        except (OSError, ValueError):
            pass
    finally:
        if core is not None:
            core.close()


if __name__ == "__main__":
    main()
