from __future__ import annotations
"""
Always-on / session recording → internal transcription → Client ledger.

Design constraints:
- Explicit user consent required (enabled flag).
- Audio is ephemeral: deleted on a 3-hour schedule after transcription.
- Transcript text is what persists in Client ledger / insight pipeline.
- Local-first; no third-party upload in this module.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable, Dict, List, Optional

logger = logging.getLogger("gameforge.recording_ledger")


def _data_dir() -> Path:
    p = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class AudioChunkMeta:
    path: str
    created_ts: float
    user_id: str
    transcribed: bool = False
    transcript: Optional[str] = None


class TranscriptionProvider:
    """Pluggable STT. Default is a stub for offline/dev."""

    async def transcribe(self, audio_path: str) -> str:
        # Production: wire whisper.cpp / on-device STT / consented cloud STT
        name = Path(audio_path).name
        return f"[transcript-stub for {name} @ {datetime.utcnow().isoformat()}]"


class RecordingLedgerService:
    """
    Manages ephemeral audio + durable transcript ledger entries.
    """

    def __init__(
        self,
        user_id: str,
        log_service=None,
        transcriber: Optional[TranscriptionProvider] = None,
        audio_ttl_seconds: int = 3 * 3600,
        enabled: bool = False,
    ):
        self.user_id = user_id
        self.log_service = log_service
        self.transcriber = transcriber or TranscriptionProvider()
        self.audio_ttl_seconds = audio_ttl_seconds
        self.enabled = enabled and os.getenv("GAMEFORGE_ALWAYS_ON_RECORDING", "0") == "1"
        self.consent = False  # must be set True by explicit user action
        self._chunks: List[AudioChunkMeta] = []
        self._running = False
        self.audio_dir = _data_dir() / "ephemeral_audio" / user_id
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def set_consent(self, granted: bool):
        self.consent = bool(granted)
        logger.info("recording consent user=%s granted=%s", self.user_id, self.consent)

    def is_active(self) -> bool:
        return self.enabled and self.consent

    async def ingest_audio_file(self, path: str) -> Dict[str, Any]:
        """Register an audio file produced by the capture layer."""
        if not self.is_active():
            return {"accepted": False, "reason": "recording inactive (enable+consent required)"}
        meta = AudioChunkMeta(path=path, created_ts=time.time(), user_id=self.user_id)
        self._chunks.append(meta)
        transcript = await self.transcriber.transcribe(path)
        meta.transcribed = True
        meta.transcript = transcript
        ledger_entry = None
        if self.log_service is not None and transcript.strip():
            ledger_entry = await self.log_service.ledger_from_transcript(
                transcript,
                title="Ambient transcript",
                tags=["transcript", "client_ledger"],
                metadata={"audio_path": path, "ephemeral_audio": True},
            )
        return {
            "accepted": True,
            "transcribed": True,
            "transcript_preview": transcript[:240],
            "ledger_entry_id": getattr(ledger_entry, "entry_id", None),
        }

    async def purge_expired_audio(self) -> int:
        """Delete audio older than TTL. Transcripts remain in ledger."""
        now = time.time()
        kept: List[AudioChunkMeta] = []
        deleted = 0
        for c in self._chunks:
            age = now - c.created_ts
            if age >= self.audio_ttl_seconds:
                try:
                    Path(c.path).unlink(missing_ok=True)
                    deleted += 1
                except Exception:
                    logger.exception("failed to delete audio %s", c.path)
            else:
                kept.append(c)
        # also sweep directory for orphans
        for p in self.audio_dir.glob("*"):
            try:
                if p.is_file() and now - p.stat().st_mtime >= self.audio_ttl_seconds:
                    p.unlink(missing_ok=True)
                    deleted += 1
            except Exception:
                pass
        self._chunks = kept
        return deleted

    async def start_purge_loop(self, interval_seconds: int = 300):
        self._running = True
        logger.info(
            "audio purge loop start ttl=%ss interval=%ss",
            self.audio_ttl_seconds,
            interval_seconds,
        )
        while self._running:
            try:
                n = await self.purge_expired_audio()
                if n:
                    logger.info("purged %s audio files", n)
            except Exception:
                logger.exception("purge loop error")
            await asyncio.sleep(interval_seconds)

    async def stop(self):
        self._running = False

    def status(self) -> Dict[str, Any]:
        return {
            "enabled_env": self.enabled,
            "consent": self.consent,
            "active": self.is_active(),
            "audio_ttl_seconds": self.audio_ttl_seconds,
            "pending_chunks": len(self._chunks),
            "audio_dir": str(self.audio_dir),
        }
