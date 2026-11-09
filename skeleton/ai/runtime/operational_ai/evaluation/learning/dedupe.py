"""Exact and normalized duplicate detection, preserving original source lineage."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import re,unicodedata
from .dataset import TrainingDataset,LearningError

@dataclass(frozen=True,slots=True)
class DuplicateReport:
    exact:tuple[tuple[str,str],...]
    normalized:tuple[tuple[str,str],...]
    total:int


def _normalized(text:str)->str:
    return ' '.join(unicodedata.normalize('NFKC',text).casefold().split())


def duplicates(dataset:TrainingDataset)->DuplicateReport:
    exact_seen={};norm_seen={};exact=[];normalized=[]
    for record in dataset.records:
        full=record.source_sha
        norm=sha256((_normalized(record.prompt)+'\x00'+_normalized(record.response)).encode()).hexdigest()
        if full in exact_seen:exact.append((exact_seen[full],record.sample_id))
        else:exact_seen[full]=record.sample_id
        if norm in norm_seen and full not in exact_seen:
            normalized.append((norm_seen[norm],record.sample_id))
        else:norm_seen.setdefault(norm,record.sample_id)
    return DuplicateReport(tuple(exact),tuple(normalized),len(dataset.records))
