"""Output-free, digest-pinned measurements; never persist prompts or generations."""
from __future__ import annotations
from hashlib import sha256
from .contracts import QualificationHeld


def trial_record(index, elapsed_ns, receipt, model_digest, tokenizer_digest, max_tokens):
    from ..native import Generated
    if not isinstance(receipt, Generated):
        raise QualificationHeld('native runtime did not return real typed generation metadata')
    if receipt.model_digest!=model_digest or receipt.tokenizer_digest!=tokenizer_digest:
        raise QualificationHeld('model identity changed during stress qualification')
    if not isinstance(receipt.text,str) or not receipt.text.strip():
        raise QualificationHeld('native model generated empty or invalid output')
    if sha256(receipt.text.encode('utf8')).hexdigest()!=receipt.output_digest:
        raise QualificationHeld('model result digest and text disagree')
    if (type(receipt.prompt_tokens)is not int or receipt.prompt_tokens<0 or
        type(receipt.generated_tokens)is not int or not 0<=receipt.generated_tokens<=max_tokens):
        raise QualificationHeld('native token accounting cannot be certified')
    if receipt.finish_reason not in ('stop','length','eos'):
        raise QualificationHeld('model native finish reason invalid')
    if type(index)is not int or index<1 or type(elapsed_ns)is not int or elapsed_ns<=0:
        raise QualificationHeld('invalid monotonic trial')
    return {'trial':index,'elapsed_ns':elapsed_ns,
            'prompt_tokens':receipt.prompt_tokens,
            'generated_tokens':receipt.generated_tokens,
            'output_sha256':receipt.output_digest,
            'finish_reason':receipt.finish_reason}
