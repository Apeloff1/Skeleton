"""Bounded Opus-in-Ogg identification, without media replay."""
from __future__ import annotations
import struct
import unittest
from skeleton.ai.webcrawler.ogg_metadata import extract_ogg_opus
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def opus(channels=2,rate=48000):
    ident=(b"OpusHead"+bytes([1,channels])+struct.pack("<H",312)
           +struct.pack("<I",rate)+b"\x00\x00\x00")
    page=b"OggS"+bytes([0,2])+b"\x00"*20+bytes([1, len(ident)])+ident
    return page


class OpusTests(unittest.TestCase):
    def test_header_is_captured_without_transcription(self):
        row=extract_ogg_opus(opus())
        self.assertIn("Opus-in-Ogg",row.text)
        self.assertIn("48000",row.text)
        self.assertEqual(row.links,())

    def test_non_bos_page_denied(self):
        value=opus().replace(b"OggS\x00\x02",b"OggS\x00\x00")
        with self.assertRaises(ResearchFormatError):
            extract_ogg_opus(value)

    def test_truncated_segment_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ogg_opus(opus()[:-1])

    def test_channel_overflow_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ogg_opus(opus(channels=40))


if __name__=="__main__":
    unittest.main()
