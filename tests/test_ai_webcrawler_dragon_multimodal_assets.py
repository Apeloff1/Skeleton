"""Binary media, archive inventory and 3D asset source-only + canonical tests."""
from __future__ import annotations

import io
import json
import struct
import time
import unittest
from unittest.mock import patch
import zipfile
import zlib

from skeleton.ai.webcrawler.binary_media_metadata import extract_binary_media_metadata
from skeleton.ai.webcrawler.zip_inventory import extract_zip_inventory
from skeleton.ai.webcrawler.obj_documents import extract_obj
from skeleton.ai.webcrawler.gltf_documents import extract_gltf
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

IHDR=struct.pack(">IIBBBBB",96,64,8,2,0,0,0)
PNG=(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",len(IHDR))
     +b"IHDR"+IHDR+struct.pack(">I",zlib.crc32(b"IHDR"+IHDR)&0xffffffff))
JPEG=(b"\xff\xd8\xff\xc0\x00\x11"+struct.pack(">BHHB",8,64,96,3)
      +b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"+b"\xff\xd9")
GIF=b"GIF89a"+struct.pack("<HH",96,64)+b"\x00\x00\x00"
PCM=b"\x00\x00\x00\x00"
FMT=struct.pack("<HHIIHH",1,1,8000,16000,2,16)
WAV_BODY=(b"WAVE"+b"fmt "+struct.pack("<I",16)+FMT
          +b"data"+struct.pack("<I",len(PCM))+PCM)
WAV=b"RIFF"+struct.pack("<I",len(WAV_BODY))+WAV_BODY
ZIP_BYTES=io.BytesIO()
with zipfile.ZipFile(ZIP_BYTES,"w",compression=zipfile.ZIP_STORED) as z:
    z.writestr("models/plane.obj","v 0 0 0\n")
    z.writestr("docs/readme.md","Wing physics and original models\n")
ZIP=ZIP_BYTES.getvalue()
OBJ=("o Original aircraft\n"
     "v 0.0 0.0 0.0\nv 2.0 0.0 0.0\nv 0.0 1.0 0.0\n"
     "g wing\nf 1 2 3\n"
     "mtllib https://outside.example.net/untrusted.mtl\n")
GLTF=json.dumps({
    "asset":{"version":"2.0","generator":"UNTRUSTED_SOURCE"},
    "scene":0,
    "scenes":[{"nodes":[0]}],
    "nodes":[{"name":"Aircraft","children":[1]},{"name":"Wing","mesh":0}],
    "meshes":[{"name":"Original flight mesh","primitives":[]}],
    "materials":[{"name":"Wing surface"}],
    "buffers":[{"uri":"https://outside.example.net/secret.bin","byteLength":100}],
    "images":[{"uri":"https://outside.example.net/secret.png"}],
    "animations":[]
})


class BinaryParserTests(unittest.TestCase):
    def test_png_header_crc_dimensions(self):
        row=extract_binary_media_metadata(PNG,"image/png")
        self.assertIn("96 x 64",row.text)
        self.assertIn("Pixels and EXIF",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_png_crc_corruption_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_binary_media_metadata(PNG[:-1]+b"\x01","image/png")

    def test_png_billion_pixel_dimensions_denied(self):
        hdr=struct.pack(">IIBBBBB",16384,16384,8,2,0,0,0)
        raw=(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",len(hdr))+b"IHDR"
             +hdr+struct.pack(">I",zlib.crc32(b"IHDR"+hdr)&0xffffffff))
        with self.assertRaises(ResearchFormatError):
            extract_binary_media_metadata(raw,"image/png")

    def test_jpeg_sof_without_exif(self):
        row=extract_binary_media_metadata(JPEG,"image/jpeg")
        self.assertIn("96 x 64",row.text)
        self.assertNotIn("UNTRUSTED_SOURCE",row.text)

    def test_jpeg_invalid_marker_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_binary_media_metadata(b"\xff\xd8\xff\xd9","image/jpeg")

    def test_gif_screen_dimensions_without_animation(self):
        row=extract_binary_media_metadata(GIF,"image/gif")
        self.assertIn("96 x 64",row.text)
        self.assertIn("not decoded",row.text)

    def test_wave_pcm_duration_not_transcribed(self):
        row=extract_binary_media_metadata(WAV,"audio/wav")
        self.assertIn("WAV PCM",row.text)
        self.assertIn("duration_seconds_from_header:",row.text)
        self.assertEqual(row.links,())

    def test_wave_forged_length_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_binary_media_metadata(WAV[:-1],"audio/wav")

    def test_wave_invalid_sample_format_denied(self):
        value=WAV.replace(FMT,struct.pack("<HHIIHH",3,1,8000,16000,2,16))
        with self.assertRaises(ResearchFormatError):
            extract_binary_media_metadata(value,"audio/wav")


class AssetParserTests(unittest.TestCase):
    def test_zip_inventory_no_file_extraction(self):
        row=extract_zip_inventory(ZIP)
        self.assertIn("Extension class .obj: 1",row.text)
        self.assertIn("Extension class .md: 1",row.text)
        self.assertNotIn("models/plane.obj",row.text)
        self.assertEqual(row.links,())

    def test_zip_path_traversal_rejected(self):
        blob=io.BytesIO()
        with zipfile.ZipFile(blob,"w") as z:
            z.writestr("../../private.key","bad")
        with self.assertRaises(ResearchFormatError):
            extract_zip_inventory(blob.getvalue())

    def test_zip_duplicate_path_rejected(self):
        blob=io.BytesIO()
        with zipfile.ZipFile(blob,"w") as z:
            z.writestr("A.txt","one")
            z.writestr("a.txt","two")
        with self.assertRaises(ResearchFormatError):
            extract_zip_inventory(blob.getvalue())

    def test_obj_vertex_face_and_groups(self):
        row=extract_obj(OBJ)
        self.assertIn("Vertices: 3; faces: 1",row.text)
        self.assertIn("wing",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertEqual(row.links,())

    def test_obj_face_index_missing_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_obj("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 99")

    def test_obj_nan_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_obj("v NaN 0 0")

    def test_gltf_scene_graph_no_external_buffer_fetch(self):
        row=extract_gltf(GLTF)
        self.assertIn("Nodes: 2; graph edges: 1",row.text)
        self.assertIn("Original flight mesh",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_gltf_node_cycle_denied(self):
        value=json.loads(GLTF)
        value["nodes"][1]["children"]=[0]
        with self.assertRaises(ResearchFormatError):
            extract_gltf(json.dumps(value))

    def test_gltf_unknown_mesh_denied(self):
        value=json.loads(GLTF)
        value["nodes"][1]["mesh"]=100
        with self.assertRaises(ResearchFormatError):
            extract_gltf(json.dumps(value))

    def test_gltf_duplicate_keys_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_gltf('{"asset":{"version":"2.0"},"nodes":[],"nodes":[]}')


class AssetTransport:
    timeout_seconds=4
    transport_mode="scripted_multimodal_metadata"
    def __init__(self,mime,body):
        self.mime,self.body,self.calls=mime,body,[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/asset":
            raise AssertionError("asset generated an unsolicited outbound request")
        if len(self.body)>max_bytes:
            raise AssertionError("mock media exceeded transport reserve")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())


class CanonicalAssetCaptureTests(unittest.TestCase):
    def capture(self,mime,body):
        now=time.time()
        fetcher=AssetTransport(mime,body)
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/asset",),
                allowed_hosts=("example.com",),
                max_requests=4,max_documents=2,max_depth=1,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"multimodal-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,
                     "expires_at":now+3600},
            now=now,fetcher=fetcher,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,
                              authorize=lambda:None,cancelled=lambda:False,
                              on_checkpoint=lambda snapshot,event:None)
        return run,fetcher

    def test_canonical_multimodal_sources_are_bounded_unreviewed(self):
        cases=(
            ("image/png",PNG,"96 x 64"),
            ("image/jpeg",JPEG,"96 x 64"),
            ("image/gif",GIF,"96 x 64"),
            ("audio/wav",WAV,"WAV PCM"),
            ("application/zip",ZIP,"Extension class .obj"),
            ("model/obj",OBJ.encode(),"Vertices: 3"),
            ("model/gltf+json",GLTF.encode(),"Nodes: 2"),
        )
        for mime,body,expected in cases:
            with self.subTest(mime=mime):
                run,fetcher=self.capture(mime,body)
                state=run.snapshot()
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(len(fetcher.calls),2)
                self.assertEqual(state["frontier"],[])
                self.assertIn(expected,run.sources()[0]["text"])
                self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
                self.assertFalse(run.sources()[0]["provenance"]["raw_bytes_retained"])
                self.assertEqual(
                    CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state,
                )

    def test_invalid_png_charged_but_not_retained(self):
        run,fetcher=self.capture("image/png",PNG[:-1])
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)

    def test_only_explicit_supported_mime_values(self):
        allowed=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("image/png","image/jpeg","image/gif","audio/wav",
                     "application/zip","model/obj","model/gltf+json"):
            self.assertIn(mime,allowed)


if __name__=="__main__":
    unittest.main()
