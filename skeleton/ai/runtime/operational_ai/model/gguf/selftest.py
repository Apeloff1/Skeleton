"""Actual local model generation smoke, not a synthetic backend readiness claim."""
from __future__ import annotations
from dataclasses import asdict
import time
from .runtime import GGUFBackend
from .manifest import GGUFManifestError


def live_smoke(backend:GGUFBackend,*,max_new_tokens:int=16)->dict:
    if type(max_new_tokens) is not int or not 1<=max_new_tokens<=64:
        raise GGUFManifestError('smoke output token bound invalid')
    started=time.monotonic_ns()
    result=backend.generate([{'role':'system','content':'Reply in English.'},
          {'role':'user','content':'Reply with one short greeting.'}],
          max_output_tokens=max_new_tokens,seed=7,temperature=0.2)
    if not result.text.strip():raise GGUFManifestError('live inference returned no text')
    return {'status':'native-generation-observed','model_sha256':result.model_digest,
            'tokenizer_binding':result.tokenizer_digest,'generated_tokens':result.generated_tokens,
            'prompt_tokens':result.prompt_tokens,'output_sha256':result.output_digest,
            'elapsed_ns':time.monotonic_ns()-started}
