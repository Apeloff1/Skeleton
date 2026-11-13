"""Pinned real llama.cpp inference over a hash-verified Linux memfd model.

The runtime always uses a real, explicitly available local llama_cpp dependency.
Response accounting comes from the native backend, not synthetic estimates.
"""
from __future__ import annotations
import hashlib
import importlib
import math
import threading
from typing import Any
from .manifest import GGUFModelManifest,GGUFManifestError
from .assembly import ModelAssembly,assemble_model
from .header import inspect_header
from ..native import Generated


class GGUFBackend:
    def __init__(self,manifest:GGUFModelManifest,assembly:ModelAssembly,*,
                 n_ctx:int=2048,n_gpu_layers:int=0,n_threads:int=4,loader:Any=None):
        if assembly._closed or not assembly.sealed or assembly.sha256!=manifest.model_sha256:
            raise GGUFManifestError("model image not pinned and authenticated")
        if (type(n_ctx) is not int or not 128<=n_ctx<=manifest.context_ceiling
            or type(n_gpu_layers) is not int or not 0<=n_gpu_layers<=manifest.gpu_layers_ceiling
            or type(n_threads) is not int or not 1<=n_threads<=64):
            raise GGUFManifestError("GGUF runtime resource configuration exceeds operator ceiling")
        inspect_header(assembly.fd)
        if loader is None:
            try:
                loader=importlib.import_module('llama_cpp').Llama
            except (ImportError,AttributeError) as exc:
                raise GGUFManifestError("local llama-cpp-python is required; no fallback") from exc
        self._image=assembly
        self._manifest=manifest
        self._ctx=n_ctx
        self._mutex=threading.Lock()
        try:
            self._engine=loader(model_path=assembly.path,n_ctx=n_ctx,n_gpu_layers=n_gpu_layers,
                                n_threads=n_threads,verbose=False,use_mmap=False)
        except Exception as exc:
            raise GGUFManifestError("native GGUF load refused by llama.cpp") from exc

    @property
    def model_digest(self)->str:return self._manifest.model_sha256

    @property
    def tokenizer_digest(self)->str:
        # GGUF embeds tokenization metadata in the exact pinned model bytes. This
        # is a model-bound identity, not an independent tokenizer attestation.
        return self._manifest.model_sha256

    def generate(self,messages:list[dict[str,str]],*,max_output_tokens:int,
                 seed:int,temperature:float)->Generated:
        if (type(max_output_tokens) is not int or not 1<=max_output_tokens<=4096
            or type(seed) is not int or not 0<=seed<=2**32-1
            or type(temperature) not in (int,float) or not math.isfinite(temperature)
            or not 0<temperature<=2):
            raise GGUFManifestError("invalid native generation configuration")
        if not isinstance(messages,list) or not messages or len(messages)>1024:
            raise GGUFManifestError("invalid chat history")
        for msg in messages:
            if (not isinstance(msg,dict) or set(msg)!={'role','content'}
                or msg['role'] not in {'system','user','assistant'}
                or not isinstance(msg['content'],str) or len(msg['content'].encode())>250_000):
                raise GGUFManifestError("invalid message role or content")
        with self._mutex:
            if self._image._closed:raise GGUFManifestError("model custody released")
            try:
                result=self._engine.create_chat_completion(messages=messages,
                    max_tokens=max_output_tokens,temperature=float(temperature),seed=seed,
                    stream=False)
            except Exception as exc:
                raise GGUFManifestError("native generation failed") from exc
        try:
            choices=result['choices']
            if not isinstance(choices,list) or len(choices)!=1:
                raise KeyError('choices')
            choice=choices[0]
            message=choice['message']
            if (not isinstance(message,dict) or message.get('role','assistant')!='assistant'
                    or message.get('tool_calls') or message.get('function_call')):
                raise ValueError('native backend attempted unauthorized tool or role')
            text=message['content']
            reason=choice.get('finish_reason')
            # A function/tool-call finish cannot be represented as a safe
            # user-visible chat response, even if content is also present.
            if reason not in ('stop','length'):
                raise ValueError('unsupported native finish reason')
            usage=result['usage']
            prompt_tokens=usage['prompt_tokens']
            generated=usage['completion_tokens']
            if (not isinstance(text,str) or not isinstance(reason,str)
                or type(prompt_tokens) is not int or type(generated) is not int
                or prompt_tokens<0 or not 0<=generated<=max_output_tokens
                or prompt_tokens+generated>self._ctx
                or len(text.encode())>262144):
                raise ValueError('native receipt invalid')
            return Generated(text,prompt_tokens,generated,
                hashlib.sha256(text.encode()).hexdigest(),self.model_digest,
                self.tokenizer_digest,reason)
        except (KeyError,TypeError,IndexError,ValueError) as exc:
            raise GGUFManifestError("malformed native generation receipt") from exc

    def close(self)->None:
        with self._mutex:
            self._engine=None
            self._image.close()

    def __enter__(self)->"GGUFBackend":return self
    def __exit__(self,*_:object)->None:self.close()
