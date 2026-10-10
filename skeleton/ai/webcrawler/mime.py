"""Bounded extraction registry for textual web payloads."""
from __future__ import annotations
import json,re
from dataclasses import dataclass
_CHARSET=re.compile(r"charset\s*=\s*[\"']?([^;\"'\s]+)",re.I)
@dataclass(frozen=True)
class ExtractedPayload:
    text:str
    media_type:str
    charset:str
class MimeExtractor:
    def __init__(self,max_chars=2_000_000,max_bytes=8_000_000):
        self.max_chars=max_chars;self.max_bytes=max_bytes
    def extract(self,body:bytes,content_type:str):
        if len(body)>self.max_bytes:return None
        media=content_type.split(";",1)[0].strip().lower()
        match=_CHARSET.search(content_type);charset=(match.group(1) if match else "utf-8").lower()
        if charset not in {"utf-8","utf8","us-ascii","iso-8859-1","latin-1"}:return None
        try:text=body.decode(charset,errors="strict")
        except (UnicodeDecodeError,LookupError):return None
        if media in {"application/json","application/ld+json"}:
            try:obj=json.loads(text)
            except json.JSONDecodeError:return None
            text=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        elif media not in {"text/plain","text/markdown","text/csv"}:return None
        text=text[:self.max_chars].strip()
        return ExtractedPayload(text,media,charset) if text else None
