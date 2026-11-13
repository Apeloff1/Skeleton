"""Contract and integrated fake-native execution tests for actual serving code."""
import hashlib
import threading
import time
import unittest
from skeleton.ai.runtime.operational_ai.model.serving.admission import Slots
from skeleton.ai.runtime.operational_ai.model.serving.contracts import Request,ServingError,ModelIdentity
from skeleton.ai.runtime.operational_ai.model.serving.queue import FairRequestQueue
from skeleton.ai.runtime.operational_ai.model.serving.quotas import TenantQuotas
from skeleton.ai.runtime.operational_ai.model.serving.stream import chunk_response
from skeleton.ai.runtime.operational_ai.model.serving.health import HealthWindow
from skeleton.ai.runtime.operational_ai.model.serving.context import admit_window
from skeleton.ai.runtime.operational_ai.model.serving.receipts import Receipt
from skeleton.ai.runtime.operational_ai.model.serving.engine import ServingEngine
from skeleton.ai.runtime.operational_ai.model.serving.model_slot import ModelSlot
from skeleton.ai.runtime.operational_ai.authority.budgets import Limits
from skeleton.ai.runtime.operational_ai.model.native import Generated

D='a'*64
I=ModelIdentity(D,D,1)
class TinyNative:
    model_digest=D
    tokenizer_digest=D
    def __init__(self):self.calls=0;self.closed=False;self.max_tokens=[]
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1;self.max_tokens.append(max_output_tokens)
        msg='Verified response'
        return Generated(msg,3,2,hashlib.sha256(msg.encode()).hexdigest(),D,D,'stop')
    def close(self):self.closed=True

def req(tenant='A',name='id1',tokens=8,deadline=None):
    return Request(tenant,name,(('user','Prompt'),),tokens,7,.8,deadline or (time.monotonic_ns()+10_000_000_000))

class ServingV2Tests(unittest.TestCase):
    def test_scope_fair_queue(self):
        q=FairRequestQueue(8,3)
        for a in (req('A','a'),req('A','b'),req('B','a'),req('B','b')):q.put(a)
        self.assertEqual([q.get().tenant for _ in range(4)],['A','B','A','B'])
        self.assertIsNone(q.get())

    def test_duplicate_and_tenant_cap(self):
        q=FairRequestQueue(2,1);q.put(req())
        with self.assertRaises(ServingError):q.put(req())
        with self.assertRaises(ServingError):q.put(req('A','id2'))

    def test_concurrency_draining(self):
        slots=Slots(1)
        with slots.admitted(time.monotonic_ns()+1_000_000_000):
            self.assertEqual(slots.used,1)
            slots.drain()
            with self.assertRaises(ServingError):
                with slots.admitted(time.monotonic_ns()+10000):pass
        slots.wait_empty(time.monotonic_ns()+1_000_000)

    def test_quota_and_refund(self):
        q=TenantQuotas(20,1)
        q.reserve('A',12);self.assertEqual(q.remaining('A'),8)
        with self.assertRaises(ServingError):q.reserve('B',2)
        q.refund('A',5);self.assertEqual(q.remaining('A'),13)

    def test_unicode_stream_reconstruct(self):
        text='A🤖é B🌍'
        self.assertEqual(''.join(c.body for c in chunk_response(text,4)),text)
        self.assertEqual(chunk_response(text,4)[-1].final_sha256,hashlib.sha256(text.encode()).hexdigest())
        with self.assertRaises(ServingError):chunk_response(text,1)

    def test_negative_token_budget(self):
        self.assertEqual(admit_window(10,20,100),38)
        with self.assertRaises(ServingError):admit_window(90,20,100)

    def test_receipt_changes_when_output_changes(self):
        r=Receipt('A','id',I,'b'*64,'c'*64,3,2,'stop',100)
        self.assertEqual(len(r.digest),64)

    def test_model_gateway_end_to_end(self):
        native=TinyNative()
        slot=ModelSlot(native,I)
        runner=ServingEngine(slot,Limits(context_tokens=1024,output_tokens=128))
        gen,rec=runner.run(req(tokens=8),I)
        self.assertEqual(native.calls,1)
        self.assertEqual(native.max_tokens,[8])
        self.assertEqual(gen.text,'Verified response')
        self.assertEqual(rec.output_sha256,hashlib.sha256(gen.text.encode()).hexdigest())
        self.assertEqual(runner.usage.get('A'),(3,2))
        self.assertTrue(runner.health.snapshot()['healthy'])
        slot.close(time.monotonic_ns()+1_000_000_000)
        self.assertTrue(native.closed)

    def test_epoch_fence(self):
        native=TinyNative();slot=ModelSlot(native,I)
        with self.assertRaises(ServingError):
            ServingEngine(slot,Limits()).run(req(),ModelIdentity(D,D,2))
        slot.fence.acquire(I)
        with self.assertRaises(ServingError):slot.fence.replace(ModelIdentity(D,D,2))
        slot.fence.release();slot.fence.replace(ModelIdentity(D,D,2))

    def test_invalid_request_types(self):
        with self.assertRaises(ServingError):Request('A','id',(('tool','bad'),),8,0,.8,time.monotonic_ns()+1_000_000)
        with self.assertRaises(ServingError):req(tokens=0)
        with self.assertRaises(ServingError):req(deadline=-1)
