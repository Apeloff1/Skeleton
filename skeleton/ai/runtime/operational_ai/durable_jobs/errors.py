"""Bounded fail-closed denial codes; no sensitive request bodies in exceptions."""
from __future__ import annotations
import re

CODE = re.compile(r"[a-z][a-z0-9_-]{0,127}\Z", re.ASCII)


class JobDenied(ValueError):
    def __init__(self, code: str):
        if type(code) is not str or CODE.fullmatch(code) is None:
            raise ValueError("invalid job denial code")
        self.code = code
        super().__init__(code)


def deny(code: str) -> None:
    raise JobDenied(code)
