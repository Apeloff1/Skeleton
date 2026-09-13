"""Canonical state hashing for deterministic replay and provenance."""
import hashlib
import json
from typing import Any


def state_digest(state: Any) -> str:
    payload = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()
