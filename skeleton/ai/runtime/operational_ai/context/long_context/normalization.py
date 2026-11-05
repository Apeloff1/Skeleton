"""Unicode normalization solely for search, never signed record mutation."""
from __future__ import annotations
import unicodedata
from .contracts import ContextError


def search_normalize(text:str,limit:int=65536)->str:
    if not isinstance(text,str) or len(text.encode())>limit:
        raise ContextError('oversize search normalization')
    return ' '.join(unicodedata.normalize('NFKC',text).casefold().split())
