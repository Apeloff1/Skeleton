"""Vault policies — declarative checks enforced on put/get/delete."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple

from skeleton.kernel.errors import VaultError


class PolicyViolation(VaultError):
    code = "VLT.POLICY"
    http_status = 422


@dataclass(frozen=True)
class VaultPolicy:
    name: str
    check: Callable[[str, bytes], bool]  # (secret_id, plaintext)
    message: str


class PolicyRegistry:
    """Ordered policy set; SealedStore callers invoke before mutation."""

    def __init__(self) -> None:
        self._policies: Tuple[VaultPolicy, ...] = tuple()

    def register(self, policy: VaultPolicy) -> None:
        self._policies = self._policies + (policy,)

    def evaluate(self, secret_id: str, plaintext: bytes) -> None:
        for policy in self._policies:
            if not policy.check(secret_id, plaintext):
                raise PolicyViolation(
                    "policy violation",
                    context={"policy": policy.name, "message": policy.message},
                )


def require_prefix(prefix: str) -> VaultPolicy:
    return VaultPolicy(
        name=f"prefix-{prefix}",
        check=lambda secret_id, _: secret_id.startswith(prefix),
        message=f"must start with {prefix!r}",
    )


def enforce_plaintext_minimum(min_bytes: int) -> VaultPolicy:
    return VaultPolicy(
        name=f"min-bytes-{min_bytes}",
        check=lambda _, plaintext: len(plaintext) >= min_bytes,
        message=f"must be at least {min_bytes} bytes",
    )
