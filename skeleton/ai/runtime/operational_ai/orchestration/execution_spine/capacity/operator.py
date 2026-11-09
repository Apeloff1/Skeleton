"""Minimal read-only operator façade; it never exposes a prompt or secret."""
from __future__ import annotations
from ..contracts import SpineError
from .preview import preview
from .policy import named


def readiness(spine, session: str, prompt: str, *, profile: str = 'portable') -> dict:
    report = preview(spine, session, prompt, policy=named(profile))
    if report['token_admission'] != 'exact-backend-count-admitted':
        return report | {'operator_action':'native-tokenizer-qualification-still-required'}
    return report | {'operator_action':'context-admitted-not-model-quality-certified'}
