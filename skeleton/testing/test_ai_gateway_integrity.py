"""Native receipt corruption and quota failures must trip the real model breaker."""
from __future__ import annotations
from hashlib import sha256
import unittest
from skeleton.ai.runtime.operational_ai.authority.budgets import Limits
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.model.gateway import ModelGateway
from skeleton.ai.runtime.operational_ai.model.circuit import CircuitBreaker,CircuitOpen

SHA='a'*64
TOKEN='b'*64

class Backend:
    model_digest=SHA
    tokenizer_digest=TOKEN
    def __init__(self,mode='good'):
        self.calls=0;self.mode=mode
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1
        if self.mode=='raise':raise RuntimeError('native failure')
        answer='Native response; no fallback'
        digest=sha256(answer.encode('utf8')).hexdigest()
        return Generated(text=answer,
            prompt_tokens=20 if self.mode!='context_overrun' else 4095,
            generated_tokens=4 if self.mode!='output_overrun' else max_output_tokens+1,
            output_digest=digest if self.mode!='bad_digest' else 'f'*64,
            model_digest=SHA if self.mode!='identity' else 'c'*64,
            tokenizer_digest=TOKEN,
            finish_reason='stop') if self.mode!='bad_type' else {'text':answer}

class GatewayReceiptIntegrity(unittest.TestCase):
    def setup_gateway(self,mode='good'):
        backend=Backend(mode)
        gateway=ModelGateway(backend,circuit=CircuitBreaker(max_consecutive_failures=3,cooldown_ms=60000))
        return backend,gateway
    def limit(self):return Limits(context_tokens=4096,output_tokens=64,output_bytes=8192)
    def call(self,gateway):return gateway.complete([{'role':'user','content':'Hello'}],self.limit())
    def test_success_receipt(self):
        backend,gateway=self.setup_gateway()
        result=self.call(gateway)
        self.assertEqual(result.generation.text,'Native response; no fallback')
        self.assertEqual(backend.calls,1)
        self.assertEqual(gateway.circuit.health['failures'],0)
    def test_digest_mismatch_failure(self):
        _,gateway=self.setup_gateway('bad_digest')
        with self.assertRaises(ContractViolation):self.call(gateway)
        self.assertEqual(gateway.circuit.health['failures'],1)
    def test_missing_native_receipt_counts_failure(self):
        _,gateway=self.setup_gateway('bad_type')
        with self.assertRaises(ContractViolation):self.call(gateway)
        self.assertEqual(gateway.circuit.health['failures'],1)
    def test_model_switch_counts_failure(self):
        _,gateway=self.setup_gateway('identity')
        with self.assertRaises(ContractViolation):self.call(gateway)
        self.assertEqual(gateway.circuit.health['failures'],1)
    def test_context_token_overrun_counts_failure(self):
        _,gateway=self.setup_gateway('context_overrun')
        with self.assertRaises(ContractViolation):self.call(gateway)
        self.assertEqual(gateway.circuit.health['failures'],1)
    def test_completion_token_overrun_counts_failure(self):
        _,gateway=self.setup_gateway('output_overrun')
        with self.assertRaises(ContractViolation):self.call(gateway)
        self.assertEqual(gateway.circuit.health['failures'],1)
    def test_native_failure_counts_failure(self):
        _,gateway=self.setup_gateway('raise')
        with self.assertRaises(RuntimeError):self.call(gateway)
        self.assertEqual(gateway.circuit.health['failures'],1)
    def test_rejected_receipts_open_breaker(self):
        backend,gateway=self.setup_gateway('bad_digest')
        for _ in range(3):
            with self.assertRaises(ContractViolation):self.call(gateway)
        self.assertTrue(gateway.circuit.health['open'])
        with self.assertRaises(CircuitOpen):self.call(gateway)
        self.assertEqual(backend.calls,3)
    def test_success_resets_earlier_failure(self):
        backend,gateway=self.setup_gateway('bad_digest')
        with self.assertRaises(ContractViolation):self.call(gateway)
        backend.mode='good'
        self.call(gateway)
        self.assertEqual(gateway.circuit.health['failures'],0)
    def test_no_implicit_provider_fallback(self):
        backend,gateway=self.setup_gateway('raise')
        with self.assertRaises(RuntimeError):self.call(gateway)
        self.assertEqual(backend.calls,1)

if __name__=='__main__':unittest.main()
