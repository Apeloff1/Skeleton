"""Isolated subprocess using the *actual* Skeleton NativeCore against original C.

Not a real console, commercial ROM, firmware, installed core authority,
Bubblewrap launch qualification or production AI training.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from skeleton.jeeves.game_emulator_worker import NativeCore


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
