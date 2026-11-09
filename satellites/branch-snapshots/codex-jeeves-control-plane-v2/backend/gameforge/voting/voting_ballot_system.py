#!/usr/bin/env python3
"""
Voting Ballot System for Zaibatsu CNS
Structured, auditable voting with weights, reputation, and tie detection.
Used by agents (and the Judge on ties).
"""

import json
from typing import Dict, List
from datetime import datetime

class VotingBallotSystem:
    def __init__(self):
        self.ballots = {}
        self.voting_history = []

    def create_ballot(self, room_id: str, topic: str, options: List[str], 
                      deadline: str = None) -> Dict:
        ballot = {
            "ballot_id": f"ballot_{room_id}_{datetime.now().timestamp()}",
            "room_id": room_id,
            "topic": topic,
            "options": options,
            "votes": {},
            "created_at": datetime.now().isoformat(),
            "deadline": deadline,
            "status": "open"
        }
        self.ballots[ballot["ballot_id"]] = ballot
        return ballot

    def cast_vote(self, ballot_id: str, agent_id: str, choice: str, 
                  weight: float = 1.0, reputation: float = 1.0) -> Dict:
        if ballot_id not in self.ballots:
            return {"error": "Ballot not found"}
        
        ballot = self.ballots[ballot_id]
        if ballot["status"] != "open":
            return {"error": "Ballot is closed"}
        
        effective_weight = weight * reputation
        ballot["votes"][agent_id] = {
            "choice": choice,
            "weight": effective_weight,
            "timestamp": datetime.now().isoformat()
        }
        
        return {"status": "vote_cast", "effective_weight": effective_weight}

    def tally_votes(self, ballot_id: str) -> Dict:
        if ballot_id not in self.ballots:
            return {"error": "Ballot not found"}
        
        ballot = self.ballots[ballot_id]
        tally = {}
        
        for vote in ballot["votes"].values():
            choice = vote["choice"]
            weight = vote["weight"]
            tally[choice] = tally.get(choice, 0) + weight
        
        winner = max(tally, key=tally.get) if tally else None
        is_tie = len([v for v in tally.values() if v == max(tally.values())]) > 1 if tally else False
        
        return {
            "tally": tally,
            "winner": winner,
            "is_tie": is_tie,
            "total_votes": len(ballot["votes"])
        }

if __name__ == "__main__":
    voting = VotingBallotSystem()
    print("Voting Ballot System ready. Structured, weighted, auditable voting available.")
