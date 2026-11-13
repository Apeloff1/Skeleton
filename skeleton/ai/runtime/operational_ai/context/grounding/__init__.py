"""Offline evidence-grounding: exact source custody, FTS, citations and trust isolation."""
from .documents import Document, Passage
from .chunking import segment
from .index import GroundingIndex
from .ranking import RankedHit, rerank
from .citations import parse_citations, verify_citations
from .projection import project_evidence
__all__=['Document','Passage','segment','GroundingIndex','RankedHit','rerank','parse_citations','verify_citations','project_evidence']
