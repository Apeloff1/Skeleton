"""Compile the original test core and run Skeleton's real ctypes NativeCore ABI.

Unlike mock callback tests, this launches compiled native C. It does not
launch the full Bubblewrap host, certify any historical console, or train AI.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURE=Path(__file__).parent/"fixtures"/"homebrew_disc_sram_libretro.c"
CHILD=Path(__file__).parent/"fixtures"/"verify_homebrew_disc_sram.py"


class CompiledHomebrewConsoleContracts(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"),"C compiler is needed for native ABI smoke")
    def test_real_compiled_libretro_disk_input_pcm_and_sram(self):
        with tempfile.TemporaryDirectory(prefix="skl-original-disc-sram-") as folder:
            parent=Path(folder)
            library=parent/"original_disc_sram_libretro.so"
            marker=parent/"original_marker.bin"
            marker.write_bytes(b"SKL-HOMEBREW")
            result=subprocess.run(
                [shutil.which("cc"),"-std=c11","-fPIC","-shared",
                 "-O2","-Wall","-Wextra","-Werror",
                 str(FIXTURE),"-o",str(library)],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,text=True,timeout=30,check=False,
            )
            self.assertEqual(result.returncode,0,result.stderr[-4000:])
            self.assertTrue(library.is_file())
            observed=subprocess.run(
                [sys.executable,str(CHILD),str(library),str(marker)],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,text=True,timeout=20,check=False,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
            self.assertEqual(observed.returncode,0,observed.stderr[-6000:])
            value=json.loads(observed.stdout)
            self.assertEqual(value["status"],"actual_compiled_original_disc_sram_abi_exercised")
            self.assertTrue(value["actual_native_shared_library_loaded"])
            self.assertTrue(value["actual_native_registered_disc_switch"])
            self.assertTrue(value["actual_native_controller_changed_frame"])
            self.assertTrue(value["actual_native_sram_survived_reset"])
            self.assertEqual(value["actual_native_save_ram_bytes_written"],256)
            self.assertEqual(value["actual_native_disc_index_after_switch"],2)
            self.assertGreaterEqual(value["actual_native_pcm_callback_frames"],64)
            self.assertFalse(value["commercial_rom_or_bios_used"])
            self.assertFalse(value["real_console_compatibility_qualified"])
            self.assertFalse(value["bubblewrap_launch_tested"])
            self.assertFalse(value["model_weights_changed"])


if __name__=="__main__":
    unittest.main()
