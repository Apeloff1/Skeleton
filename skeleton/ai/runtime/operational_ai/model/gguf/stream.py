"""Bounded token-delta stream from a *real* local llama.cpp engine.

llama.cpp can produce usage only at the end. The stream therefore exposes
provisional deltas, then a verified terminal receipt; clients must not treat
intermediate tokens as committed authoritative chat.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import threading
from collections.abc import Iterator
from .manifest import GGUFManifestError
from .runtime import GGUFBackend

@dataclass(frozen=True,slots=True)
class GenerationDelta:
    sequence:int
    kind:str
    text:str
    digest:str
    committed:bool


def stream_generation(backend:GGUFBackend,messages:list[dict],*,max_tokens:int=128,
                      seed:int=0,temperature:float=1.0,
                      cancel:threading.Event|None=None)->Iterator[GenerationDelta]:
    if not isinstance(backend,GGUFBackend):raise GGUFManifestError('real GGUF backend required')
    if type(max_tokens) is not int or not 1<=max_tokens<=4096:
        raise GGUFManifestError('invalid streaming output budget')
    if type(seed) is not int or not 0<=seed<=2**32-1:
        raise GGUFManifestError('invalid sampling seed')
    if not isinstance(temperature,(int,float)) or not 0<temperature<=2:
        raise GGUFManifestError('invalid sampling temperature')
    if not isinstance(messages,list) or not messages:
        raise GGUFManifestError('nonempty chat history required')
    with backend._mutex:
        if backend._image._closed:raise GGUFManifestError('model custody released')
        try:
            iterator=backend._engine.create_chat_completion(messages=messages,
               max_tokens=max_tokens,temperature=float(temperature),seed=seed,stream=True)
            text_parts=[];size=0;sequence=0;finish_seen=False
            for response in iterator:
                if cancel is not None and cancel.is_set():
                    raise GGUFManifestError('generation cancelled; no terminal receipt')
                if not isinstance(response,dict) or not isinstance(response.get('choices'),list) or len(response['choices'])!=1:
                    raise GGUFManifestError('invalid native stream chunk')
                choice=response['choices'][0]
                payload=choice.get('delta') or {}
                delta=payload.get('content') or ''
                if not isinstance(delta,str):raise GGUFManifestError('nontext native stream delta')
                if delta:
                    size+=len(delta.encode())
                    if size>262144:raise GGUFManifestError('native streaming text byte ceiling exceeded')
                    text_parts.append(delta);sequence+=1
                    yield GenerationDelta(sequence,'delta',delta,sha256(delta.encode()).hexdigest(),False)
                if choice.get('finish_reason') is not None:
                    finish_seen=True
            if not finish_seen:
                raise GGUFManifestError('native stream ended without terminal reason')
            full=''.join(text_parts)
            sequence+=1
            yield GenerationDelta(sequence,'end','',sha256(full.encode()).hexdigest(),True)
        except GGUFManifestError:raise
        except Exception as exc:
            raise GGUFManifestError('native stream failed; uncommitted deltas only') from exc
