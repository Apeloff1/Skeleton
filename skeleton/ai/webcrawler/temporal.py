"""Bitemporal crawl history and change intelligence."""
from __future__ import annotations
import difflib, hashlib
from dataclasses import dataclass
from typing import Iterable
from .core import CrawlDocument

@dataclass(frozen=True)
class TemporalVersion:
    url: str
    content_hash: str
    observed_at: float
    valid_from: float
    valid_to: float | None
    text: str

@dataclass(frozen=True)
class ChangeEvent:
    url: str
    previous_hash: str
    current_hash: str
    observed_at: float
    similarity: float
    added_excerpt: str
    removed_excerpt: str

class TemporalCorpus:
    def __init__(self) -> None:
        self._versions: dict[str,list[TemporalVersion]]={}

    def observe(self, doc: CrawlDocument) -> ChangeEvent | None:
        versions=self._versions.setdefault(doc.canonical_url,[])
        if versions and versions[-1].content_hash == doc.content_hash:
            return None
        previous=versions[-1] if versions else None
        if previous:
            versions[-1]=TemporalVersion(
                previous.url,previous.content_hash,previous.observed_at,
                previous.valid_from,doc.fetched_at,previous.text,
            )
        current=TemporalVersion(
            doc.canonical_url,doc.content_hash,doc.fetched_at,
            doc.fetched_at,None,doc.text,
        )
        versions.append(current)
        if previous is None:
            return None
        matcher=difflib.SequenceMatcher(None,previous.text,doc.text,autojunk=False)
        added=[]; removed=[]
        for tag,i1,i2,j1,j2 in matcher.get_opcodes():
            if tag in {"insert","replace"}: added.append(doc.text[j1:j2])
            if tag in {"delete","replace"}: removed.append(previous.text[i1:i2])
        return ChangeEvent(
            doc.canonical_url,previous.content_hash,doc.content_hash,doc.fetched_at,
            matcher.ratio()," ".join(added)[:1000]," ".join(removed)[:1000],
        )

    def history(self,url:str) -> tuple[TemporalVersion,...]:
        return tuple(self._versions.get(url,()))

    def as_of(self,url:str,when:float) -> TemporalVersion | None:
        for version in reversed(self._versions.get(url,())):
            if version.valid_from <= when and (version.valid_to is None or when < version.valid_to):
                return version
        return None

    def changed_urls(self) -> tuple[str,...]:
        return tuple(sorted(url for url,versions in self._versions.items() if len(versions)>1))
