"""Process-wide AppServices accessor (lazy; no lifespan hook)."""
from __future__ import annotations

import os
import threading
from typing import Optional

from skeleton.app_services.container import AppServices

_lock = threading.Lock()
_services: Optional[AppServices] = None


def get_app_services() -> AppServices:
    global _services
    with _lock:
        if _services is None:
            _services = AppServices.open(os.environ.get("APP_SERVICES_DATA_DIR", "data/app_services"))
        return _services
