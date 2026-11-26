#!/usr/bin/env python3
"""Offline internal build: deterministic ZIP with a real reference game loop."""
from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
from typing import Any

from core.exec_guard import execution_disabled_message, require_execution_allowed
from gameforge.workflow.portable_runtime import campaign_from_game_data, canonical, digest, smoke

MAX_GAME_DATA_BYTES = 2 * 1024 * 1024
MAX_HISTORY = 128


class InternalBuildSystem:
    """Package a source-level playable prototype, not a signed native release."""
    ARCHITECTURES = ["python-portable"]

    def __init__(self, project_name: str):
        if type(project_name) is not str or not 1 <= len(project_name) <= 120:
            raise ValueError("invalid project name")
        self.project_name = project_name
        self.build_history: list[dict] = []

    def build_game(self, game_data: dict, phase: str = "final") -> dict:
        if not require_execution_allowed("GameForge internal build"):
            return {"status": "disabled", "ok": False, "disabled": True,
                    "error": execution_disabled_message("GameForge internal build")}
        if type(game_data) is not dict or len(canonical(game_data)) > MAX_GAME_DATA_BYTES:
            raise ValueError("invalid or oversized game data")
        campaign = campaign_from_game_data(self.project_name, game_data)
        measured = smoke(campaign)
        source = self._generate_source(game_data, campaign, measured)
        bundle_bytes, files = self._zip_bundle(source, game_data)
        signature = self._sign(bundle_bytes)
        result = {
            "project": self.project_name, "phase": phase,
            "package_name": f"{self._safe(self.project_name)}__{self._safe(phase)}.zip",
            "bundle_bytes": bundle_bytes, "size_bytes": len(bundle_bytes), "files": files,
            "architectures": list(self.ARCHITECTURES), "signature": signature,
            "artifact_kind": "portable_playable_prototype",
            "release_qualified": False, "qualification": {
                "basis": "deterministic_reference_runtime_smoke",
                "native_device_qualified": False, **measured,
            },
            "runnable": {"entry_point": "internal_runtime.py", "data_file": "game_manifest.json",
                         "execution_command": "python internal_runtime.py game_manifest.json --play",
                         "can_run_internally": True},
            "timestamp": time.time(), "status": "built_successfully",
        }
        self.build_history.append({k: v for k, v in result.items() if k != "bundle_bytes"})
        del self.build_history[:-MAX_HISTORY]
        return result

    def _generate_source(self, game_data: dict, campaign: dict, measured: dict) -> dict[str, str]:
        runtime = Path(__file__).with_name("portable_runtime.py").read_text(encoding="utf-8")
        compile(runtime, "internal_runtime.py", "exec")
        manifest = {
            "name": self.project_name, "version": "1.0.0-portable",
            "artifact_kind": "portable_playable_prototype",
            "campaign_file": "campaign.json", "campaign_sha256": digest(campaign),
            "source_sha256": digest(game_data), "runtime_sha256": hashlib.sha256(runtime.encode()).hexdigest(),
            "release_qualified": False, "levels": len(campaign["levels"]),
        }
        def encode(value: Any) -> str:
            return canonical(value).decode("ascii") + "\n"
        return {
            "game_manifest.json": encode(manifest),
            "campaign.json": encode(campaign),
            "levels.json": encode(game_data.get("levels", {})),
            "systems.json": encode(game_data.get("systems", {})),
            "narrative.json": encode(game_data.get("narrative", {})),
            "content.json": encode(game_data.get("content", {})),
            "raw_game_data.json": encode(game_data),
            "reference_smoke.json": encode(measured),
            "internal_runtime.py": runtime,
            "README.txt": (
                "GameForge portable reference prototype (Python 3.10+).\n"
                "Play: python internal_runtime.py game_manifest.json --play\n"
                "Smoke/replay: python internal_runtime.py game_manifest.json\n"
                "Not a signed or native-qualified product release.\n"
            ),
        }

    def _zip_bundle(self, source: dict[str, str], game_data: dict):
        # Stable timestamps, ordering and stored bytes make regeneration across
        # process restarts byte-identical without depending on zlib versions.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            for name, content in sorted(source.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                zf.writestr(info, content.encode("utf-8"))
        return buf.getvalue(), sorted(source)

    def _sign(self, data: bytes) -> dict:
        # A SHA-256 checksum is integrity metadata, not an asymmetric signature.
        return {"algorithm": "sha256", "digest": hashlib.sha256(data).hexdigest(),
                "signature": None, "signed": False}

    @staticmethod
    def _safe(s: str) -> str:
        return "".join(c if c.isascii() and (c.isalnum() or c in "-_") else "_" for c in str(s))[:60]


def create_internal_build_system(project_name: str) -> InternalBuildSystem:
    return InternalBuildSystem(project_name)
