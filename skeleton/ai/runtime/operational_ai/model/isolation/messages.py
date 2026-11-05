"""Strict request admission before native IPC; content is never a tool call."""
from __future__ import annotations
import math
from .contracts import IsolationProtocolError, IsolationPolicy, integer


def validate(messages: object, max_output_tokens: object, seed: object,
             temperature: object, policy: IsolationPolicy) -> list[dict[str, str]]:
    if type(messages) is not list or not 1 <= len(messages) <= policy.max_prompts:
        raise IsolationProtocolError('invalid native message count')
    normalized = []
    total = 0
    for item in messages:
        if not isinstance(item, dict) or set(item) != {'role', 'content'}:
            raise IsolationProtocolError('native message must contain role and text only')
        if item['role'] not in ('system', 'user', 'assistant') or not isinstance(item['content'], str):
            raise IsolationProtocolError('unsupported native message role')
        try:
            size = len(item['content'].encode('utf8', 'strict'))
        except UnicodeError as exc:
            raise IsolationProtocolError('invalid native message encoding') from exc
        if size > 250000:
            raise IsolationProtocolError('native message too large')
        total += size
        if total > min(800000, policy.max_frame_bytes - 8192):
            raise IsolationProtocolError('native aggregate context exceeds IPC budget')
        normalized.append(dict(item))
    integer(max_output_tokens, 'native generation tokens', 1, 4096)
    if max_output_tokens >= policy.context_tokens:
        raise IsolationProtocolError('generation exceeds native context')
    integer(seed, 'native seed', 0, (2 ** 32) - 1)
    if (type(temperature) not in (float, int) or not math.isfinite(temperature)
            or not 0 < temperature <= 2):
        raise IsolationProtocolError('invalid native temperature')
    return normalized
