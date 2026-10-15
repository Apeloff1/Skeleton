"""Isolated subprocess using the *actual* Skeleton NativeCore against original C.

Not a real console, commercial ROM, firmware, installed core authority,
Bubblewrap launch qualification or production AI training.
"""
from __future__ import annotations

import hashlib
import json
import sys
import ctypes as C
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from skeleton.jeeves.game_emulator_worker import NativeCore
from skeleton.jeeves.game_emulator_timing import inspect_rgb_frame


def main(argv:list[str])->int:
    if len(argv)!=2:
        raise ValueError("Compiled homebrew fixture library and lawful local marker required")
    library=Path(argv[0]).resolve(strict=True)
    marker=Path(argv[1]).resolve(strict=True)
    if marker.read_bytes()!=b"SKL-HOMEBREW":
        raise ValueError("Expected only the original twelve-byte source marker")
    library_hash=hashlib.sha256(library.read_bytes()).hexdigest()
    core=NativeCore({
        "library_path":str(library),
        "library_sha256":library_hash,
        "entrypoint":str(marker),
        "options":{},
        "controller_port_devices":["joypad","none","none","none"],
    })
    try:
        prior=core.disk_status()
        if not prior["supported"] or prior["image_count"]!=3 or prior["image_index"]!=0:
            raise ValueError("Real compiled native core did not register three approved disc indices")
        core.core.retro_run()
        screen_zero=core.frame()[0]["pixel_sha256"]
        core.controls[0]["buttons"]=1<<8
        core.core.retro_run()
        screen_pressed=core.frame()[0]["pixel_sha256"]
        if screen_zero==screen_pressed:
            raise ValueError("Actual native controller callback did not affect frame bytes")
        before,raw=core.command("save_ram_export",{}, {})
        if before["size"]!=256 or len(raw["save_ram"])!=256:
            raise ValueError("Native SAVE_RAM capacity differs from original fixture")
        new=bytes((index*7)%256 for index in range(256))
        sha=hashlib.sha256(new).hexdigest()
        ack,_=core.command(
            "save_ram_import",{"memory_region":0,"size":256,"sha256":sha},
            {"save_ram":new},
        )
        if not ack["readback_verified"]:
            raise ValueError("Actual compiled native SRAM memory writeback failed")
        core.core.retro_reset()
        after,raw_after=core.command("save_ram_export",{}, {})
        if after["sha256"]!=sha or raw_after["save_ram"]!=new:
            raise ValueError("Compiled libretro SRAM bytes did not survive native retro_reset")
        switched=core.swap_disc(2)
        if switched["image_index"]!=2 or not switched["changed"] or switched["ejected"]:
            raise ValueError("Compiled native disk callbacks rejected eject-select-insert")
        core.core.retro_run()
        frame=core.frame()[0]
        if frame["width"]!=32 or frame["height"]!=24 or frame["audio_frames"]<64:
            raise ValueError("Compiled native frame/audio callbacks did not return actual buffers")
        # Real native frame cursor, exposed ONLY by this original test C core.
        # A pause or RGB tile audit must not call retro_run; 1 and 8 native
        # callbacks must move exactly 1 and 8 C-core state ticks respectively.
        native_cursor=core.core.skl_fixture_ticks
        native_cursor.restype=C.c_uint32
        frozen_cursor=int(native_cursor())
        rgb=core.rgb()
        inspected=inspect_rgb_frame(
            rgb,frame["width"],frame["height"],frame["pixel_sha256"],
            frame["audio_sha256"],frozen_cursor,
        )
        if int(native_cursor())!=frozen_cursor or inspected["total_tiles"]!=256:
            raise ValueError("Compiled native framebuffer inspection mutated actual core ticks")
        if inspected["tiles"][0]["tile_rgb_sha256"]!=hashlib.sha256(
            b"".join(rgb[y*frame["width"]*3:y*frame["width"]*3+6] for y in range(1))
        ).hexdigest():
            raise ValueError("Compiled first native RGB tile differs from actual pixel bytes")
        core.controls[0]["buttons"]=0
        core.core.retro_run()
        after_single=int(native_cursor())
        if after_single-frozen_cursor!=1:
            raise ValueError("Single-frame slow motion did not execute exactly one native retro_run")
        frame_after_single=core.frame()[0]
        if frame_after_single["pixel_sha256"]==frame["pixel_sha256"]:
            raise ValueError("Native frame-by-frame precision did not update original output pixels")
        for _ in range(8):
            core.core.retro_run()
        after_eight=int(native_cursor())
        if after_eight-after_single!=8:
            raise ValueError("Fast native batch did not execute exactly eight retro_run callbacks")
        report={
            "schema_version":"skeleton.game.compiled_homebrew_console_abi.v1",
            "status":"actual_compiled_original_disc_sram_abi_exercised",
            "actual_native_shared_library_loaded":True,
            "actual_native_controller_changed_frame":True,
            "actual_native_registered_disc_switch":True,
            "actual_native_disc_index_after_switch":switched["image_index"],
            "actual_native_save_ram_bytes_written":256,
            "actual_native_sram_sha256_after_reset":after["sha256"],
            "actual_native_sram_survived_reset":True,
            "actual_native_pcm_callback_frames":frame["audio_frames"],
            "compiled_core_pause_cursor_unchanged":True,
            "compiled_native_single_frame_run_count":after_single-frozen_cursor,
            "compiled_native_fast_eight_frame_run_count":after_eight-after_single,
            "compiled_original_rgb_tile_hashes_checked":inspected["total_tiles"],
            "commercial_rom_or_bios_used":False,
            "real_console_compatibility_qualified":False,
            "bubblewrap_launch_tested":False,
            "model_weights_changed":False,
        }
        print(json.dumps(report,sort_keys=True))
        return 0
    finally:
        core.close()


if __name__=="__main__":
    raise SystemExit(main(sys.argv[1:]))
