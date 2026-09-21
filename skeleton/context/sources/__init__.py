"""Canonical source adapters for ContextSegment construction."""

from skeleton.context.sources.conversation import conversation_message_segment
from skeleton.context.sources.retrieval import retrieval_segment

__all__ = [
    "conversation_message_segment",
    "retrieval_segment",
]
