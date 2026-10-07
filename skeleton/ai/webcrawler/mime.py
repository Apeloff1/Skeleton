"""Bounded extraction registry for textual web payloads."""
from __future__ import annotations
import json
from dataclasses import dataclass
@dataclass(frozen=True)
class ExtractedPayload:
    text:str
    media_type:str
class MimeExtractor:
    def __init__(self,max_chars=2_000_000):
        self.max_chars=max_chars
    def extract(self,body:bytes,content_type:str):
        media=content_type.split(";",1)[0].strip().lower()
        if media in {"text/plain","text/markdown","text/csv"}:
            text=body.decode("utf-8",errors="replace")
        elif media in {"application/json","application/ld+json"}:
            try:
                obj=json.loads(body.decode("utf-8",errors="strict"))
            except (UnicodeDecodeError,json.JSONDecodeError):
                return None
            text=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        else:
            return None
        text=text[:self.max_chars].strip()
        return ExtractedPayload(text,media) if text else None
