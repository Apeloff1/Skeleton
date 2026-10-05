#!/usr/bin/env python3
"""
Snowball Questionnaire Logging
Logs all user answers during the initial Snowball intake questionnaire.
Makes answers available to agents across all rooms.
"""

import time
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
import json
import os

@dataclass
class QuestionnaireResponse:
    question_id: str
    question: str
    answer: Any
    timestamp: float
    confidence: float = 1.0  # How sure the user seemed

class SnowballQuestionnaireLogger:
    def __init__(self, base_path: str = "/tmp/snowball_questionnaire"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
        self.log_file = os.path.join(base_path, "questionnaire_log.json")
        self.responses: List[QuestionnaireResponse] = self._load()

    def _load(self) -> List[QuestionnaireResponse]:
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as f:
                data = json.load(f)
                return [QuestionnaireResponse(**item) for item in data]
        return []

    def _save(self):
        with open(self.log_file, "w") as f:
            json.dump([asdict(r) for r in self.responses], f, indent=2)

    def log_response(self, question_id: str, question: str, answer: Any, confidence: float = 1.0):
        response = QuestionnaireResponse(
            question_id=question_id,
            question=question,
            answer=answer,
            timestamp=time.time(),
            confidence=confidence
        )
        self.responses.append(response)
        self._save()
        print(f"[Questionnaire] Logged: {question_id} -> {answer}")

    def get_all_responses(self) -> List[Dict]:
        return [asdict(r) for r in self.responses]

    def get_responses_as_context(self) -> str:
        """Returns formatted context for agents in rooms."""
        if not self.responses:
            return "No questionnaire responses yet."
        
        lines = ["=== Snowball Questionnaire Responses ==="]
        for r in self.responses:
            lines.append(f"- {r.question}: {r.answer} (confidence: {r.confidence})")
        return "\n".join(lines)

# Global logger
questionnaire_logger = SnowballQuestionnaireLogger()