"""
Skeleton Memory — Guarded compaction for turn history

Provides:
- compact_turns: Compress turn history while preserving semantic content
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def compact_turns(turns: Optional[List[Dict[str, Any]]], constraints: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Compress turn history while preserving key information.
    
    Args:
        turns: List of turn dicts with 'role', 'content', etc.
        constraints: Optional list of constraint strings to preserve
        
    Returns:
        Compaction result with summary and preserved turns, or None if no turns.
    """
    if not turns:
        return None
    
    # Extract key information
    roles = {}
    for turn in turns:
        role = turn.get("role", "unknown")
        roles.setdefault(role, 0)
        roles[role] += 1
    
    # Preserve first and last turns, summarize middle
    preserved = []
    if len(turns) > 0:
        preserved.append({"index": 0, "role": turns[0].get("role"), "content_preview": turns[0].get("content", "")[:100]})
    
    if len(turns) > 1:
        preserved.append({"index": len(turns) - 1, "role": turns[-1].get("role"), "content_preview": turns[-1].get("content", "")[:100]})
    
    # Summarize middle turns
    middle_count = max(0, len(turns) - 2)
    
    result = {
        "original_count": len(turns),
        "preserved_count": len(preserved),
        "middle_summarized": middle_count,
        "role_distribution": roles,
        "preserved_turns": preserved,
        "constraints_preserved": constraints or [],
    }
    
    if constraints:
        result["constraint_count"] = len(constraints)
    
    return result
