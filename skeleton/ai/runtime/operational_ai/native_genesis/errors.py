"""Stable genesis errors; do not emit private prompts, checkpoint bytes or paths."""
from __future__ import annotations
import re

_CODE = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z", re.ASCII)


class GenesisRejected(ValueError):
    def __init__(self, code: str):
        if type(code) is not str or _CODE.fullmatch(code) is None:
            raise ValueError("invalid genesis rejection code")
        self.code = code
        super().__init__(code)


def refuse(code: str) -> None:
    raise GenesisRejected(code)
