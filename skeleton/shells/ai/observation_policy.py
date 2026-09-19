"""Policy for deciding what execution observation data can return to a model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from skeleton.shells.ai.observation import AIObservation


class ObservationExposure(str, Enum):
    METADATA_ONLY = "metadata_only"
    REDACTED_EXCERPT = "redacted_excerpt"
    DIGEST_ONLY = "digest_only"


@dataclass(frozen=True)
class ObservationPolicy:
    exposure: ObservationExposure = ObservationExposure.METADATA_ONLY
    max_excerpt_chars: int = 1024
    blocked_patterns: tuple[str, ...] = (
        "password",
        "secret",
        "token",
        "authorization",
        "private_key",
    )

    def __post_init__(self) -> None:
        if self.max_excerpt_chars < 0 or self.max_excerpt_chars > 16384:
            raise ValueError("observation excerpt limit out of range")
        patterns = tuple(self.blocked_patterns)
        if len(patterns) > 128:
            raise ValueError("too many observation blocked patterns")
        object.__setattr__(self, "blocked_patterns", patterns)


class ObservationPolicyEngine:
    def __init__(self, policy: ObservationPolicy | None = None) -> None:
        self.policy = policy or ObservationPolicy()
        self._patterns = tuple(
            re.compile(re.escape(item), re.IGNORECASE)
            for item in self.policy.blocked_patterns
        )

    def sanitize(self, observation: AIObservation) -> dict[str, object]:
        data = observation.to_dict()
        if self.policy.exposure is ObservationExposure.DIGEST_ONLY:
            return {
                "observation_id": observation.observation_id,
                "correlation_id": observation.correlation_id,
                "command": observation.command,
                "ok": observation.ok,
                "stdout_digest": observation.stdout_digest,
                "stderr_digest": observation.stderr_digest,
            }
        if self.policy.exposure is ObservationExposure.METADATA_ONLY:
            data["safe_excerpt"] = ""
            return data
        excerpt = observation.safe_excerpt[: self.policy.max_excerpt_chars]
        for pattern in self._patterns:
            excerpt = pattern.sub("[REDACTED]", excerpt)
        data["safe_excerpt"] = excerpt
        return data
