"""
Local AI package. Exports complete facade and core seams.
"""
from .local_ai_complete import LocalAIComplete, get_complete
from .local_ai_index import SEAMS

__all__ = ["LocalAIComplete", "get_complete", "SEAMS"]
