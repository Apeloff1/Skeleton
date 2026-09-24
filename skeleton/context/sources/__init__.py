"""Canonical source adapters for ContextSegment construction."""

from skeleton.context.sources.artifact import artifact_segment
from skeleton.context.sources.conversation import conversation_message_segment
from skeleton.context.sources.memory import memory_record_segment
from skeleton.context.sources.retrieval import retrieval_segment
from skeleton.context.sources.skill import skill_instruction_segment
from skeleton.context.sources.tool import tool_manifest_segment

__all__ = [
    "artifact_segment",
    "conversation_message_segment",
    "memory_record_segment",
    "retrieval_segment",
    "skill_instruction_segment",
    "tool_manifest_segment",
]
