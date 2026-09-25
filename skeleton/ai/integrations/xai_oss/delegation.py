"""Provider-neutral handoff contract informed by the Grok Build bridge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping


class DelegationMode(str, Enum):
    REVIEW = "review"
    INVESTIGATE = "investigate"
    IMPLEMENT = "implement"


class DelegationWaitMode(str, Enum):
    WAIT = "wait"
    BACKGROUND = "background"


@dataclass(frozen=True, slots=True)
class GrokDelegationRequest:
    objective: str
    workspace_id: str
    mode: DelegationMode
    wait_mode: DelegationWaitMode = DelegationWaitMode.WAIT
    resume_session_id: str | None = None
    model: str | None = None
    effort: str | None = None
    allowed_paths: tuple[str, ...] = ()
    metadata: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, DelegationMode):
            object.__setattr__(self, "mode", DelegationMode(str(self.mode)))
        if not isinstance(self.wait_mode, DelegationWaitMode):
            object.__setattr__(
                self,
                "wait_mode",
                DelegationWaitMode(str(self.wait_mode)),
            )
        if not self.objective.strip():
            raise ValueError("objective must be non-empty")
        if not self.workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if self.effort not in {None, "low", "medium", "high"}:
            raise ValueError("effort must be low, medium, or high")
        if any(not path.strip() or path.startswith("/") for path in self.allowed_paths):
            raise ValueError("allowed_paths must be non-empty relative paths")
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def digest(self) -> str:
        payload = {
            "objective": self.objective,
            "workspace_id": self.workspace_id,
            "mode": self.mode.value,
            "wait_mode": self.wait_mode.value,
            "resume_session_id": self.resume_session_id,
            "model": self.model,
            "effort": self.effort,
            "allowed_paths": list(self.allowed_paths),
            "metadata": dict(sorted((self.metadata or {}).items())),
        }
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


__all__ = [
    "DelegationMode",
    "DelegationWaitMode",
    "GrokDelegationRequest",
]
