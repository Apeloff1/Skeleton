"""Binary GLB JSON-first scene inventory with no buffer processing."""
from __future__ import annotations
import json
import struct
import unittest
from skeleton.ai.webcrawler.glb_metadata import extract_glb
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def glb():
    text=json.dumps({"asset":{"version":"2.0"},"nodes":[{"name":"Wing"}],
                     "scenes":[{"nodes":[0]}]}).encode()
    text+=b" "*((-len(text))%4)
    chunk=struct.pack("<I4s",len(text),b"JSON")+text
    return struct.pack("<4sII",b"glTF",2,12+len(chunk))+chunk


class BinaryGLTFTests(unittest.TestCase):
    def test_gltf_scene_is_inert(self):
        row=extract_glb(glb())
        self.assertIn("Nodes: 1",row.text)
        self.assertIn("GLB binary container",row.text)
        self.assertEqual(row.links,())

    def test_wrong_container_version_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_glb(glb().replace(struct.pack("<I",2),struct.pack("<I",1),1))

    def test_truncated_chunk_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_glb(glb()[:-1])

    def test_invalid_chunk_order_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_glb(glb().replace(b"JSON",b"BIN\x00",1))


if __name__=="__main__":
    unittest.main()
