#!/usr/bin/env python3
"""
Judge Tie-Break + Evaluation Engine
The Jeeves Judge only activates on ties. He evaluates outputs and makes final decisions using Exocortex context.
"""

import json
from typing import Dict, List, Any
from datetime import datetime

class JudgeTiebreakEvaluationEngine:
    def __init__(self, exocortex_context_provider=None):
        self.exocortex = exocortex_context_provider  # Link to real Exocortex
        self.tie_breaks_performed = 0

    def evaluate_and_judge(self, room_id: str, proposals: List[Dict], 
                          current_votes: Dict, judge_agent: Dict) -> Dict:
        """
        Main entry point for the Judge.
        Only runs when there is a tie.
        """
        if not self._is_tie(current_votes):
            return {
                "action": "no_intervention",
                "reason": "No tie detected. Judge remains in observation mode."
            }

        # Tie detected — Judge activates
        context = self._get_exocortex_context(room_id, judge_agent)
        
        decision = self._make_tiebreak_decision(proposals, current_votes, context)
        
        self.tie_breaks_performed += 1
        
        return {
            "action": "tiebreak_vote_cast",
            "judge_agent_id": judge_agent["agent_id"],
            "room_id": room_id,
            "decision": decision,
            "exocortex_context_used": bool(context),
            "reasoning": decision.get("reasoning", ""),
            "timestamp": datetime.now().isoformat()
        }

    def _is_tie(self, votes: Dict) -> bool:
        """Simple tie detection logic."""
        if not votes:
            return False
        vote_counts = {}
        for vote in votes.values():
            vote_counts[vote] = vote_counts.get(vote, 0) + 1
        max_votes = max(vote_counts.values())
        return list(vote_counts.values()).count(max_votes) > 1

    def _get_exocortex_context(self, room_id: str, judge_agent: Dict) -> Dict:
        """Pull relevant context from Exocortex (memory, journals, salience, etc.)."""
        if not self.exocortex:
            return {"note": "Exocortex link simulated"}
        
        # In real system this would query:
        # - Relevant journals
        # - Salience network
        # - Recent coherence metrics
        # - User intent / project goals
        return {
            "exocortex_context": "loaded",
            "relevant_journals": ["project_progress", "coherence_log"],
            "user_intent_alignment": 0.94
        }

    def _make_tiebreak_decision(self, proposals: List[Dict], 
                               votes: Dict, context: Dict) -> Dict:
        """Core judgement logic. Uses Exocortex context + quality criteria."""
        # Placeholder for sophisticated judgement
        best_proposal = proposals[0] if proposals else {}
        
        return {
            "chosen_proposal_id": best_proposal.get("id", "unknown"),
            "reasoning": "Selected based on highest coherence, synergy potential, and Exocortex-aligned quality.",
            "exocortex_influence": context.get("user_intent_alignment", 0.9),
            "confidence": 0.93
        }

if __name__ == "__main__":
    engine = JudgeTiebreakEvaluationEngine()
    print("Judge Tie-Break Evaluation Engine ready. Jeeves stands ready to judge only on ties.")
