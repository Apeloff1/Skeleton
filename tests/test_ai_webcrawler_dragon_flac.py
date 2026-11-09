"""FLAC native STREAMINFO metadata without audio/tag decode."""
from __future__ import annotations
import unittest
from skeleton.ai.webcrawler.flac_metadata import extract_flac
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def flac(rate=44100,channels=2,bits=16,total=88200):
    packed=(rate<<44)|((channels-1)<<41)|((bits-1)<<36)|total
    info=(16).to_bytes(2,"big")*2+b"\x00"*6+packed.to_bytes(8,"big")+b"\x00"*16
    return b"fLaC"+b"\x80"+(34).to_bytes(3,"big")+info


class FLACMetadataTests(unittest.TestCase):
    def test_streaminfo_is_measured_not_decoded(self):
        row=extract_flac(flac())
        self.assertIn("sampling_hz: 44100",row.text)
        self.assertIn("2.000",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_missing_streaminfo_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_flac(flac().replace(b"\x80",b"\x81",1))

    def test_outside_sampling_range_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_flac(flac(rate=400000))

    def test_truncated_streaminfo_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_flac(flac()[:-2])


if __name__=="__main__":
    unittest.main()
