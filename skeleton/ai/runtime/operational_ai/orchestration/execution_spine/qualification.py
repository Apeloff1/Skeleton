"""Explicitly bounded live-model qualification without demo fallback."""
from __future__ import annotations
from hashlib import sha256
import time
from .contracts import Identity,SpineError,SpineLimits
from .adapter import generate

PROBE_PROMPT='Return a short description of your offline operation.'
def run_canary(backend,identity:Identity,limits:SpineLimits,*,seed:int=32)->dict:
    # Probe is deliberately a real generation; its answer is neither
    # content-certified nor inserted into the user's chat store.
    messages=({'role':'system','content':'Respond briefly. You cannot execute tools.'},
              {'role':'user','content':PROBE_PROMPT})
    started=time.monotonic_ns()
    receipt=generate(backend,identity,messages,limits,seed=seed,temperature=.5)
    duration=time.monotonic_ns()-started
    return {'status':'native-canary-executed-not-quality-certified',
        'model_sha256':receipt.model_sha256,'tokenizer_sha256':receipt.tokenizer_sha256,
        'output_sha256':receipt.output_digest(),'prompt_tokens':receipt.prompt_tokens,
        'generated_tokens':receipt.generated_tokens,'elapsed_ns':duration}
