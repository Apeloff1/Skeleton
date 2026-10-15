"""Compile and *actually execute* tiny lawful C libretro ABI smoke in child process.

A real native shared library is compiled from tracked homebrew fixture
source, exercises controller/video/audio/state callbacks, and is discarded.
No commercial games/ROMs/BIOS, live Linux Bubblewrap host or trained model.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURE=Path(__file__).parent/"fixtures"/"homebrew_libretro_smoke.c"
CHILD=Path(__file__).parent/"fixtures"/"verify_homebrew_libretro_smoke.py"


class NativeCompiledLibretroAbiContracts(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler is required to qualify actual libretro callbacks")
    def test_compile_load_and_exercise_native_callbacks_and_savestate(self):
        with tempfile.TemporaryDirectory(prefix="skl-homebrew-libretro-") as temporary:
            library=Path(temporary)/"homebrew_smoke_libretro.so"
            build=subprocess.run(
                [
                    shutil.which("cc"),"-std=c11","-fPIC","-shared",
                    "-O2","-Wall","-Wextra","-Werror",
                    str(FIXTURE),"-o",str(library),
                ],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,text=True,timeout=30,check=False,
            )
            self.assertEqual(build.returncode,0,build.stderr[-3000:])
            self.assertTrue(library.is_file())
            self.assertGreater(library.stat().st_size,1000)
            process=subprocess.run(
                [sys.executable,str(CHILD),str(library)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                text=True,timeout=15,check=False,
            )
            self.assertEqual(process.returncode,0,process.stderr[-5000:])
            result=json.loads(process.stdout)
            self.assertEqual(result["status"],
                             "real_compiled_homebrew_libretro_abi_smoke_passed")
            self.assertTrue(result["actual_native_library_loaded"])
            self.assertTrue(result["controller_changes_native_frame"])
            self.assertTrue(result["native_savestate_restored_identically"])
            self.assertEqual(result["actual_pcm_callbacks_received"],4)
            self.assertEqual(result["actual_video_callbacks_received"],4)
            self.assertFalse(result["actual_commercial_rom_or_firmware_run"])
            self.assertFalse(result["commercial_console_hardware_accuracy_qualified"])
            self.assertFalse(result["model_weights_changed"])


if __name__=="__main__":
    unittest.main()
