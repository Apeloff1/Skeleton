"""Stable machine-readable denial semantics; never leak private inputs."""
from __future__ import annotations


class GateDenied(ValueError):
    """A policy denial whose code is safe for user-facing reporting."""

    def __init__(self, code: str):
        if not isinstance(code, str) or not code.isascii() or not code.replace("-", "").isalnum():
            raise ValueError("invalid denial code")
        self.code = code
        super().__init__(code)


def deny(code: str) -> None:
    raise GateDenied(code)
