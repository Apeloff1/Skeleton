"""Exact native receipt checks on the trust boundary between processes."""
from __future__ import annotations
from hashlib import sha256
from .contracts import IsolationProtocolError, digest, integer
from ..native import Generated


def parse_ready(raw: dict, *, model: str, manifest: str) -> str:
    if not isinstance(raw, dict) or set(raw) != {'version', 'type', 'model_sha256', 'tokenizer_sha256', 'manifest_sha256'}:
        raise IsolationProtocolError('invalid native worker startup identity')
    if raw['version'] != 1 or type(raw['version']) is not int or raw['type'] != 'ready':
        raise IsolationProtocolError('unsupported native worker protocol')
    if digest(raw['model_sha256'], 'model') != model or digest(raw['manifest_sha256'], 'manifest') != manifest:
        raise IsolationProtocolError('worker model or manifest identity mismatch')
    return digest(raw['tokenizer_sha256'], 'tokenizer')


def parse_generation(raw: dict, *, request: int, model: str, tokenizer: str,
                     max_tokens: int, context_tokens: int) -> Generated:
    expected = {'version', 'type', 'request', 'text', 'output_digest', 'model_digest',
                'tokenizer_digest', 'prompt_tokens', 'generated_tokens', 'finish_reason'}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise IsolationProtocolError('malformed native generation envelope')
    if (type(raw['version']) is not int or raw['version'] != 1 or raw['type'] != 'result'
            or type(raw['request']) is not int or raw['request'] != request):
        raise IsolationProtocolError('native generation response is stale or mismatched')
    if digest(raw['model_digest'], 'response model') != model or digest(raw['tokenizer_digest'], 'response tokenizer') != tokenizer:
        raise IsolationProtocolError('native model or tokenizer changed mid-operation')
    p = integer(raw['prompt_tokens'], 'native prompt tokens', 0, context_tokens)
    g = integer(raw['generated_tokens'], 'native completion tokens', 0, max_tokens)
    if p + g > context_tokens:
        raise IsolationProtocolError('native generation exceeded exact token budget')
    text = raw['text']
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf8')) > 262144:
        raise IsolationProtocolError('invalid native generation text')
    if digest(raw['output_digest'], 'native output') != sha256(text.encode('utf8')).hexdigest():
        raise IsolationProtocolError('native text and output hash disagree')
    if raw['finish_reason'] not in ('stop', 'length', 'eos'):
        raise IsolationProtocolError('unsupported native finish reason')
    return Generated(text=text, prompt_tokens=p, generated_tokens=g,
                     output_digest=raw['output_digest'], model_digest=model,
                     tokenizer_digest=tokenizer, finish_reason=raw['finish_reason'])


def emit_generation(generation: Generated, request: int) -> dict:
    if not isinstance(generation, Generated):
        raise IsolationProtocolError('worker must return a native receipt')
    return {'version': 1, 'type': 'result', 'request': request,
            'text': generation.text, 'output_digest': generation.output_digest,
            'model_digest': generation.model_digest, 'tokenizer_digest': generation.tokenizer_digest,
            'prompt_tokens': generation.prompt_tokens, 'generated_tokens': generation.generated_tokens,
            'finish_reason': generation.finish_reason}
