"""Exact native tokenizer hook; estimates cannot qualify true token capacity."""
from __future__ import annotations
from typing import Callable
from .contracts import ContextError

class TokenMeter:
    def __init__(self,encoder:Callable[[str],list[int]],identity:str):
        if not callable(encoder) or not isinstance(identity,str) or len(identity)!=64:
            raise ContextError('native tokenizer and digest required')
        self.encoder=encoder;self.identity=identity

    def count(self,text:str)->int:
        encoded=self.encoder(text)
        if (not isinstance(encoded,list) or len(encoded)>1_048_576 or
            any(type(x) is not int or x<0 for x in encoded)):
            raise ContextError('invalid native tokenization result')
        return len(encoded)


def pessimistic_bytes(text:str)->int:
    return len(text.encode('utf8'))
