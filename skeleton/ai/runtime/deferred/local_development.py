"""Reproducible local-environment qualification for VOL-195."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import sha256_json
from .operations_experience import LocalEnvironment


@dataclass(frozen=True, slots=True)
class LocalEnvironmentReceipt:
    environment_id: str
    python_version: str
    dependency_digest: str
    secret_mode: str
    service_digests: tuple[tuple[str, str], ...]

    @property
    def digest(self) -> str:
        return sha256_json({
            "environment_id": self.environment_id,
            "python_version": self.python_version,
            "dependency_digest": self.dependency_digest,
            "secret_mode": self.secret_mode,
            "services": list(self.service_digests),
        })


class LocalEnvironmentQualifier:
    """Fail-closed comparison between declared and observed local environments."""

    def __init__(self, expected: LocalEnvironment, *, service_digests: Mapping[str, str]) -> None:
        if not service_digests:
            raise ValueError("at least one declared service is required")
        normalized: list[tuple[str, str]] = []
        for name, digest in service_digests.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("service name must be non-empty")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("service digest must be lowercase sha256")
            normalized.append((name.strip(), digest))
        self.expected = expected
        self.service_digests = tuple(sorted(normalized))

    def qualify(
        self,
        observed: LocalEnvironment,
        *,
        observed_services: Mapping[str, str],
        real_secret_present: bool = False,
    ) -> LocalEnvironmentReceipt:
        if real_secret_present is not False:
            raise PermissionError("real secrets are forbidden in local qualification")
        if observed != self.expected:
            raise ValueError("local environment does not match canonical declaration")
        actual = tuple(sorted(observed_services.items()))
        if actual != self.service_digests:
            raise ValueError("local service inventory/digests do not match canonical declaration")
        return LocalEnvironmentReceipt(
            environment_id=observed.environment_id,
            python_version=observed.python_version,
            dependency_digest=observed.dependency_digest,
            secret_mode=observed.secret_mode,
            service_digests=self.service_digests,
        )
