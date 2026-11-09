"""Direct ephemeral homebrew libretro ABI smoke child, not a console emulator.

Launched only by test_game_emulator_homebrew_native_abi after compiling the
repository's tiny C fixture. No third-party ROMs, game images or network.
"""
from __future__ import annotations

import ctypes as C
import hashlib
import json
import sys
from pathlib import Path

ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16)
BATCH=C.CFUNCTYPE(C.c_size_t,C.POINTER(C.c_int16),C.c_size_t)
POLL=C.CFUNCTYPE(None)
INPUT=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)


class GameInfo(C.Structure):
    _fields_=[
        ("path",C.c_void_p),("data",C.c_void_p),
        ("size",C.c_size_t),("meta",C.c_void_p),
    ]


class InputDescriptor(C.Structure):
    _fields_=[
        ("port",C.c_uint),("device",C.c_uint),
        ("index",C.c_uint),("id",C.c_uint),
        ("description",C.c_void_p),
    ]


class SystemInfo(C.Structure):
    _fields_=[
        ("name",C.c_void_p),("version",C.c_void_p),
        ("extensions",C.c_void_p),
        ("need_fullpath",C.c_bool),("block_extract",C.c_bool),
    ]


class Geometry(C.Structure):
    _fields_=[
        ("width",C.c_uint),("height",C.c_uint),
        ("max_width",C.c_uint),("max_height",C.c_uint),
        ("aspect_ratio",C.c_float),
    ]


class Timing(C.Structure):
    _fields_=[("fps",C.c_double),("sample_rate",C.c_double)]


class AvInfo(C.Structure):
    _fields_=[("geometry",Geometry),("timing",Timing)]


def main(argv:list[str])->int:
    if len(argv)!=1:
        raise ValueError("Only exact locally compiled fixture library path is accepted")
    library=Path(argv[0]).resolve(strict=True)
    lib=C.CDLL(str(library))
    state={"pressed":False,"labels":[],"videos":[],"audio":[]}
    def environment(cmd,data):
        if cmd==10:
            return C.cast(data,C.POINTER(C.c_uint))[0]==0
        if cmd==11:
            table=C.cast(data,C.POINTER(InputDescriptor))
            for index in range(16):
                if not table[index].description:
                    break
                state["labels"].append(C.string_at(table[index].description).decode())
            return True
        return False
    def video(ptr,width,height,pitch):
        if width!=32 or height!=24 or pitch!=64:
            raise ValueError("Native callback frame geometry differs")
        state["videos"].append(C.string_at(ptr,height*pitch))
    def audio_sample(_left,_right):
        return
    def audio_batch(ptr,frames):
        if frames!=64:
            raise ValueError("Native PCM callback frame count differs")
        state["audio"].append(C.string_at(ptr,frames*4))
        return frames
    def poll():
        return
    def controller(port,device,index,button):
        return int(
            state["pressed"] and port==0
            and device==1 and index==0 and button==8
        )
    callbacks=[
        ENV(environment),VIDEO(video),AUDIO(audio_sample),
        BATCH(audio_batch),POLL(poll),INPUT(controller),
    ]
    setters=[
        ("retro_set_environment",ENV),
        ("retro_set_video_refresh",VIDEO),
        ("retro_set_audio_sample",AUDIO),
        ("retro_set_audio_sample_batch",BATCH),
        ("retro_set_input_poll",POLL),
        ("retro_set_input_state",INPUT),
    ]
    for (name,ftype),callback in zip(setters,callbacks,strict=True):
        setter=getattr(lib,name)
        setter.argtypes=[ftype]
        setter(callback)
    lib.retro_api_version.restype=C.c_uint
    assert lib.retro_api_version()==1
    lib.retro_init()
    assert state["labels"]==["Homebrew pulse","Homebrew rest"]
    system=SystemInfo()
    lib.retro_get_system_info.argtypes=[C.POINTER(SystemInfo)]
    lib.retro_get_system_info(C.byref(system))
    assert C.string_at(system.name)==b"Skeleton homebrew ABI fixture"
    assert C.string_at(system.extensions)==b"bin"
    assert not system.need_fullpath and not system.block_extract
    av=AvInfo()
    lib.retro_get_system_av_info.argtypes=[C.POINTER(AvInfo)]
    lib.retro_get_system_av_info(C.byref(av))
    assert (av.geometry.width,av.geometry.height)==(32,24)
    assert av.timing.fps==60.0 and av.timing.sample_rate==16000.0
    game_bytes=b"SKL-HOMEBREW"
    content=C.create_string_buffer(game_bytes)
    name=C.create_string_buffer(b"fixture.bin")
    descriptor=GameInfo(C.addressof(name),C.addressof(content),len(game_bytes),None)
    lib.retro_load_game.argtypes=[C.POINTER(GameInfo)]
    lib.retro_load_game.restype=C.c_bool
    assert lib.retro_load_game(C.byref(descriptor))
    lib.retro_set_controller_port_device.argtypes=[C.c_uint,C.c_uint]
    lib.retro_set_controller_port_device(0,1)
    lib.retro_run()
    assert len(state["videos"])==len(state["audio"])==1
    first=hashlib.sha256(state["videos"][-1]).hexdigest()
    state["pressed"]=True
    lib.retro_run()
    second=hashlib.sha256(state["videos"][-1]).hexdigest()
    assert first!=second
    lib.retro_serialize_size.restype=C.c_size_t
    size=lib.retro_serialize_size()
    assert size==8
    saved=C.create_string_buffer(size)
    lib.retro_serialize.argtypes=[C.c_void_p,C.c_size_t]
    lib.retro_serialize.restype=C.c_bool
    lib.retro_unserialize.argtypes=[C.c_void_p,C.c_size_t]
    lib.retro_unserialize.restype=C.c_bool
    assert lib.retro_serialize(saved,size)
    lib.retro_run()
    future_hash=hashlib.sha256(state["videos"][-1]).hexdigest()
    assert lib.retro_unserialize(saved,size)
    lib.retro_run()
    restored_hash=hashlib.sha256(state["videos"][-1]).hexdigest()
    assert future_hash==restored_hash
    assert len(state["audio"])==len(state["videos"])==4
    lib.retro_get_memory_data.argtypes=[C.c_uint]
    lib.retro_get_memory_data.restype=C.c_void_p
    lib.retro_get_memory_size.argtypes=[C.c_uint]
    lib.retro_get_memory_size.restype=C.c_size_t
    assert lib.retro_get_memory_size(0)==256
    assert lib.retro_get_memory_data(0)
    lib.retro_unload_game()
    lib.retro_deinit()
    print(json.dumps({
        "status":"real_compiled_homebrew_libretro_abi_smoke_passed",
        "actual_native_library_loaded":True,
        "libretro_api_version":1,
        "actual_core_reported_controller_descriptors":state["labels"],
        "controller_changes_native_frame":True,
        "actual_pcm_callbacks_received":len(state["audio"]),
        "actual_video_callbacks_received":len(state["videos"]),
        "native_savestate_restored_identically":True,
        "commercial_console_hardware_accuracy_qualified":False,
        "actual_commercial_rom_or_firmware_run":False,
        "model_weights_changed":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main(sys.argv[1:]))
