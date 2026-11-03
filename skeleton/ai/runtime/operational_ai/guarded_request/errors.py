"""Stable machine-readable denial semantics; never leak private inputs."""
from __future__ import annotations

import re


_CODE = re.compile(r"[a-z][a-z0-9_-]{0,127}\Z", re.ASCII)


class GateDenied(ValueError):
    """A policy denial whose bounded code is safe for reporting."""

    def __init__(self, code: str):
        if type(code) is not str or _CODE.fullmatch(code) is None:
            raise ValueError("invalid denial code")
        self.code = code
        super().__init__(code)


def deny(code: str) -> None:
    raise GateDenied(code)
