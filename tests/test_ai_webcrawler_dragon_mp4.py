"""Finite MP4 movie metadata with immutable box bounds."""
from __future__ import annotations
import struct
import unittest
from skeleton.ai.webcrawler.mp4_metadata import extract_mp4
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def atom(kind,payload):
    return struct.pack(">I",len(payload)+8)+kind+payload


def movie(rate=1000,duration=2300):
    mvhd=(b"\x00"*12+struct.pack(">II",rate,duration))
    return atom(b"ftyp",b"isom\x00\x00\x02\x00")+atom(b"moov",atom(b"mvhd",mvhd))


class MovieTests(unittest.TestCase):
    def test_movie_timescale_advisory(self):
        row=extract_mp4(movie())
        self.assertIn("2.300",row.text)
        self.assertIn("major_brand: isom",row.text)
        self.assertEqual(row.links,())

    def test_forged_movie_box_length_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_mp4(movie()[:-1])

    def test_zero_movie_timescale_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_mp4(movie(rate=0))

    def test_missing_movie_header_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_mp4(atom(b"ftyp",b"isom\x00\x00\x02\x00")+atom(b"moov",b""))


if __name__=="__main__":
    unittest.main()
