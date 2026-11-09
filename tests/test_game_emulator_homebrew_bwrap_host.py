"""Optional end-to-end Linux bwrap/worker/ABI smoke with synthetic homebrew core.

Never adds a fixture to production core IDs or exposes unauthorized ROM data.
Runs only if the host has Linux, a C compiler and Bubblewrap; otherwise the
test is *skipped*, not falsely marked as actual sandbox qualification.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from skeleton.jeeves import game_emulator_catalog as catalog
from skeleton.jeeves.game_emulator_host import create_emulator_environment

SOURCE=Path(__file__).parent/"fixtures"/"homebrew_libretro_smoke.c"
FIXTURE_CORE_ID="skl_test_only_homebrew_abi"
MARKER=b"SKL-HOMEBREW"


class NativeIsolatedHomebrewCoreContract(unittest.TestCase):
    @unittest.skipUnless(
        sys.platform.startswith("linux") and shutil.which("cc") and shutil.which("bwrap"),
        "Real native worker smoke requires Linux, cc and bubblewrap",
    )
    def test_synthetic_input_pcm_frame_and_native_state_in_bwrap(self):
        with tempfile.TemporaryDirectory(prefix="skl-native-abi-host-") as temp:
            root=Path(temp)
            core=root/"homebrew_libretro.so"
            library_build=subprocess.run(
                [
                    shutil.which("cc"),"-std=c11","-fPIC","-shared",
                    "-O2","-Wall","-Wextra","-Werror",
                    str(SOURCE),"-o",str(core),
                ],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,text=True,timeout=30,check=False,
            )
            self.assertEqual(library_build.returncode,0,library_build.stderr[-3000:])
            system=root/"system"
            system.mkdir()
            manifest=root/"registry.json"
            manifest.write_text(json.dumps({
                "schema_version":catalog.REGISTRY_SCHEMA,
                "cores":[{
                    "core_id":FIXTURE_CORE_ID,
                    "approved":True,
                    "library_path":str(core),
                    "library_sha256":hashlib.sha256(core.read_bytes()).hexdigest(),
                    "target_ids":["nes"],
                    "system_directory":str(system),
                    "options":{},
                    "firmware":[],
                }],
            },sort_keys=True))
            with (
                mock.patch.dict(
                    catalog._CORE_TARGET_GROUPS,
                    {FIXTURE_CORE_ID:("nes",)},
                ),
                mock.patch.dict(
                    catalog._CORE_CONTENT_EXTENSIONS,
                    {FIXTURE_CORE_ID:"bin"},
                ),
                mock.patch.dict(
                    "os.environ",
                    {catalog.REGISTRY_ENV:str(manifest)},
                ),
            ):
                # This identity is registered for this test process only.
                # The worker sees an exact materialized approved binary; no
                # permanent source/core mapping is added to production.
                registry=catalog.GameEmulatorRegistry.from_environment()
                with create_emulator_environment(
                    "nes",
                    core_id=FIXTURE_CORE_ID,
                    expected_registry_digest=registry.registry_digest,
                    rom_source=MARKER,
                    filename="fixture.bin",
                    max_steps=8,
                    frames_per_step=1,
                    controller_devices=["joypad"],
                    timeout_seconds=10,
                ) as native:
                    native.reset(17)
                    self.assertEqual(native._frame["width"],32)
                    self.assertEqual(native._frame["height"],24)
                    self.assertEqual(native._frame["audio_frames"],64)
                    labels=native._system_info["core_input_descriptors"]
                    self.assertEqual(
                        [row["description"] for row in labels],
                        ["Homebrew pulse","Homebrew rest"],
                    )
                    quiet=native.step("idle")
                    quiet_sha=native._frame["pixel_sha256"]
                    pulse=native.step("a")
                    pulse_sha=native._frame["pixel_sha256"]
                    self.assertNotEqual(quiet_sha,pulse_sha)
                    self.assertEqual(native._frame["audio_frames"],64)
                    self.assertNotEqual(native._frame["audio_sha256"],
                                        hashlib.sha256(b"").hexdigest())
                    snapshot=native.snapshot()
                    native.step("a")
                    forward=native._frame["pixel_sha256"]
                    native.restore(snapshot)
                    native.step("a")
                    restored=native._frame["pixel_sha256"]
                    self.assertEqual(forward,restored)
                    self.assertTrue(pulse.transition_digest)
                    self.assertFalse(native.done)
                    self.assertEqual(native.core.core_id,FIXTURE_CORE_ID)


if __name__=="__main__":
    unittest.main()
