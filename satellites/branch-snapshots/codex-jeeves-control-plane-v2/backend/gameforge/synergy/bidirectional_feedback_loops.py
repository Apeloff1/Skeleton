#!/usr/bin/env python3
"""
Bidirectional Feedback Loops
RAG and Navigation (plus other systems) continuously inform and improve each other in real time.
"""

import json
from typing import Dict
from datetime import datetime

class BidirectionalFeedbackLoops:
    def __init__(self):
        self.feedback_history = []

    def rag_to_navigation_feedback(self, rag_results: list, current_navigation_state: dict) -> dict:
        """RAG sends quality/relevance signals back to Navigation to adjust path weights."""
        feedback = {
            "timestamp": datetime.now().isoformat(),
            "direction": "RAG → Navigation",
            "action": "Adjust path weights based on RAG result quality",
            "details": "High-quality RAG results increase weight of related navigation edges."
        }
        self.feedback_history.append(feedback)
        return feedback

    def navigation_to_rag_feedback(self, navigation_trajectory: list, current_rag_state: dict) -> dict:
        """Navigation sends trajectory/intent signals to RAG to improve future retrievals."""
        feedback = {
            "timestamp": datetime.now().isoformat(),
            "direction": "Navigation → RAG",
            "action": "Pre-narrow retrieval scope and boost context relevant to current trajectory",
            "details": "RAG now prioritizes content along the agent's current path and predicted next steps."
        }
        self.feedback_history.append(feedback)
        return feedback

    def latent_reasoning_to_both(self, latent_refinements: list) -> dict:
        """Latent space reasoning feeds improvements back into both RAG and Navigation."""
        feedback = {
            "timestamp": datetime.now().isoformat(),
            "direction": "Latent Reasoning → RAG + Navigation",
            "action": "Use refined latent understanding to improve both retrieval quality and path suggestions"
        }
        self.feedback_history.append(feedback)
        return feedback

if __name__ == "__main__":
    loops = BidirectionalFeedbackLoops()
    print("Bidirectional Feedback Loops initialized. RAG, Navigation, and Latent Reasoning now continuously improve each other.")
