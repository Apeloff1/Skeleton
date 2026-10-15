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


DEFAULT_CORES = tuple(PINNED_CORES)
PINNED_CORES.update(
    {
        "stella2014": {
            "repository": "https://github.com/libretro/stella2014-libretro.git",
            "revision": "7d1361e407e63f29e52892655069e5fb4096e691",
            "artifact": "stella2014_libretro.so",
            "license": "stella/license.txt",
            "targets": ["atari_2600"],
            "makefile": "Makefile",
        },
        "prosystem": {
            "repository": "https://github.com/libretro/prosystem-libretro.git",
            "revision": "8a88014287c7a01cd568067e5a557d0a2b2a051f",
            "artifact": "prosystem_libretro.so",
            "license": "License.txt",
            "targets": ["atari_7800"],
            "makefile": "Makefile",
        },
        "handy": {
            "repository": "https://github.com/libretro/libretro-handy.git",
            "revision": "bc55d462f0b2d6b073ea93dc552ebd73cec60fd1",
            "artifact": "handy_libretro.so",
            "license": "lynx/license.txt",
            "targets": ["lynx"],
            "makefile": "Makefile",
            "firmware_mode": "Upstream built-in replacement/HLE with no external BIOS copied",
        },
        "mednafen_ngp": {
            "repository": "https://github.com/libretro/beetle-ngp-libretro.git",
            "revision": "a50d5ac288a81f2104ddf43195a4efdd15c72227",
            "artifact": "mednafen_ngp_libretro.so",
            "license": "COPYING",
            "targets": ["neo_geo_pocket", "neo_geo_pocket_color"],
            "makefile": "Makefile",
        },
        "mednafen_wswan": {
            "repository": "https://github.com/libretro/beetle-wswan-libretro.git",
            "revision": "4b01295838ea89e3f1355bbe4cb5cf98aa6108cd",
            "artifact": "mednafen_wswan_libretro.so",
            "license": "COPYING",
            "targets": ["wonderswan", "wonderswan_color"],
            "makefile": "Makefile",
        },
        "mednafen_vb": {
            "repository": "https://github.com/libretro/beetle-vb-libretro.git",
            "revision": "d5ae54c8e23b573a3b34e888b2d48a588027e92c",
            "artifact": "mednafen_vb_libretro.so",
            "license": "COPYING",
            "targets": ["virtual_boy"],
            "makefile": "Makefile",
        },
        "mednafen_pce_fast": {
            "repository": "https://github.com/libretro/beetle-pce-fast-libretro.git",
            "revision": "3f946f277aef3aa99a95551618bbcd1dd2bda0d9",
            "artifact": "mednafen_pce_fast_libretro.so",
            "license": "COPYING",
            "targets": ["turbografx_16"],
            "makefile": "Makefile",
        },
        "mednafen_supergrafx": {
            "repository": "https://github.com/libretro/beetle-supergrafx-libretro.git",
            "revision": "9c11dcd213a79d57d2c86313971631af801f2cdc",
            "artifact": "mednafen_supergrafx_libretro.so",
            "license": "COPYING",
            "targets": ["turbografx_16"],
            "makefile": "Makefile",
        },
        "vecx": {
            "repository": "https://github.com/libretro/libretro-vecx.git",
            "revision": "8f671cc9d737f2890c3ce19e177e2984dcae121f",
            "artifact": "vecx_libretro.so",
            "license": "LICENSE.md",
            "targets": ["vectrex"],
            "makefile": "Makefile.libretro",
            "make_variables": {"HAS_GPU": "0"},
        },
        "pokemini": {
            "repository": "https://github.com/libretro/PokeMini.git",
            "revision": "132111b76343559860532a1ccc094f93f1ed5650",
            "artifact": "pokemini_libretro.so",
            "license": "LICENSE",
            "targets": ["pokemon_mini"],
            "makefile": "Makefile.libretro",
        },
        "freeintv": {
            "repository": "https://github.com/libretro/FreeIntv.git",
            "revision": "ef3e0fe322bec62a7f916c0bb0834c08c348d0b4",
            "artifact": "freeintv_libretro.so",
            "license": "LICENSE",
            "targets": ["intellivision"],
            "makefile": "Makefile",
            "firmware": ["exec.bin", "grom.bin"],
        },
        "fuse": {
            "repository": "https://github.com/libretro/fuse-libretro.git",
            "revision": "e997e2bc32c888348f862f69f2c53babfedf7791",
            "artifact": "fuse_libretro.so",
            "license": "LICENSE",
            "targets": ["zx_spectrum"],
            "makefile": "Makefile.libretro",
        },
        "eightyone": {
            "repository": "https://github.com/libretro/81-libretro.git",
            "revision": "fa7094910d040baa5fd8b11dbf6a1a618330ecd9",
            "artifact": "81_libretro.so",
            "license": "LICENSE",
            "targets": ["zx81"],
            "makefile": "Makefile.libretro",
        },
        "atari800": {
            "repository": "https://github.com/libretro/libretro-atari800.git",
            "revision": "4e7fbc73765c1a9670c7506616046ad1d4ccda51",
            "artifact": "atari800_libretro.so",
            "license": "atari800/COPYING",
            "targets": ["atari_400_800", "atari_130xe", "atari_5200"],
            "makefile": "Makefile",
            "firmware_mode": "Upstream built-in replacement/HLE with no external BIOS copied",
        },
        "cap32": {
            "repository": "https://github.com/libretro/libretro-cap32.git",
            "revision": "2d41a1f07e654e97c4f24ab8447c3fbd7d728bc8",
            "artifact": "cap32_libretro.so",
            "license": "cap32/COPYING.txt",
            "targets": ["amstrad_cpc"],
            "makefile": "Makefile",
        },
        "crocods": {
            "repository": "https://github.com/libretro/libretro-crocods.git",
            "revision": "a9c63b29443715ae2add392010fca4eae7f93e67",
            "artifact": "crocods_libretro.so",
            "license": "LICENSE",
            "targets": ["amstrad_cpc"],
            "makefile": "Makefile",
        },
        "virtualjaguar": {
            "repository": "https://github.com/libretro/virtualjaguar-libretro.git",
            "revision": "69c5f6a44ec1f1678e040f8a449c6cebb99e0c99",
            "artifact": "virtualjaguar_libretro.so",
            "license": "LICENSE",
            "targets": ["atari_jaguar"],
            "makefile": "Makefile",
        },
        "gearcoleco": {
            "repository": "https://github.com/drhelius/Gearcoleco.git",
            "revision": "8afc7f1ccb0fb7bf4a771bcfa17a1b8002c3fe64",
            "artifact": "platforms/libretro/gearcoleco_libretro.so",
            "license": "LICENSE",
            "targets": ["colecovision"],
            "makefile": "Makefile",
            "build_directory": "platforms/libretro",
            "firmware": ["colecovision.rom"],
        },
        "neocd": {
            "repository": "https://github.com/libretro/neocd_libretro.git",
            "revision": "b1e04c738cb48a1dae0574b8877f6a116d270ca1",
            "artifact": "neocd_libretro.so",
            "license": "LICENSE.md",
            "targets": ["neo_geo_cd"],
            "makefile": "Makefile",
            "firmware_mode": "Upstream built-in replacement/HLE with no external BIOS copied",
        },
        "mednafen_pcfx": {
            "repository": "https://github.com/libretro/beetle-pcfx-libretro.git",
            "revision": "c1650bad5fbdcc3c3ccd45e29e3983e1ccf16cff",
            "artifact": "mednafen_pcfx_libretro.so",
            "license": "COPYING",
            "targets": ["pc_fx"],
            "makefile": "Makefile",
            "firmware": ["pcfx.rom"],
        },
        "opera": {
            "repository": "https://github.com/libretro/opera-libretro.git",
            "revision": "684926fe2079ba12b59d99082291c0a8fe780c67",
            "artifact": "opera_libretro.so",
            "license": "libopera/opera_arm.c",
            "targets": ["3do"],
            "makefile": "Makefile",
            "options": {"opera_bios": "opera-boot-internal"},
            "license_review": "Upstream FreeDO modified LGPL restricts commercial use; operator approval does not grant usage rights",
            "firmware_mode": "Upstream built-in replacement/HLE with no external BIOS copied",
        },
        "melonds": {
            "repository": "https://github.com/libretro/melonDS.git",
            "revision": "66b5d2634cd0a79030562811e6e05f5532f800ba",
            "artifact": "melonds_libretro.so",
            "license": "LICENSE",
            "targets": ["nintendo_ds"],
            "makefile": "Makefile",
            "make_variables": {"HAVE_OPENGL": "0", "HAVE_OPENGLES3": "0", "LIBS": "-lm -lpthread -lrt"},
            "options": {
                "melonds_console_mode": "DS",
                "melonds_boot_directly": "enabled",
                "melonds_threaded_renderer": "disabled",
            },
            "firmware_mode": "Pinned upstream FreeBIOS and generated DS firmware; DSi is excluded",
        },
        "desmume": {
            "repository": "https://github.com/libretro/desmume.git",
            "revision": "95b4d798731caa809125b6c3c11d17cc332ff6ef",
            "artifact": "desmume/src/frontend/libretro/desmume_libretro.so",
            "license": "license.txt",
            "targets": ["nintendo_ds"],
            "makefile": "Makefile.libretro",
            "build_directory": "desmume/src/frontend/libretro",
        },
        "picodrive": {
            "repository": "https://github.com/libretro/picodrive.git",
            "revision": "1890c2932234c9d30f4cd3851d02228baae8f09e",
            "artifact": "picodrive_libretro.so",
            "license": "COPYING",
            "targets": ["genesis", "master_system", "sega_32x"],
            "makefile": "Makefile.libretro",
            "submodules": True,
        },
        "dosbox_pure": {
            "repository": "https://github.com/schellingb/dosbox-pure.git",
            "revision": "6108e45e5f1c4ba7d66f32aa109027afa67d74a9",
            "artifact": "dosbox_pure_libretro.so",
            "license": "LICENSE",
            "targets": ["dos_8086", "dos_vga", "dos_cga", "dos_ega", "dos_vesa"],
            "makefile": "Makefile",
        },
        "parallel_n64": {
            "repository": "https://github.com/libretro/parallel-n64.git",
            "revision": "a8280501a71c1bcd4c85c5b8bfe75cfa62cd6127",
            "artifact": "parallel_n64_libretro.so",
            "license": "mupen64plus-core/LICENSES",
            "targets": ["nintendo_64"],
            "makefile": "Makefile",
            "make_variables": {
                "HAVE_OPENGL": "0",
                "HAVE_GLIDE64": "0",
                "HAVE_GLIDEN64": "0",
                "HAVE_GLN64": "0",
                "HAVE_RICE": "0",
                "HAVE_PARALLEL": "0",
                "HAVE_PARALLEL_RSP": "0",
                "WITH_DYNAREC": "0",
            },
            "options": {
                "parallel-n64-gfxplugin": "angrylion",
                "parallel-n64-cpucore": "pure_interpreter",
                "parallel-n64-angrylion-multithread": "off",
            },
            "build_dependency": "Installed OpenGL development headers are required by upstream declarations even in this software-renderer build",
        },
        "fbneo": {
            "repository": "https://github.com/libretro/FBNeo.git",
            "revision": "abe41e850b515c4ffc4dca054d1d61b828e9200c",
            "artifact": "src/burner/libretro/fbneo_libretro.so",
            "license": "src/license.txt",
            "targets": ["neo_geo"],
            "makefile": "Makefile",
            "build_directory": "src/burner/libretro",
            "firmware": ["neogeo.zip"],
            "license_review": "Retain and respect upstream FBNeo noncommercial restrictions; core installation grants no game/firmware rights",
        },
        "ppsspp": {
            "repository": "https://github.com/hrydgard/ppsspp.git",
            "revision": "e26225c99b401f259a670e45d25be4f4615bdbc5",
            "artifact": "core-build/lib/ppsspp_libretro.so",
            "license": "LICENSE.TXT",
            "targets": ["psp", "psp_go", "psp_street"],
            "build_kind": "cmake",
            "cmake_target": "ppsspp_libretro",
            "cmake_options": {
                "LIBRETRO": "ON",
                "UNITTEST": "OFF",
                "HEADLESS": "OFF",
                "ATLAS_TOOL": "OFF",
                "NO_OPENGL": "OFF",
                "OpenGL_GL_PREFERENCE": "LEGACY",
                "ARM_NO_VULKAN": "ON",
                "USING_X11_VULKAN": "OFF",
                "USE_FFMPEG": "OFF",
                "USE_DISCORD": "OFF",
                "USE_MINIUPNPC": "OFF",
                "USE_CCACHE": "OFF",
                "USE_SYSTEM_LIBPNG": "OFF",
                "CMAKE_BUILD_TYPE": "Release",
            },
            "submodules": True,
            "submodule_paths": [
                "libretro/libretro-common",
                "ext/armips",
                "ext/glslang",
                "ext/SPIRV-Cross",
                "ext/rapidjson",
                "ext/zstd",
                "ext/cpu_features",
                "ext/rcheevos",
                "ext/libchdr",
                "ext/lua",
                "ext/aemu_postoffice",
                "ext/OpenXR-SDK",
                "ext/miniupnp",
            ],
            "options": {"ppsspp_backend": "none", "ppsspp_software_rendering": "enabled"},
            "system_assets": {"assets": "PPSSPP"},
            "operator_opengl_library": True,
            "build_dependency": "Operator-installed OpenGL development headers and library; runtime explicitly selects the software context",
            "firmware_mode": "Upstream replacement PSP firmware/assets; no external proprietary BIOS installed",
            "feature_limits": "Software-only renderer; no FFmpeg/video decoding, network, achievements or commercial game compatibility qualification",
        },
        "flycast": {
            "repository": "https://github.com/libretro/flycast.git",
            "revision": "6b41116a315bc372d6f813439e1bd04a57718b1c",
            "artifact": "flycast_libretro.so",
            "license": "LICENSE",
            "targets": ["dreamcast"],
            "makefile": "Makefile",
            "make_variables": {"GL_LIB": "-l:libGL.so.1", "ENABLE_MODEM": "0", "HAVE_OPENMP": "0"},
            "build_include_variable": "MFLAGS",
            "options": {"flycast_use_real_bios": "disabled"},
            "candidate_only": True,
            "unavailable_requirements": [
                "An isolated approved hardware-rendering context is not implemented by this host"
            ],
            "build_dependency": "Operator-installed OpenGL development headers and libGL.so.1",
            "firmware_mode": "Upstream Dreamcast HLE; no external proprietary BIOS installed; Naomi and Atomiswave excluded",
        },

        "a5200": {
            "repository": "https://github.com/libretro/a5200.git",
            "revision": "40c6f2f1ad4a3145b328d5baaf010fae6c7e752b",
            "artifact": "a5200_libretro.so",
            "license": "License.txt",
            "targets": ["atari_5200"],
            "makefile": "Makefile",
            "firmware": ["5200.rom"],
            "firmware_mode": "External operator-supplied Atari 5200 BIOS only; no BIOS is fetched",
        },
        "mupen64plus_next": {
            "repository": "https://github.com/libretro/mupen64plus-libretro-nx.git",
            "revision": "12edd2c74a517ff86dfa8cfc71ad75e4c10486d5",
            "artifact": "mupen64plus_next_libretro.so",
            "license": "LICENSE",
            "targets": ["nintendo_64"],
            "makefile": "Makefile",
            "make_variables": {"WITH_DYNAREC": "", "HAVE_PARALLEL_RSP": "0", "HAVE_PARALLEL_RDP": "0"},
            "candidate_only": True,
            "unavailable_requirements": ["Software-only framebuffer operation has not been qualified in the isolated host; GPU context is unavailable"],
        },
        "nestopia": {
            "repository": "https://github.com/libretro/nestopia.git",
            "revision": "06a8949e0b3cf60e3a38a374b1426bf40fccb9a0",
            "artifact": "libretro/nestopia_libretro.so",
            "license": "COPYING",
            "targets": ["nes"],
            "build_directory": "libretro",
            "makefile": "Makefile",
            "feature_limits": "NES cartridges only; Famicom Disk System BIOS is not bundled or approved",
        },
        "mesen": {
            "repository": "https://github.com/libretro/mesen.git",
            "revision": "0102910c39ad1a62bc3f784466f3f67ca9eae335",
            "artifact": "Libretro/mesen_libretro.so",
            "license": "LICENSE",
            "targets": ["nes"],
            "build_directory": "Libretro",
            "makefile": "Makefile",
            "feature_limits": "NES cartridge scope only; no FDS firmware approved",
        },
        "vba_next": {
            "repository": "https://github.com/libretro/vba-next.git",
            "revision": "788192f215ad0a1413f1625b40ebba3423fa0ade",
            "artifact": "vba_next_libretro.so",
            "license": "LICENSE",
            "targets": ["game_boy_advance", "game_boy_micro", "game_boy_player"],
            "makefile": "Makefile.libretro",
            "feature_limits": "GBA cartridge scope; hardware accessories and original BIOS execution are not certified",
        },
        "fmsx": {
            "repository": "https://github.com/libretro/fmsx-libretro.git",
            "revision": "4de11755ce4f196ac1c8a7bb20bb4eccbc87a7d4",
            "artifact": "fmsx_libretro.so",
            "license": "LICENSE",
            "targets": ["msx1", "msx2"],
            "makefile": "Makefile",
            "candidate_only": True,
            "unavailable_requirements": ["Exact required MSX system ROM inventory and core boot behavior are not qualified; operator must inspect legitimately owned firmware"],
        },
        "bluemsx": {
            "repository": "https://github.com/libretro/blueMSX-libretro.git",
            "revision": "e3086eb5d36d77fa11704cf53dc176686e70127d",
            "artifact": "bluemsx_libretro.so",
            "license": "license.txt",
            "targets": ["msx1", "msx2", "msx_turbo_r"],
            "makefile": "Makefile.libretro",
            "system_assets": {"system/bluemsx": "bluemsx"},
            "candidate_only": True,
            "unavailable_requirements": ["Bundled C-BIOS source assets must be license-reviewed and core system-directory discovery qualified before approval"],
        },
        "px68k": {
            "repository": "https://github.com/libretro/px68k-libretro.git",
            "revision": "0ad84d7058a12b7db4f7f7a906e87fad4e2f26f6",
            "artifact": "px68k_libretro.so",
            "license": "COPYING",
            "targets": ["sharp_x68000"],
            "makefile": "Makefile.libretro",
            "firmware": ["iplrom.dat", "cgrom.dat"],
            "firmware_mode": "Exact operator-owned IPL and character ROMs; no firmware is fetched",
        },
        "vice_x64": {
            "repository": "https://github.com/libretro/vice-libretro.git",
            "revision": "f63b56688f3133a2bb17499db9eebb7ab81df5f5",
            "artifact": "vice_x64_libretro.so",
            "license": "COPYING",
            "targets": ["commodore_64"],
            "makefile": "Makefile",
            "make_variables": {"EMUTYPE": "x64"},
            "candidate_only": True,
            "unavailable_requirements": ["VICE system ROM assets have not been operator-admitted or qualified"],
        },
        "vice_x64sc": {
            "repository": "https://github.com/libretro/vice-libretro.git",
            "revision": "f63b56688f3133a2bb17499db9eebb7ab81df5f5",
            "artifact": "vice_x64sc_libretro.so",
            "license": "COPYING",
            "targets": ["commodore_64"],
            "makefile": "Makefile",
            "make_variables": {"EMUTYPE": "x64sc"},
            "candidate_only": True,
            "unavailable_requirements": ["VICE system ROM assets have not been operator-admitted or qualified"],
        },
    }
)


def _environment(*, network: bool = False):
    # No inherited provider/Mongo credentials, user git configuration, dynamic
    # loader overrides, compiler injection flags or credential helpers.
    result = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "SOURCE_DATE_EPOCH": "0",
    }
    if network:
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "CURL_CA_BUNDLE",
            "GIT_SSL_CAINFO",
        ):
            if name in os.environ:
                result[name] = os.environ[name]
    return result


def _run(command: list[str], *, cwd: Path, log: Path, timeout: int, network: bool = False) -> str:
    with log.open("ab") as stream:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=_environment(network=network),
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
    from skeleton.jeeves.game_emulator_catalog import _read_file, _safe_path

    _private_directory(destination)
    if not (source / mandatory).is_file():
        raise ValueError("Pinned upstream core license is missing")
    candidates, total = [source / mandatory], 0
    for folder, directories, files in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name != ".git"]
        for filename in files:
            if filename.casefold().startswith(("license", "copying", "copyright")):
                candidate = Path(folder) / filename
                if candidate not in candidates:
                    candidates.append(candidate)
                if len(candidates) > 256:
                    raise ValueError("Upstream license inventory exceeds its bound")
    copied = []
    for path in sorted(candidates):
        actual_path = path
        alias_target = None
        if path.is_symlink():
            actual_path = path.resolve(strict=True)
            if not actual_path.is_relative_to(source):
                raise ValueError("Upstream license alias escapes the pinned source root")
            alias_target = str(actual_path.relative_to(source))
        _safe_path(str(actual_path))
        if actual_path.stat().st_size == 0:
            if path == source / mandatory:
                raise ValueError("Pinned upstream mandatory license is empty")
            copied.append(
                {
                    "source_path": str(path.relative_to(source)),
                    "empty_notice": True,
                    "sha256": hashlib.sha256(b"").hexdigest(),
                }
            )
            continue
        data = _read_file(actual_path, 1024 * 1024)
        total += len(data)
        if total > 8 * 1024 * 1024:
            raise ValueError("Upstream license bytes exceed their aggregate bound")
        relative = str(path.relative_to(source))
        name = hashlib.sha256(relative.encode()).hexdigest()[:16] + "-" + path.name
        _write_once(destination / name, data)
        copied.append(
            {
                "source_path": relative,
                "installed_name": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "source_alias_target": alias_target,
            }
        )
    return copied


def _system_assets(source: Path, system: Path, folders: dict[str, str]):
    from skeleton.jeeves.game_emulator_catalog import (
        _content_name,
        _read_file,
        _safe_path,
    )

    copied, total = [], 0
    for source_folder, destination_folder in sorted(folders.items()):
        origin = source / _content_name(source_folder)
        destination_prefix = _content_name(destination_folder)
        _safe_path(str(origin))
        if not origin.is_dir():
            raise ValueError("Pinned upstream runtime assets are unavailable")
        for folder, directories, files in os.walk(origin, followlinks=False):
            for directory in directories:
                _safe_path(str(Path(folder) / directory))
            for filename in sorted(files):
                path = Path(folder) / filename
                relative = _content_name(destination_prefix + "/" + path.relative_to(origin).as_posix())
                if len(relative.split("/")) > 8 or len(copied) >= 1024:
                    raise ValueError("Pinned runtime asset inventory exceeds the registry bound")
                data = _read_file(path, 64 * 1024 * 1024)
                total += len(data)
                if total > 64 * 1024 * 1024:
                    raise ValueError("Pinned runtime asset bytes exceed the registry bound")
                destination = system / relative
                _private_directory(destination.parent)
                _write_once(destination, data)
                copied.append(
                    {
                        "source_path": str(path.relative_to(source)),
                        "name": relative,
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
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
    if args.all_cores and args.core:
        raise ValueError("--all-cores and individual --core selection are mutually exclusive")
    selected = list(PINNED_CORES) if args.all_cores else (args.core or list(DEFAULT_CORES))
    if len(selected) != len(set(selected)):
        raise ValueError("Core selection cannot repeat")
    records, failures = [], []

    def _install_one(identity):
        pin = PINNED_CORES[identity]
        directory = args.source_root / identity
        log = args.install_root / "logs" / (identity + ".log")
        if not directory.exists():
            if not args.fetch_sources:
                raise ValueError(
                    "Pinned source is absent; explicitly select --fetch-sources to acquire public source"
                )
            _run(
                [
                    "/usr/bin/git",
                    "clone",
                    "--depth",
                    "1",
                    "--no-tags",
                    "--no-checkout",
                    "--",
                    pin["repository"],
                    str(directory),
                ],
                cwd=args.source_root,
                log=log,
                timeout=args.timeout,
                network=True,
            )
            _run(
                ["/usr/bin/git", "fetch", "--depth", "1", "origin", pin["revision"]],
                cwd=directory,
                log=log,
                timeout=args.timeout,
                network=True,
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
        if pin.get("submodules") and not args.adopt_built:
            if not args.fetch_sources:
                raise ValueError("Pinned submodule acquisition requires explicit --fetch-sources")
            _run(
                [
                    "/usr/bin/git",
                    "-c",
                    "protocol.file.allow=never",
                    "-c",
                    "protocol.ext.allow=never",
                    "submodule",
                    "update",
                    "--init",
                    "--recursive",
                    "--depth",
                    "1",
                    "--",
                    *pin.get("submodule_paths", []),
                ],
                cwd=directory,
                log=log,
                timeout=args.timeout,
                network=True,
            )
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
        build_command.extend(key + "=" + value for key, value in pin.get("make_variables", {}).items())
        if args.build_include:
            _safe_path(str(args.build_include))
            if not args.build_include.is_dir():
                raise ValueError("Explicit operator build include path must be a safe directory")
            build_command.append(
                pin.get("build_include_variable", "CPPFLAGS") + "=-I" + str(args.build_include)
            )
        configuration_command = None
        if pin.get("build_kind") == "cmake":
            cmake = args.cmake_binary or Path("/usr/bin/cmake")
            if not args.adopt_built:
                _safe_path(str(cmake))
                if not cmake.is_file() or not os.access(cmake, os.X_OK):
                    raise ValueError(
                        "CMake compilation requires an explicitly installed binary; this command never installs build tools"
                    )
            build_directory = directory
            configuration_command = [
                str(cmake),
                "-S",
                str(directory),
                "-B",
                str(directory / "core-build"),
            ]
            cmake_options = pin.get(
                "cmake_options",
                {
                    "BUILD_LIBRETRO": "ON",
                    "BUILD_QT": "OFF",
                    "BUILD_SDL": "OFF",
                    "BUILD_TEST": "OFF",
                    "USE_FFMPEG": "OFF",
                    "USE_LIBZIP": "OFF",
                    "USE_SQLITE3": "OFF",
                },
            )
            configuration_command.extend("-D" + key + "=" + value for key, value in cmake_options.items())
            if pin.get("operator_opengl_library") and args.opengl_library:
                _safe_path(str(args.opengl_library))
                if not args.opengl_library.is_file():
                    raise ValueError("Explicit installed OpenGL library must be a safe regular file")
                configuration_command.append("-DOPENGL_LIBRARIES=" + str(args.opengl_library))
                configuration_command.append("-DOPENGL_gl_LIBRARY=" + str(args.opengl_library))
            if args.build_include:
                configuration_command.extend(
                    [
                        "-DCMAKE_C_FLAGS=-I" + str(args.build_include),
                        "-DCMAKE_CXX_FLAGS=-I" + str(args.build_include),
                    ]
                )
                if pin.get("operator_opengl_library"):
                    configuration_command.append("-DOPENGL_INCLUDE_DIR=" + str(args.build_include))
            build_command = [
                str(cmake),
                "--build",
                str(directory / "core-build"),
                "--target",
                pin.get("cmake_target", "mgba_libretro"),
                "-j",
                str(args.jobs),
            ]
        if not args.adopt_built:
            if configuration_command:
                _run(configuration_command, cwd=directory, log=log, timeout=args.timeout)
            else:
                _run(
                    [*build_command, "clean"],
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
        system_assets = _system_assets(directory, system, pin.get("system_assets", {}))
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
            "submodule_identities": (
                _git(["submodule", "status", "--recursive"], directory).splitlines()
                if pin.get("submodules")
                else []
            ),
            "firmware_requirements": pin.get("firmware", []),
            "feature_limits": pin.get("feature_limits"),
            "unavailable_requirements": pin.get("unavailable_requirements", []),
            "build_dependency": pin.get("build_dependency"),
            "explicit_build_include": str(args.build_include) if args.build_include else None,
            "operator_opengl_library": (
                {
                    "path": str(args.opengl_library),
                    "sha256": hashlib.sha256(
                        _read_file(args.opengl_library, MAX_LIBRARY_BYTES, trusted=True)
                    ).hexdigest(),
                }
                if pin.get("operator_opengl_library") and args.opengl_library
                else None
            ),
            "declared_submodule_paths": pin.get("submodule_paths", []),
            "firmware_mode": pin.get("firmware_mode", "Operator supplied external files only if declared"),
            "license_review": pin.get(
                "license_review", "Operator must respect retained upstream license terms"
            ),
            "licenses": licenses,
            "upstream_runtime_assets": system_assets,
            "bios_installed": False,
            "sega_cd_available": False,
            "execution_checked": False,
            "sandbox_readiness": "requires_bwrap_user_namespace_admission_at_execution",
            "production_promotion_authorized": False,
        }
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
        missing = []
        for name in pin.get("firmware", []):
            invocation.extend(["--firmware", name])
            if not (system / name).is_file():
                missing.append(name)
        if missing or pin.get("candidate_only"):
            invocation.append("--defer-approval")
        record["approval_status"] = (
            "candidate_firmware_missing"
            if missing
            else (
                "candidate_runtime_requirements"
                if pin.get("candidate_only")
                else "operator_approved_installation"
            )
        )
        record["missing_firmware"] = missing
        with contextlib.redirect_stdout(io.StringIO()):
            admission_code = configure_registry(invocation)
        if admission_code != 0:
            raise ValueError("Compiled core was not admitted to the explicit operator registry")
        encoded = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
        identity_path = (
            args.install_root
            / "identities"
            / (identity + "-" + hashlib.sha256(encoded).hexdigest() + ".json")
        )
        _write_once(identity_path, encoded)
        return record

    for identity in selected:
        try:
            records.append(_install_one(identity))
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            if not args.continue_on_error:
                raise
            failures.append({"core_id": identity, "error_type": type(exc).__name__, "message": str(exc)})
    registry = GameEmulatorRegistry(args.install_root / "cores.json")
    return {
        "status": "partial_core_installation" if failures else "compiled_artifacts_installed",
        "registry_digest": registry.registry_digest,
        "registry_path": str(args.install_root / "cores.json"),
        "environment_variable": "SKL_GAME_EMULATOR_REGISTRY",
        "cores": records,
        "selected_count": len(selected),
        "installed_count": len(records),
        "failed_count": len(failures),
        "failures": failures,
        "execution_checked": False,
        "tests_run": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--install-root", type=Path)
    parser.add_argument("--core", action="append", choices=sorted(PINNED_CORES))
    parser.add_argument("--all-cores", action="store_true", help="Explicitly select every pinned build recipe")
    parser.add_argument("--continue-on-error", action="store_true", help="Attempt remaining selected cores after a recorded per-core failure; return nonzero if any failed")
    parser.add_argument("--list-recipes", action="store_true", help="Read-only pinned recipe inventory; no downloads, builds or registry writes")
    parser.add_argument("--fetch-sources", action="store_true")
    parser.add_argument(
        "--adopt-built", action="store_true", help="Inspect/install already compiled pinned source artifacts"
    )
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--cmake-binary",
        type=Path,
        help="Explicit operator-installed native CMake binary for CMake recipes",
    )
    parser.add_argument(
        "--build-include",
        type=Path,
        help="Explicit operator-installed build headers; no dependency acquisition is performed",
    )
    parser.add_argument(
        "--opengl-library",
        type=Path,
        help="Explicit canonical installed OpenGL library for software-fallback recipes; no runtime rendering permission is granted",
    )
    args = parser.parse_args(argv)
    if args.list_recipes:
        if args.fetch_sources or args.adopt_built or args.continue_on_error:
            parser.error("--list-recipes must be read-only")
        if args.all_cores and args.core:
            parser.error("--all-cores and --core cannot be combined")
        selected = list(PINNED_CORES) if args.all_cores else (args.core or list(PINNED_CORES))
        print(json.dumps({
            "schema_version": "skeleton.game.emulator_recipes.v1",
            "recipe_count": len(selected),
            "default_bootstrap_count": len(DEFAULT_CORES),
            "recipes": [{
                "core_id": name,
                "source_repository": PINNED_CORES[name]["repository"],
                "source_revision": PINNED_CORES[name]["revision"],
                "targets": PINNED_CORES[name]["targets"],
                "candidate_only": bool(PINNED_CORES[name].get("candidate_only")),
                "required_firmware": PINNED_CORES[name].get("firmware", []),
                "requirements": PINNED_CORES[name].get("unavailable_requirements", []),
            } for name in selected],
            "compiled_or_installed": False,
        }, indent=2))
        return 0
    if args.source_root is None or args.install_root is None:
        parser.error("--source-root and --install-root are required for installation")
    if not 1 <= args.jobs <= 8 or not 30 <= args.timeout <= 3600:
        parser.error("jobs must be 1..8 and command timeout 30..3600 seconds")
    try:
        result = install(args)
        print(json.dumps(result, indent=2))
        return 2 if result["failed_count"] else 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "installation_rejected", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
