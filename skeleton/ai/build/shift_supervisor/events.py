from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

LOGGER = logging.getLogger("shift_supervisor")


def emit_event(event: str, *, actor: str, correlation_id: str, payload: Any) -> None:
    """Emit a structured event through the repo's logging pipeline.

    Secrets should never be passed in payload. The helper intentionally accepts
    serializable operational state only and uses one stable logger namespace.
    """
    if is_dataclass(payload):
        payload = asdict(payload)
    LOGGER.info(
        json.dumps(
            {
                "event": event,
                "actor": actor,
                "correlation_id": correlation_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "payload": payload,
            },
            default=str,
            sort_keys=True,
        )
    )
