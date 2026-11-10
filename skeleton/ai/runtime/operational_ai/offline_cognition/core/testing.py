"""Run domain-specific positive and adversarial cases against actual core algorithms.

A production model may never be substituted with this test-only FakeWorker.
Tests run against source-bound transforms and real temporary SQLite metadata.
"""
from __future__ import annotations
import importlib
import tempfile
from .contracts import Scope,CognitionError,hash_bytes
from .profiles import read_profile

BASE="skeleton.ai.runtime.operational_ai.offline_cognition.families"

def _module(family,operation):
    from skeleton.ai.runtime.operational_ai.offline_cognition.catalog import FAMILIES
    if family not in FAMILIES:
        raise CognitionError("unregistered capability family")
    return importlib.import_module(BASE+"."+family+"."+operation)

def exercise(family,operation,*,attack=False):
    p=read_profile(family)
    if operation not in p.operations:raise CognitionError("unknown operational boundary")
    m=_module(family,operation)
    scope=Scope("local","owner","a"*64,"b"*64)
    if operation=="source":
        raw=b"Actual source text about private offline model retrieval and precise receipts. "*16
        if attack:
            try:m.ingest(raw,source_id="doc",tenant="local",subject="owner",approved=False)
            except CognitionError:return True
            return False
        result=m.ingest(raw,source_id="doc",tenant="local",subject="owner",approved=True)
        return result["source_sha256"]==hash_bytes(raw) and len(m.partition(raw))>=1
    if operation=="search":
        from .retrieval import IndexedDocument
        docs=(IndexedDocument("doc1","local","a"*64,"offline inference and lexical evidence"),
              IndexedDocument("doc2","other","b"*64,"offline inference and lexical evidence"))
        result=m.query(docs,"offline",scope="other" if attack else "local")
        return len(result)==1 and result[0][0]==("doc2" if attack else "doc1")
    if operation=="fusion":
        rows=(("doc1",1.0,"other" if attack else "local"),)
        if attack:
            try:m.combine(rows,rows,scope="local")
            except CognitionError:return True
            return False
        output=m.combine(rows,rows,scope="local")
        return output==("doc1",)
    if operation=="rank":
        from .ranker import RankedSource
        rows=(RankedSource("doc1","local","a"*64,.9,.8,.7,True),
              RankedSource("doc2","local","b"*64,.9,.8,.7,False))
        result=m.score(rows,scope="other" if attack else "local")
        return result==() if attack else len(result)==1 and result[0][0]=="doc1"
    if operation=="context":
        from .contexts import ContextSlice
        rows=(ContextSlice("system","system","a"*64,100,10,True),
              ContextSlice("user","user","b"*64,100,10,True))
        if attack:
            try:m.assemble(rows[:1])
            except CognitionError:return True
            return False
        return set(m.assemble(rows)["selected"])=={"system","user"}
    if operation=="plan":
        from .planner import PlanTask
        a=PlanTask("source",100,0,"retrieval",())
        b=PlanTask("generate",200,128,"model",("source",))
        if attack:
            bad=(PlanTask("a",100,0,"retrieval",("b",)),
                 PlanTask("b",100,0,"retrieval",("a",)))
            try:m.compile(bad)
            except CognitionError:return True
            return False
        result=m.compile((b,a))
        return result["order"]==("source","generate") and result["critical_path_ms"]==300
    if operation=="resource":
        from .budget import Resource
        cap=Resource(512,1000,1000,2)
        need=Resource(128,100,100,1)
        if attack:
            result=m.reserve(Resource(1,100,100,1),(("oversize",need),))
            return result["held"]==("oversize",)
        result=m.reserve(cap,(("task",need),))
        return result["admitted"]==("task",)
    if operation=="schedule":
        from .scheduler import Task
        queue=m.enqueue((Task("task","local",128,1,1000),))
        result=m.admit(queue,now_ns=1000 if attack else 10,tokens=128)
        return result["expired"]==("task",) if attack else result["admitted"]==("task",)
    if operation=="permission":
        from .admission import Permit
        permit=Permit(scope,"c"*64,"read_source",1,100,200,True)
        if attack:
            try:m.inspect(permit,scope,operation="read_source",now_ns=200,source_sha256="c"*64)
            except CognitionError:return True
            return False
        result=m.inspect(permit,scope,operation="read_source",now_ns=150,source_sha256="c"*64)
        return result["permitted"] and not result["external_source_authenticated_by_this_function"]
    if operation=="native":
        from skeleton.testing.laptop_runtime_test_support import FakeWorker
        worker=FakeWorker();worker.spine.create("s_1")
        if attack:
            wrong=Scope("local","owner","c"*64,"b"*64)
            try:m.generate(worker,wrong,"s_1","r1","hello")
            except CognitionError:return worker.generation_calls==0
            return False
        receipt=m.generate(worker,scope,"s_1","r1","hello")
        return receipt.text=="hello" and worker.generation_calls==1
    if operation=="replay":
        from skeleton.testing.laptop_runtime_test_support import FakeWorker
        worker=FakeWorker();worker.spine.create("s_1")
        if attack:
            got=m.read(worker,scope,"s_1","unseen","hello")
            return got is None and worker.generation_calls==0
        worker.turn("s_1","r1","hello")
        receipt=m.read(worker,scope,"s_1","r1","hello")
        return receipt.replayed and worker.generation_calls==1
    if operation=="memory":
        from .memory import MemoryCatalog
        with tempfile.TemporaryDirectory() as temp:
            with MemoryCatalog(temp+"/metadata.sqlite") as catalog:
                m.remember(catalog,scope,"doc","c"*64,length=12,now_ns=100,expires_ns=200)
                if attack:
                    wrong=Scope("other","owner","a"*64,"b"*64)
                    return m.recall(catalog,wrong,now_ns=150)==()
                count=len(m.recall(catalog,scope,now_ns=150))
                removed=m.forget(catalog,scope,"doc",revision=1,now_ns=160)
                return count==1 and removed["tombstoned"] and not removed["physical_payload_erasure_proved"]
    if operation=="privacy":
        from .metrics import Metrics
        sink=Metrics(maximum=2)
        if attack:
            try:m.record(sink,"token_leak",elapsed_ms=100)
            except CognitionError:return True
            return False
        m.record(sink,"accepted",elapsed_ms=100)
        data=m.snapshot(sink)
        return data["sample_count"]==1 and data["secret_bytes_stored"]==0
    if operation=="evaluate":
        from .evaluation import EvaluationCase
        cases=tuple(EvaluationCase("case"+str(i),"a"*64,"b"*64,
                    "b"*64 if i%2 else "c"*64,True) for i in range(8))
        if attack:
            try:m.run(({"not":"a receipt"},))
            except CognitionError:return True
            return False
        result=m.run(cases)
        return result["passed"]==4 and result["wilson_lower"]<.5
    if operation=="audit":
        from .audit import Audit
        if attack:
            try:m.append(None,"event",{})
            except CognitionError:return True
            return False
        ledger=Audit("local");m.append(ledger,"first",{"sha":"a"*64})
        m.append(ledger,"second",{"sha":"b"*64})
        return m.verify(ledger)["count"]==2
    if operation=="recover":
        from skeleton.testing.laptop_runtime_test_support import FakeWorker
        worker=FakeWorker();worker.spine.create("s_1")
        if not attack:worker.turn("s_1","r1","hello")
        state=m.reconcile(worker,scope,"s_1","r1","hello")
        return (state["state"]=="native-effect-unknown" and not state["auto_retry"]) if attack else (
            state["state"]=="spine-committed" and worker.generation_calls==1)
    if operation=="stream":
        value="Snow ☃ emitted"
        if attack:
            try:m.postcommit(value,"a"*64)
            except CognitionError:return True
            return False
        body=m.drain(m.postcommit(value,hash_bytes(value.encode("utf-8")),frame_bytes=5,credit=1))
        return "".join(v["text"] for v in body["frames"])==value and not body["native_live_streaming_proved"]
    if operation=="tool":
        if attack:
            try:m.request(scope,request_id="r1",tool="shell",
                          args={"source_id":"doc","limit":1},expires_ns=200)
            except CognitionError:return True
            return False
        intent=m.request(scope,request_id="r1",tool="read_source",
                         args={"source_id":"doc","limit":1},expires_ns=200)
        return m.status(intent,scope,now_ns=150)["executable"] is False
    if operation=="checkpoint":
        from .audit import Audit
        if attack:
            try:m.capture(None,scope,"a"*64)
            except CognitionError:return True
            return False
        chain=Audit("local");chain.record("created",{"id":"source"})
        item=m.capture(chain,scope,"c"*64)
        return len(item["sha256"])==64 and item["external_checkpoint_signature"] is False
    if operation=="health":
        from .budget import Resource
        if attack:
            try:m.resources(None,Resource(1,1,1,1))
            except CognitionError:return True
            return False
        result=m.resources(Resource(1024,10000,5000,4),
                           Resource(128,1000,100,1))
        return result["admitted"] and result["laptop_device_qualified"] is False
    raise CognitionError("unknown operation")
