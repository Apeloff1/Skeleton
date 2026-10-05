"""
Skeleton Context Package

Exports:
- intake: Process questionnaire answers
- Questionnaire: Interactive game design questionnaire
- IntakeResult: Structured intake result
"""

from skeleton.context.questionnaire import IntakeResult, Questionnaire, intake

__all__ = ["intake", "Questionnaire", "IntakeResult"]
