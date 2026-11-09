"""Invalid-model receipts open the local circuit; live probe never fakes readiness."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch
import io
import contextlib
import unittest

from skeleton.ai.runtime.operational_ai.model.gateway import ModelGateway
from skeleton.ai.runtime.operational_ai.model.circuit import CircuitBreaker, CircuitOpen
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.authority.budgets import Limits
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
from skeleton.ai.runtime.operational_ai.model.gguf.probe_cli import main as probe_main

A = 'a'*64
B = 'b'*64


class InvalidBackend:
    model_digest=A
    tokenizer_digest=A

    def __init__(self,kind='valid'):
        self.kind=kind
        self.calls=0

    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1
        if self.kind=='raises':
            raise RuntimeError('native failed')
        if self.kind=='untyped':
            return {'text':'not a native receipt'}
        prompt=10000 if self.kind=='context' else 3
        generated=900 if self.kind=='output' else 3
        return Generated('hello',prompt,generated,sha256(b'hello').hexdigest(),
                         B if self.kind=='identity' else A,A,'stop')


class TestNativeReceiptCustody(unittest.TestCase):
    def gateway(self,kind):
        backend=InvalidBackend(kind)
        breaker=CircuitBreaker(max_consecutive_failures=1,cooldown_ms=30000)
        return ModelGateway(backend,circuit=breaker),backend,breaker

    def run_gateway(self,gateway):
        return gateway.complete([{'role':'user','content':'ping'}], Limits(),seed=0,temperature=.7)

    def test_valid_receipt_resets_failure_count(self):
        gateway,backend,breaker=self.gateway('valid')
        receipt=self.run_gateway(gateway)
        self.assertEqual(receipt.generation.text,'hello')
        self.assertEqual(breaker.health['failures'],0)

    def test_untyped_native_output_trips_circuit(self):
        gateway,backend,breaker=self.gateway('untyped')
        with self.assertRaises(ContractViolation):self.run_gateway(gateway)
        self.assertTrue(breaker.health['open'])
        with self.assertRaises(CircuitOpen):self.run_gateway(gateway)
        self.assertEqual(backend.calls,1)

    def test_identity_switch_trips_circuit(self):
        gateway,backend,breaker=self.gateway('identity')
        with self.assertRaises(ContractViolation):self.run_gateway(gateway)
        self.assertTrue(breaker.health['open'])

    def test_context_overrun_trips_circuit(self):
        gateway,backend,breaker=self.gateway('context')
        with self.assertRaises(ContractViolation):self.run_gateway(gateway)
        self.assertTrue(breaker.health['open'])

    def test_output_overrun_trips_circuit(self):
        gateway,backend,breaker=self.gateway('output')
        with self.assertRaises(ContractViolation):self.run_gateway(gateway)
        self.assertTrue(breaker.health['open'])

    def test_backend_failure_trips_circuit(self):
        gateway,backend,breaker=self.gateway('raises')
        with self.assertRaises(RuntimeError):self.run_gateway(gateway)
        self.assertTrue(breaker.health['open'])

    def test_live_probe_no_silent_fallback(self):
        result=SimpleNamespace(model_sha256=A)
        with (patch('skeleton.ai.runtime.operational_ai.model.gguf.probe_cli.inspect_installed_model',return_value=result),
              patch('skeleton.ai.runtime.operational_ai.model.gguf.probe_cli.load_approved_manifest',return_value=result),
              patch('skeleton.ai.runtime.operational_ai.model.gguf.probe_cli.activate_model',side_effect=ImportError('no llama'))):
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                code=probe_main(['--model-root','/never/exists'])
        self.assertEqual(code,2)
        self.assertIn('ImportError',errors.getvalue())
        self.assertNotIn('no llama',errors.getvalue())

    def test_live_probe_observation_never_certifies_release(self):
        result=SimpleNamespace(model_sha256=A)
        class FakeManager:
            def __enter__(self):return SimpleNamespace(model_digest=A)
            def __exit__(self,*args):return False
        with (patch('skeleton.ai.runtime.operational_ai.model.gguf.probe_cli.inspect_installed_model',return_value=result),
              patch('skeleton.ai.runtime.operational_ai.model.gguf.probe_cli.load_approved_manifest',return_value=result),
              patch('skeleton.ai.runtime.operational_ai.model.gguf.probe_cli.activate_model',return_value=FakeManager()),
              patch('skeleton.ai.runtime.operational_ai.model.gguf.probe_cli.live_smoke',return_value={'status':'native-generation-observed'})):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code=probe_main(['--model-root','/never/exists'])
        self.assertEqual(code,0)
        self.assertIn('"release_certified": false',output.getvalue())
        self.assertIn('"quality_certified": false',output.getvalue())


if __name__=='__main__':
    unittest.main()
