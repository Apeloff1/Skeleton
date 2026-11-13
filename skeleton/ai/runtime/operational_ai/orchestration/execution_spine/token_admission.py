"""Enforce tokenizer-authored context admission where backend exposes encode.

Fallback estimates are never treated as proof. A backend that lacks a
trustworthy tokenizer still has to reject context overruns during native
inference; release qualification records that as unverified preflight.
"""
from __future__ import annotations
from .contracts import SpineError,SpineLimits

def inspect_token_budget(backend,messages:tuple[dict,...],limits:SpineLimits)->dict:
    if not messages or not isinstance(messages,tuple):raise SpineError('context messages required')
    if hasattr(backend,'count_tokens') and callable(backend.count_tokens):
        counted=backend.count_tokens(list(messages))
        if type(counted)is not int or counted<0:raise SpineError('native tokenizer produced invalid count')
        if counted+limits.max_output_tokens>limits.context_tokens:
            raise SpineError('exact tokenizer context ceiling exceeded')
        return {'status':'exact-backend-count-admitted','prompt_tokens':counted}
    return {'status':'native-backend-must-enforce-unknown-precount',
            'prompt_tokens':None}
