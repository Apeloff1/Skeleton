#!/usr/bin/env python3
"""
Snowball Questionnaire Runner
Simple interactive questionnaire that logs all answers.
"""

from gameforge.snowball.questionnaire_logging import questionnaire_logger

QUESTIONS = [
    {"id": "game_name", "question": "What is the name of your game?"},
    {"id": "genre", "question": "What genre is your game?"},
    {"id": "core_loop", "question": "Describe the core gameplay loop in one sentence."},
    {"id": "target_platform", "question": "Primary target platform? (Mobile / PC / Both)"},
    {"id": "art_style", "question": "Preferred art style?"},
    {"id": "monetization", "question": "Monetization model? (Free, Paid, IAP, etc.)"},
]

def run_questionnaire():
    print("\n=== Snowball Game Concept Questionnaire ===\n")
    
    for q in QUESTIONS:
        answer = input(f"{q['question']}\n> ").strip()
        questionnaire_logger.log_response(
            question_id=q["id"],
            question=q["question"],
            answer=answer,
            confidence=0.9
        )
    
    print("\n=== Questionnaire Complete ===")
    print(questionnaire_logger.get_responses_as_context())
    return questionnaire_logger.get_all_responses()

if __name__ == "__main__":
    run_questionnaire()