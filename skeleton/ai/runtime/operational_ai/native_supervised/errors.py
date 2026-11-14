"""Stable errors for fail-closed, private, native supervised model lifecycle."""
from __future__ import annotations
import re

_CODE = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z", re.ASCII)


class SupervisedRejected(ValueError):
    def __init__(self,code:str):
        if type(code) is not str or not _CODE.fullmatch(code):
            raise ValueError("invalid supervised rejection code")
        self.code=code
        super().__init__(code)


def reject(code:str)->None:
    raise SupervisedRejected(code)
