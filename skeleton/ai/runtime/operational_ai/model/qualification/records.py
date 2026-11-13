"""Output-free, digest-pinned measurements; never persist prompts or generations."""
from __future__ import annotations

from hashlib import sha256
from .contracts import QualificationHeld, SHA


def trial_record(index, elapsed_ns, receipt, model_digest, tokenizer_digest, max_tokens):
    from ..native import Generated

    # Check all untrusted types before any equality, hashing, text encoding or
    # arithmetic. Generated is a frozen dataclass, not an immutable trust seal:
    # direct callers can forge fields with object.__setattr__.
    if (type(index) is not int or not 1 <= index <= 256
            or type(elapsed_ns) is not int or not 0 < elapsed_ns <= 600_000_000_000
            or type(max_tokens) is not int or not 1 <= max_tokens <= 128):
        raise QualificationHeld('invalid monotonic trial')
    if type(receipt) is not Generated:
        raise QualificationHeld('native runtime did not return real typed generation metadata')
    for digest in (model_digest, tokenizer_digest, receipt.model_digest,
                   receipt.tokenizer_digest, receipt.output_digest):
        if type(digest) is not str or len(digest) != 64 or SHA.fullmatch(digest) is None:
            raise QualificationHeld('invalid native generation digest')
    if receipt.model_digest != model_digest or receipt.tokenizer_digest != tokenizer_digest:
        raise QualificationHeld('model identity changed during stress qualification')
    if type(receipt.text) is not str or len(receipt.text) > 262144 or not receipt.text.strip():
        raise QualificationHeld('native model generated empty or invalid output')
    try:
        raw = receipt.text.encode('utf8')
    except UnicodeEncodeError:
        # A frozen Generated can be forged after construction; malformed
        # Unicode must hold qualification rather than escape the contract.
        raise QualificationHeld('invalid native generated text encoding') from None
    if len(raw) > 262144 or sha256(raw).hexdigest() != receipt.output_digest:
        raise QualificationHeld('model result digest and text disagree')
    if (type(receipt.prompt_tokens) is not int
            or not 0 <= receipt.prompt_tokens <= 131072
            or type(receipt.generated_tokens) is not int
            or not 0 <= receipt.generated_tokens <= max_tokens):
        raise QualificationHeld('native token accounting cannot be certified')
    if type(receipt.finish_reason) is not str or receipt.finish_reason not in ('stop','length','eos'):
        raise QualificationHeld('model native finish reason invalid')
    return {'trial':index,'elapsed_ns':elapsed_ns,
            'prompt_tokens':receipt.prompt_tokens,
            'generated_tokens':receipt.generated_tokens,
            'output_sha256':receipt.output_digest,
            'finish_reason':receipt.finish_reason}
