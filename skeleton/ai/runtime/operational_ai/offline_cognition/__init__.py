"""Offline cognitive operations over source-bound native AI and private memory.

No synthetic model generation, provider fallback, user-prompt tool authority,
or claims of approved external sources.
"""
from .core.contracts import CognitionError
from .core.engine import CognitiveEngine
__all__=("CognitionError","CognitiveEngine")
