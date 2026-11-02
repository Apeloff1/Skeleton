"""Adversarial local-process transport and fail-closed real-backend adapter tests.

A small fixture process emits *clearly simulated* responses. No success here
claims an approved GGUF, actual model quality, or whole-device readiness.
"""
from __future__ import annotations
from hashlib import sha256
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import tempfile
import time
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.model.isolation import (
    IsolatedGGUFBackend, IsolationFailure, IsolationPolicy)
from skeleton.ai.runtime.operational_ai.model.isolation import wire
from skeleton.ai.runtime.operational_ai.model.isolation.client import IsolationProtocolError
from skeleton.ai.runtime.operational_ai.model.isolation.messages import validate
from skeleton.ai.runtime.operational_ai.model.isolation.process import sanitized_environment
from skeleton.ai.runtime.operational_ai.model.isolation.receipts import parse_generation
from skeleton.ai.runtime.operational_ai.model.isolation.resources import snapshot_pid
from skeleton.ai.runtime.operational_ai.model.gguf.manifest import GGUFModelManifest, Shard


MODEL = sha256(b'fixture-not-a-real-model').hexdigest()
TOKEN = MODEL


def manifest() -> GGUFModelManifest:
    return GGUFModelManifest(model_id='test-fixture',
        shards=(Shard(path='weights.fake', bytes=12, sha256=sha256(b'fake'*3).hexdigest()),),
        model_sha256=MODEL, total_bytes=12, license='test-only',
        source='locally-generated-synthetic-test-model', rights_approved=True,
        context_ceiling=2048, gpu_layers_ceiling=0, minimum_memory_bytes=10)


class FixtureProcess:
    """Inject a subprocess only through a unit-test patch, never production API."""
    def __init__(self, mode: str):
        from skeleton.ai.runtime.operational_ai.model.isolation.process import OwnedWorker
        self._owned_cls = OwnedWorker
        self.process = subprocess.Popen([sys.executable, '-u', '-m',
            'skeleton.testing.fixture_isolated_worker', '--mode', mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd='/', env=sanitized_environment(),
            start_new_session=True, close_fds=True, bufsize=0)
        self._closed = False
        self.stop_count = 0

    @property
    def read_fd(self):
        return self.process.stdout.fileno()

    @property
    def write_fd(self):
        return self.process.stdin.fileno()

    def alive(self):
        return not self._closed and self.process.poll() is None

    def stop(self, *, grace_ms: int = 2000):
        self.stop_count += 1
        if self._closed:
            return
        self._closed = True
        import signal
        if self.process.poll() is None:
            try:os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:pass
        self.process.wait(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()


class WireTests(unittest.TestCase):
    def test_roundtrip_unicode(self):
        data = {'message': 'Emoji 🧪\nline 2', 'nested': [1, 2, {'ok': True}]}
        raw = wire.encode(data)
        self.assertEqual(wire.decode(raw[4:]), data)
        self.assertEqual(int.from_bytes(raw[:4], 'big'), len(raw)-4)

    def test_sorted_canonical_keys(self):
        self.assertEqual(wire.encode({'z': 1, 'a': 2}), wire.encode({'a': 2, 'z': 1}))

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(IsolationProtocolError):
            wire.decode(b'{"x":1,"x":2}')

    def test_nan_rejected(self):
        with self.assertRaises(IsolationProtocolError):
            wire.decode(b'{"x":NaN}')
        with self.assertRaises(IsolationProtocolError):
            wire.encode({'x': float('inf')})

    def test_invalid_utf8(self):
        with self.assertRaises(IsolationProtocolError):
            wire.decode(b'\xff')

    def test_array_not_message(self):
        with self.assertRaises(IsolationProtocolError):
            wire.decode(b'[1]')

    def test_json_size_ceiling(self):
        with self.assertRaises(IsolationProtocolError):
            wire.encode({'data': 'A'*500}, ceiling=60)

    def test_partial_pipe_eof(self):
        r, w = os.pipe()
        try:
            os.write(w, b'ab')
            os.close(w)
            with self.assertRaises(IsolationFailure):
                wire.read_frame(r, time.monotonic_ns()+100_000_000)
        finally:
            os.close(r)

    def test_oversized_frame_before_allocation(self):
        r, w = os.pipe()
        try:
            os.write(w, struct.pack('!I', 2_000_000))
            with self.assertRaises(IsolationProtocolError):
                wire.read_frame(r, time.monotonic_ns()+100_000_000, ceiling=1024)
        finally:
            os.close(r);os.close(w)

    def test_timeout_read(self):
        r, w = os.pipe()
        try:
            with self.assertRaises(IsolationFailure):
                wire.read_frame(r, time.monotonic_ns()+20_000_000)
        finally: os.close(r);os.close(w)

    def test_request_seed_bool_rejected(self):
        with self.assertRaises(IsolationProtocolError):
            validate([{'role':'user','content':'abc'}], 4, True, 0.5, IsolationPolicy())

    def test_request_tool_role_rejected(self):
        with self.assertRaises(IsolationProtocolError):
            validate([{'role':'tool','content':'execute'}], 4, 0, 0.5, IsolationPolicy())

    def test_request_extra_tool_properties(self):
        with self.assertRaises(IsolationProtocolError):
            validate([{'role':'user','content':'hi','tool_calls':[1]}], 4, 0, 0.5, IsolationPolicy())

    def test_total_context_bytes_enforced(self):
        with self.assertRaises(IsolationProtocolError):
            validate([{'role':'user','content':'A'*200000}]*5, 4, 0, 0.5, IsolationPolicy())

    def test_nonfinite_temperature(self):
        for t in (float('nan'),float('inf'),0.,-1,2.01):
            with self.subTest(t=t), self.assertRaises(IsolationProtocolError):
                validate([{'role':'user','content':'hi'}],4,0,t,IsolationPolicy())

    def test_bad_generation_extra_keys(self):
        with self.assertRaises(IsolationProtocolError):
            parse_generation({'version': 1}, request=1, model=MODEL,
                tokenizer=TOKEN, max_tokens=8, context_tokens=128)

    def test_resource_snapshot_readonly(self):
        observed=snapshot_pid(os.getpid())
        self.assertEqual(observed['pid'], os.getpid())
        self.assertGreater(observed['resident_bytes'],0)

    def test_sanitized_env_excludes_secret(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'NOT_FOR_CHILD','SKELETON_TEST_SECRET_ENV':'PRIVATE'}):
            values=sanitized_environment()
        self.assertNotIn('OPENAI_API_KEY',values)
        self.assertNotIn('SKELETON_TEST_SECRET_ENV',values)


class IsolatedProcessTests(unittest.TestCase):
    def backend(self, mode='normal', *, timeout=500):
        proc = []
        def factory():
            result=FixtureProcess(mode)
            proc.append(result)
            return result
        p=patch('skeleton.ai.runtime.operational_ai.model.isolation.client.OwnedWorker',new=factory)
        p.start();self.addCleanup(p.stop)
        backend=IsolatedGGUFBackend(Path('/tmp/test-model-local'),manifest(),
                                    n_ctx=256,inference_ms=timeout,startup_ms=2000)
        self.addCleanup(backend.close)
        return backend, proc

    @staticmethod
    def generate(backend):
        return backend.generate([{'role':'system','content':'be concise'},
            {'role':'user','content':'hello'}],max_output_tokens=16,seed=2,temperature=.7)

    def test_invalid_request_does_not_poison_or_consume_child_sequence(self):
        backend,_=self.backend()
        with self.assertRaises(IsolationProtocolError):
            backend.generate([{'role':'tool','content':'not authorized'}],
                max_output_tokens=16,seed=2,temperature=.7)
        self.assertTrue(backend.healthy)
        self.assertEqual(self.generate(backend).generated_tokens,6)

    def test_concurrent_close_interrupts_blocking_native_inference(self):
        backend,proc=self.backend('stall',timeout=5000)
        failures=[]
        def run():
            try:self.generate(backend)
            except IsolationFailure as exc:failures.append(type(exc).__name__)
        thread=threading.Thread(target=run)
        thread.start()
        time.sleep(.15)
        start=time.monotonic()
        backend.close()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertLess(time.monotonic()-start,2)
        self.assertTrue(failures)
        self.assertFalse(backend.healthy)
        self.assertFalse(proc[0].alive())

    def test_process_does_not_accept_second_command_during_active_call(self):
        backend,_=self.backend('stall',timeout=5000)
        done=[]
        thread=threading.Thread(target=lambda:self._expect_failure(backend,done))
        thread.start();time.sleep(.1)
        try:
            # Health is observation-only and does not claim responsiveness.
            self.assertEqual(backend.health()['isolation'],'dedicated-local-child-no-provider')
            backend.close()
        finally:
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertTrue(done)

    def _expect_failure(self,backend,completed):
        try:self.generate(backend)
        except IsolationFailure:completed.append(True)

    def test_real_subprocess_framing_generated_fixture(self):
        backend,proc=self.backend()
        receipt=self.generate(backend)
        self.assertIn('fixture result',receipt.text)
        self.assertEqual(receipt.output_digest, sha256(receipt.text.encode()).hexdigest())
        self.assertEqual(backend.model_digest,MODEL)
        self.assertEqual(backend.health()['requests_completed'],1)
        self.assertTrue(proc[0].alive())

    def test_two_calls_keep_one_worker(self):
        backend,proc=self.backend()
        self.generate(backend); self.generate(backend)
        self.assertEqual(len(proc),1)
        self.assertEqual(backend.health()['requests_completed'],2)

    def test_worker_heartbeat(self):
        backend,_=self.backend()
        pong=backend.probe()
        self.assertIn('responsive',pong['status'])
        self.generate(backend)

    def test_replay_not_available_in_native_backend(self):
        backend,_=self.backend()
        self.assertFalse(hasattr(backend, 'replay'))

    def test_stale_response_poisoned(self):
        backend,proc=self.backend('stale_result')
        with self.assertRaises(IsolationFailure):self.generate(backend)
        self.assertFalse(backend.healthy)
        with self.assertRaises(IsolationFailure):self.generate(backend)
        self.assertEqual(len(proc),1)

    def test_early_worker_death(self):
        backend,_=self.backend('exit_after_request')
        with self.assertRaises(IsolationFailure):self.generate(backend)
        self.assertFalse(backend.healthy)

    def test_native_timeout_kills(self):
        backend,proc=self.backend('stall',timeout=100)
        before=time.monotonic()
        with self.assertRaises(IsolationFailure):self.generate(backend)
        self.assertLess(time.monotonic()-before,3)
        self.assertFalse(proc[0].alive())

    def test_malformed_large_reply_kills(self):
        backend,_=self.backend('invalid_frame')
        with self.assertRaises(IsolationFailure):self.generate(backend)
        self.assertFalse(backend.healthy)

    def test_output_digest_change_poisoned(self):
        backend,_=self.backend('bad_hash')
        with self.assertRaises(IsolationFailure):self.generate(backend)
        self.assertEqual(backend.health()['requests_failed'],1)

    def test_wrong_model_after_ready(self):
        backend,_=self.backend('wrong_output_model')
        with self.assertRaises(IsolationFailure):self.generate(backend)

    def test_invalid_finish_reason(self):
        backend,_=self.backend('bad_finish_reason')
        with self.assertRaises(IsolationFailure):self.generate(backend)

    def test_invalid_token_usage(self):
        backend,_=self.backend('nonint_token')
        with self.assertRaises(IsolationFailure):self.generate(backend)

    def test_added_native_tool_call_rejected(self):
        backend,_=self.backend('native_role')
        with self.assertRaises(IsolationFailure):self.generate(backend)

    def test_wrong_heartbeat_sequence_kills(self):
        backend,_=self.backend('stale_pong')
        with self.assertRaises(IsolationFailure):backend.probe()
        self.assertFalse(backend.healthy)

    def test_closed_backend_no_model_reactivation(self):
        backend,proc=self.backend()
        backend.close()
        with self.assertRaises(IsolationFailure):self.generate(backend)
        self.assertFalse(proc[0].alive())

    def test_wrong_model_cannot_boot(self):
        proc=[]
        def factory():
            result=FixtureProcess('wrong_model');proc.append(result);return result
        with patch('skeleton.ai.runtime.operational_ai.model.isolation.client.OwnedWorker',new=factory):
            with self.assertRaises(IsolationFailure):
                IsolatedGGUFBackend(Path('/tmp/test-model-local'),manifest(),n_ctx=256,startup_ms=2000)
        self.assertFalse(proc[0].alive())

    def test_wrong_tokenizer_cannot_boot(self):
        with patch('skeleton.ai.runtime.operational_ai.model.isolation.client.OwnedWorker',new=lambda:FixtureProcess('wrong_tokenizer')):
            with self.assertRaises(IsolationFailure):
                IsolatedGGUFBackend(Path('/tmp/test-model-local'),manifest(),n_ctx=256,startup_ms=2000)

    def test_without_real_weights_production_boot_refused(self):
        # This patches nothing: production launches only its trusted child.
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(IsolationFailure):
                IsolatedGGUFBackend(Path(td),manifest(),n_ctx=256,startup_ms=1000)

    def test_no_api_key_in_child_environment(self):
        with patch.dict(os.environ,{'SKELETON_TEST_SECRET_ENV':'PRIVATE','OPENAI_API_KEY':'NOT_FOR_CHILD'}):
            backend,_=self.backend('credential_echo')
            self.assertEqual(self.generate(backend).text,'secret absent')

    def test_fixture_result_never_real_model_certification(self):
        backend,_=self.backend()
        self.generate(backend)
        self.assertEqual(backend.health()['isolation'],'dedicated-local-child-no-provider')
        self.assertNotIn('release_accepted',backend.health())


if __name__ == '__main__':
    unittest.main()
