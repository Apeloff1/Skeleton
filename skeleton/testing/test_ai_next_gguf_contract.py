"""Real GGUF backend parser/receipt path with an injected safe loader fixture.

This does not claim llama.cpp or operator checkpoint qualification; it tests
fail-closed contracts before/after the native dependency handoff.
"""
from __future__ import annotations

import hashlib
import os
import struct
import unittest

from skeleton.ai.runtime.operational_ai.model.gguf.assembly import ModelAssembly
from skeleton.ai.runtime.operational_ai.model.gguf.manifest import (
    GGUFModelManifest, GGUFManifestError, Shard,
)
from skeleton.ai.runtime.operational_ai.model.gguf.runtime import GGUFBackend


class StubLlama:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.override = {}

    def create_chat_completion(self, **kwargs):
        self.last_call=kwargs
        result={'choices':[{'message':{'role':'assistant','content':'hello'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':7,'completion_tokens':2}}
        if self.override:
            result.update(self.override)
        return result


class TestGGUFNativeContracts(unittest.TestCase):
    def setUp(self):
        raw=b'GGUF'+struct.pack('<IQQ',3,1,1)+b'unit-test-weights-not-a-real-model'
        self.fd=os.memfd_create('test-gguf-native-receipt',getattr(os,'MFD_CLOEXEC',0))
        os.write(self.fd,raw)
        sha=hashlib.sha256(raw).hexdigest()
        self.assembly=ModelAssembly(self.fd,len(raw),sha,'1'*64,True)
        self.manifest=GGUFModelManifest(model_id='original_model',
            shards=(Shard('original.gguf',len(raw),sha),),
            model_sha256=sha,total_bytes=len(raw),license='test-only',
            source='original:test',rights_approved=True,context_ceiling=2048,
            gpu_layers_ceiling=0,minimum_memory_bytes=1)
        self.llama=StubLlama()
        self.backend=GGUFBackend(self.manifest,self.assembly,n_ctx=2048,
            loader=lambda **kwargs:self.llama)

    def tearDown(self):
        self.backend.close()

    def generate(self):
        return self.backend.generate([{'role':'user','content':'Say hello'}],
                   max_output_tokens=32,seed=0,temperature=.5)

    def test_valid_receipt_and_exact_output_digest(self):
        result=self.generate()
        self.assertEqual(result.text,'hello')
        self.assertEqual(result.model_digest,self.manifest.model_sha256)
        self.assertEqual(result.output_digest,hashlib.sha256(b'hello').hexdigest())

    def test_function_call_denied(self):
        self.llama.override={'choices':[{'message':{'role':'assistant','content':'hello',
                             'function_call':{'name':'delete','arguments':'{}'}},
                             'finish_reason':'stop'}],
                              'usage':{'prompt_tokens':1,'completion_tokens':1}}
        with self.assertRaisesRegex(GGUFManifestError,'receipt'):
            self.generate()

    def test_tool_calls_denied(self):
        self.llama.override={'choices':[{'message':{'role':'assistant','content':'hello',
                             'tool_calls':[{'type':'function'}]},
                             'finish_reason':'stop'}],
                              'usage':{'prompt_tokens':1,'completion_tokens':1}}
        with self.assertRaises(GGUFManifestError):self.generate()

    def test_non_assistant_role_denied(self):
        self.llama.override={'choices':[{'message':{'role':'system','content':'hello'},
                            'finish_reason':'stop'}],
                            'usage':{'prompt_tokens':1,'completion_tokens':1}}
        with self.assertRaises(GGUFManifestError):self.generate()

    def test_unsupported_finish_reason_denied(self):
        self.llama.override={'choices':[{'message':{'role':'assistant','content':'hello'},
                            'finish_reason':'function_call'}],
                            'usage':{'prompt_tokens':1,'completion_tokens':1}}
        with self.assertRaises(GGUFManifestError):self.generate()

    def test_missing_finish_reason_denied(self):
        self.llama.override={'choices':[{'message':{'role':'assistant','content':'hello'}}],
                            'usage':{'prompt_tokens':1,'completion_tokens':1}}
        with self.assertRaises(GGUFManifestError):self.generate()

    def test_native_usage_overflow_denied(self):
        self.llama.override={'choices':[{'message':{'role':'assistant','content':'hello'},
                            'finish_reason':'stop'}],
                            'usage':{'prompt_tokens':2047,'completion_tokens':2}}
        with self.assertRaises(GGUFManifestError):self.generate()

    def test_close_refuses_generation(self):
        self.backend.close()
        with self.assertRaises(GGUFManifestError):self.generate()

    def test_native_context_bound_rejects_unbounded_history(self):
        with self.assertRaises(GGUFManifestError):
            self.backend.generate([{'role':'user','content':'x'}]*1025,
                            max_output_tokens=16,seed=0,temperature=.5)


if __name__=='__main__':unittest.main()
