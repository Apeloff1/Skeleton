from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime

from gameforge.enterprise.alerts import METRICS

logger = logging.getLogger("gameforge.backup_scheduler")


class BackupScheduler:
    def __init__(self, backup_service, interval_seconds: int | None = None):
        self.backup_service = backup_service
        self.interval_seconds = interval_seconds or int(
            os.getenv("GAMEFORGE_BACKUP_INTERVAL_SECONDS", "3600")
        )
        self._running = False
        self.last_result: dict | None = None
        self.last_error: str | None = None

    async def start(self):
        if os.getenv("GAMEFORGE_BACKUP_SCHEDULER", "1") != "1":
            logger.info("Backup scheduler disabled")
            return
        self._running = True
        logger.info("Backup scheduler started interval=%ss", self.interval_seconds)
        await asyncio.sleep(5)
        while self._running:
            try:
                result = await self.backup_service.create_snapshot(
                    label=f"scheduled-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
                )
                self.last_result = result
                self.last_error = None
                METRICS.inc("backup_scheduled_success_total")
            except Exception as e:
                self.last_error = str(e)
                METRICS.inc("backup_scheduled_error_total")
                logger.exception("Scheduled backup failed")
            await asyncio.sleep(self.interval_seconds)

    async def stop(self):
        self._running = False

    def status(self) -> dict:
        return {
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "s3_enabled": bool(os.getenv("GAMEFORGE_BACKUP_S3_BUCKET")),
        }
