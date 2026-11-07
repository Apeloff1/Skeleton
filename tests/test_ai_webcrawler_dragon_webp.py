"""WebP real byte signature and dimension guard contract."""
from __future__ import annotations
import struct
import unittest
from skeleton.ai.webcrawler.webp_metadata import extract_webp
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def vp8x(w=64,h=128):
    chunk=b"\x00"*4+(w-1).to_bytes(3,"little")+(h-1).to_bytes(3,"little")
    payload=b"WEBP"+b"VP8X"+struct.pack("<I",len(chunk))+chunk
    return b"RIFF"+struct.pack("<I",len(payload))+payload


class WebPTests(unittest.TestCase):
    def test_extended_webp_identifies_dimensions(self):
        row=extract_webp(vp8x())
        self.assertIn("64 x 128",row.text)
        self.assertFalse(row.body_executed)
        self.assertEqual(row.links,())

    def test_riff_size_forgery_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_webp(vp8x()[:-1])

    def test_dimension_bomb_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_webp(vp8x(16384,16384))

    def test_wrong_riff_container_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_webp(vp8x().replace(b"WEBP",b"RIFF"))


if __name__=="__main__":
    unittest.main()
