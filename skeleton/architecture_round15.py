"""
Skeleton — Round-15 architecture addendum

ResponseCycle round: the ContextFabric becomes conversational — every
Jeeves reply distills into work orders, orders execute between turns,
interjections flow into the next reply.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.contexts.cycle": {
        "layer": "contexts",
        "purpose": "ResponseCycle: per-turn orchestrator (distill → execute → interject → guide) + ConnectorExecutor with offline simulation",
        "exports": ["ResponseCycle", "ConnectorExecutor", "CycleReport"],
    },
}

CONVERSATION_LOOP = [
    "User turn arrives at Jeeves",
    "Provider generates the reply (SAM-expanded, KAG-cited)",
    "before_reply() prepends the interjection earned last turn",
    "after_reply() distills the reply into work orders",
    "Queue dequeues up to N orders → ConnectorExecutor runs them",
    "Completions fire the positive interjected summary",
    "Failures defer into the backlog chain (mined while idle)",
    "Oracle notes golden-path shifts for the next narration",
]


def summary() -> Dict[str, Any]:
    return {
        "round15_modules": len(NEW_MODULES),
        "conversation_loop_stages": len(CONVERSATION_LOOP),
        "conversation_loop": CONVERSATION_LOOP,
        "genesis_handles_contexts": ["fabric", "workorders", "backlog", "planning",
                                      "queue", "oracle", "syntax_fixer", "cycle"],
        "fabric_is_conversational": True,
    }
