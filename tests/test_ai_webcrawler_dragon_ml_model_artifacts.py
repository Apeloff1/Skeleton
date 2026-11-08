"""Inert safetensors/GGUF/ONNX model topology, bounds, canonical replay."""
from __future__ import annotations
import json
import struct
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.safetensors_metadata import extract_safetensors
from skeleton.ai.webcrawler.gguf_metadata import extract_gguf
from skeleton.ai.webcrawler.onnx_metadata import extract_onnx
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import CrawlPolicy,FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun


def safe_file(shape=None,offsets=None,metadata=None):
    info={
        "__metadata__":metadata or {"name":"SECRET_MODEL_ATTRIBUTE"},
        "model_weight":{
            "dtype":"F32","shape":shape if shape is not None else [2,2],
            "data_offsets":offsets if offsets is not None else [0,16],
        },
    }
    header=json.dumps(info,separators=(",",":")).encode()
    return struct.pack("<Q",len(header))+header+b"\x00"*16


def gguf_string(value):
    raw=value.encode()
    return struct.pack("<Q",len(raw))+raw


def gguf_file(tensors=1):
    header=b"GGUF"+struct.pack("<IQQ",3,tensors,2)
    header+=gguf_string("general.architecture")+struct.pack("<I",8)
    header+=gguf_string("SECRET_ARCH_PRIVATE")
    header+=gguf_string("general.alignment")+struct.pack("<II",4,32)
    for i in range(tensors):
        header+=gguf_string(f"private_model_tensor_{i}")
        header+=struct.pack("<IQQIQ",2,2,4,0,0)
    return header


def v(value):
    payload=[]
    while value>=128:
        payload.append((value&127)|128)
        value>>=7
    payload.append(value)
    return bytes(payload)


def field(number,wire,value):
    head=v(number*8+wire)
    if wire==0:
        return head+v(value)
    if wire==2:
        return head+v(len(value))+value
    raise AssertionError("test wire type unsupported")


def onnx_file():
    node1=field(4,2,b"MatMul")
    node2=field(4,2,b"Relu")
    graph=(
        field(1,2,node1)
        +field(1,2,node2)
        +field(5,2,b"SECRET_WEIGHT_BINARY_BYTES")
        +field(11,2,b"")
        +field(12,2,b"")
    )
    return field(1,0,10)+field(7,2,graph)


class SafetensorsTests(unittest.TestCase):
    def test_exact_complete_tensor_framing_and_privacy(self):
        row=extract_safetensors(safe_file())
        self.assertIn("Tensor declarations: 1",row.text)
        self.assertIn("scalar elements declared: 4",row.text)
        self.assertIn("F32=1",row.text)
        self.assertIn("tensor payload bytes: 16",row.text)
        self.assertNotIn("model_weight",row.text)
        self.assertNotIn("SECRET_MODEL_ATTRIBUTE",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_dtype_size_mismatch_fail_closed(self):
        with self.assertRaises(ResearchFormatError):
            extract_safetensors(safe_file(shape=[3,2]))

    def test_out_of_bounds_and_overlap_fail_closed(self):
        for bad in ([0,17],[0,15],[3,16],[16,0]):
            with self.subTest(bad=bad),self.assertRaises(ResearchFormatError):
                extract_safetensors(safe_file(offsets=bad))

    def test_duplicate_json_tensor_name_refused(self):
        raw=(b'{"m":{"dtype":"F32","shape":[1],"data_offsets":[0,4]},'
             b'"m":{"dtype":"F32","shape":[1],"data_offsets":[4,8]}}')
        with self.assertRaises(ResearchFormatError):
            extract_safetensors(struct.pack("<Q",len(raw))+raw+b"\x00"*8)

    def test_header_bomb_and_truncated_weight_body_refused(self):
        with self.assertRaises(ResearchFormatError):
            extract_safetensors(struct.pack("<Q",2000000)+b"{}")
        with self.assertRaises(ResearchFormatError):
            extract_safetensors(safe_file()[:-1])


class GGUFTests(unittest.TestCase):
    def test_header_and_tensor_directory_without_weight_loading(self):
        row=extract_gguf(gguf_file())
        self.assertIn("Tensors declared: 1; metadata fields: 2",row.text)
        self.assertIn("Claimed scalar/quantized elements: 8",row.text)
        self.assertIn("Declared data alignment: 32",row.text)
        self.assertNotIn("SECRET_ARCH_PRIVATE",row.text)
        self.assertNotIn("private_model_tensor",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_version_and_magic_rejected(self):
        for bad in (
            gguf_file().replace(b"GGUF",b"FAKE",1),
            gguf_file()[:4]+struct.pack("<I",2)+gguf_file()[8:],
        ):
            with self.subTest(bad=bad),self.assertRaises(ResearchFormatError):
                extract_gguf(bad)

    def test_truncated_tensor_shape_and_huge_count_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_gguf(gguf_file()[:-7])
        with self.assertRaises(ResearchFormatError):
            extract_gguf(gguf_file()[:8]+struct.pack("<Q",999999)+gguf_file()[16:])

    def test_gguf_rejects_duplicate_tensor_names(self):
        with self.assertRaises(ResearchFormatError):
            extract_gguf(gguf_file(tensors=2).replace(
                b"private_model_tensor_1",b"private_model_tensor_0",
            ))


class ONNXTests(unittest.TestCase):
    def test_wire_scanned_graph_nodes_and_opaque_weights(self):
        row=extract_onnx(onnx_file())
        self.assertIn("Declared ONNX IR version: 10",row.text)
        self.assertIn("Top-level graph nodes: 2",row.text)
        self.assertIn("MatMul=1",row.text)
        self.assertIn("Relu=1",row.text)
        self.assertIn("Initializer envelopes: 1",row.text)
        self.assertNotIn("SECRET_WEIGHT_BINARY_BYTES",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_proto_groups_and_no_graph_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_onnx(b"\x0b\x0c")
        with self.assertRaises(ResearchFormatError):
            extract_onnx(field(1,0,10))

    def test_missing_operator_type_denied(self):
        source=field(1,0,10)+field(7,2,field(1,2,field(3,2,b"name")))
        with self.assertRaises(ResearchFormatError):
            extract_onnx(source)

    def test_truncated_varint_and_invalid_fixed_width_refused(self):
        with self.assertRaises(ResearchFormatError):
            extract_onnx(b"\x80\x80")
        with self.assertRaises(ResearchFormatError):
            extract_onnx(field(1,0,10)+b"\x09\x01")

    def test_large_field_size_refused_before_allocation(self):
        with self.assertRaises(ResearchFormatError):
            extract_onnx(field(1,0,10)+v(7*8+2)+v(2000000))


class Transport:
    timeout_seconds=4
    transport_mode="scripted_ml_model_source"
    def __init__(self,mime,blob):
        self.mime,self.blob,self.calls=mime,blob,[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/model":
            raise AssertionError("model metadata attempted new network request")
        if len(self.blob)>max_bytes:
            raise AssertionError("mock model transport exceeded reserved bytes")
        return FetchResponse(url,200,{"content-type":self.mime},
                             self.blob,time.time())


class CanonicalMLSourceTests(unittest.TestCase):
    def capture(self,mime,blob):
        now=time.time()
        transport=Transport(mime,blob)
        run=CrawlRun.create(
            CrawlRequest(seed_urls=("https://example.com/model",),
                allowed_hosts=("example.com",),max_requests=4,
                max_documents=2,max_depth=1,
                max_response_bytes=65536,max_total_bytes=131072),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"ml-model-source-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,"expires_at":now+3600},
            now=now,fetcher=transport)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,
                    authorize=lambda:None,cancelled=lambda:False,
                    on_checkpoint=lambda snap,event:None)
        return run,transport

    def test_canonical_three_ml_formats_capture_and_exact_replay(self):
        for mime,blob,marker in (
            ("application/vnd.safetensors",safe_file(),"Tensor declarations: 1"),
            ("application/vnd.gguf",gguf_file(),"GGUF v3"),
            ("application/onnx",onnx_file(),"MatMul=1"),
        ):
            with self.subTest(mime=mime):
                run,transport=self.capture(mime,blob)
                snapshot=run.snapshot()
                self.assertEqual(snapshot["usage"]["requests"],2)
                self.assertEqual(snapshot["usage"]["documents"],1)
                self.assertEqual(snapshot["frontier"],[])
                self.assertEqual(len(transport.calls),2)
                item=run.sources()[0]
                self.assertIn(marker,item["text"])
                self.assertEqual(item["review_state"],"unreviewed")
                self.assertFalse(item["provenance"]["training_permission"])
                self.assertFalse(item["provenance"]["raw_bytes_retained"])
                self.assertEqual(CrawlRun.from_snapshot(snapshot,fetcher=transport).snapshot(),snapshot)

    def test_invalid_ml_header_charges_request_not_retains_source(self):
        run,transport=self.capture("application/vnd.safetensors",b"\x00"*40)
        self.assertEqual(run.snapshot()["usage"]["requests"],2)
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(transport.calls),2)

    def test_exact_media_types_without_arbitrary_programs(self):
        allowed=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("application/vnd.safetensors","application/vnd.gguf","application/onnx"):
            self.assertIn(mime,allowed)
        self.assertNotIn("application/x-msdownload",allowed)


if __name__=="__main__":
    unittest.main()
