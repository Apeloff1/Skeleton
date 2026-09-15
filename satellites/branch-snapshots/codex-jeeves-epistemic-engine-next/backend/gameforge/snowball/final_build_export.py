#!/usr/bin/env python3
"""
Snowball Final Build & Export System
Handles final stage of Snowball: building mobile (APK) and PC (EXE) games with download capability.
"""

import os
import time
import zipfile
from typing import Dict, Any, Optional
from gameforge.snowball.snowball_step_logs import get_step_database, get_all_step_logs

class FinalBuildExporter:
    def __init__(self, output_dir: str = "/tmp/snowball_builds"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def build_android_apk(self, game_name: str, build_config: Dict) -> Optional[str]:
        """Simulate building an Android APK."""
        print(f"[FinalBuild] Building Android APK for {game_name}...")
        
        # In real implementation: use buildozer, gradle, or Godot export
        apk_filename = f"{game_name}_v1.0_{int(time.time())}.apk"
        apk_path = os.path.join(self.output_dir, apk_filename)
        
        # Create placeholder APK (zip for demo)
        with zipfile.ZipFile(apk_path, 'w') as zf:
            zf.writestr("AndroidManifest.xml", f"<manifest package='{game_name}'/>")
            zf.writestr("assets/game_data.json", str(build_config))
        
        print(f"[FinalBuild] APK created: {apk_path}")
        return apk_path

    def build_windows_exe(self, game_name: str, build_config: Dict) -> Optional[str]:
        """Simulate building a Windows EXE."""
        print(f"[FinalBuild] Building Windows EXE for {game_name}...")
        
        exe_filename = f"{game_name}_v1.0_{int(time.time())}.exe"
        exe_path = os.path.join(self.output_dir, exe_filename)
        
        # Placeholder EXE (in reality use PyInstaller, Godot export, etc.)
        with open(exe_path, "wb") as f:
            f.write(b"PLACEHOLDER_WINDOWS_EXECUTABLE_" + str(build_config).encode())
        
        print(f"[FinalBuild] EXE created: {exe_path}")
        return exe_path

    def export_builds(self, game_name: str) -> Dict[str, str]:
        """Final step of Snowball - export both mobile and PC versions."""
        # Get all previous step logs to inform the build
        all_logs = get_all_step_logs()
        
        build_config = {
            "game_name": game_name,
            "snowball_logs": all_logs,
            "timestamp": time.time()
        }
        
        apk_path = self.build_android_apk(game_name, build_config)
        exe_path = self.build_windows_exe(game_name, build_config)
        
        result = {
            "status": "completed",
            "game_name": game_name,
            "apk_path": apk_path,
            "exe_path": exe_path,
            "download_ready": True,
            "message": "Builds ready for download to device."
        }
        
        # Mark final step as complete
        final_step = get_step_database("step_7_build")
        if final_step:
            final_step.record_user_choice("build_completed", True)
            final_step.complete_step()
        
        return result

# Global exporter
final_build_exporter = FinalBuildExporter()