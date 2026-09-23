"""Canonical source adapters for ContextSegment construction."""

from skeleton.context.sources.artifact import artifact_segment
from skeleton.context.sources.conversation import conversation_message_segment
from skeleton.context.sources.memory import memory_record_segment
from skeleton.context.sources.retrieval import retrieval_segment
from skeleton.context.sources.skills import skill_manifest_segment
from skeleton.context.sources.tools import tool_manifest_segment, tool_receipt_segment

__all__ = [
    "artifact_segment",
    "conversation_message_segment",
    "memory_record_segment",
    "retrieval_segment",
    "skill_manifest_segment",
    "tool_manifest_segment",
    "tool_receipt_segment",
]
