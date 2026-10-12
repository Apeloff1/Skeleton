"""Real raster inspection of AI-authored game assets against regional canon."""
from __future__ import annotations

from copy import deepcopy
import binascii
import struct
import unittest
import zlib

from skeleton.ai.game_builder.story_asset_pixels import (
    AssetPixelError, inspect_png_against_canon, compare_reused_asset)
from tests.test_game_builder_story_canon_fabric import canonical_bible


def _chunk(kind,data):
    return (struct.pack(">I",len(data))+kind+data+
            struct.pack(">I",binascii.crc32(kind+data)&0xffffffff))


def png(colors):
    raw=b"\0"+b"".join(bytes(rgb) for rgb in colors)
    head=struct.pack(">IIBBBBB",len(colors),1,8,2,0,0,0)
    return b"\x89PNG\r\n\x1a\n"+_chunk(b"IHDR",head)+_chunk(
        b"IDAT",zlib.compress(raw))+_chunk(b"IEND",b"")


class OriginalAssetPixelTests(unittest.TestCase):
    def setUp(self):
        self.bible=canonical_bible()
        self.original=png([(153,119,68),(204,153,68)])

    def test_full_actual_original_pixels_are_palette_approved(self):
        receipt=inspect_png_against_canon(self.bible,"map_table",self.original)
        self.assertEqual(receipt["asset"],"map_table")
        self.assertEqual(receipt["visible_pixels"],2)
        self.assertEqual(receipt["distinct_colors"],2)
        self.assertEqual(receipt["actual_palette_mismatch_pixels"],0)
        self.assertTrue(receipt["actual_binary_inspected"])
        self.assertFalse(receipt["semantic_style_similarity_checked"])
        self.assertFalse(receipt["copyright_clearance_proven"])
        self.assertEqual(receipt,inspect_png_against_canon(
            self.bible,"map_table",self.original))

    def test_500_scenes_cannot_replace_render_without_versioning(self):
        proof=compare_reused_asset(self.bible,"map_table",
                                  self.original,self.original)
        self.assertTrue(proof["strict_pixel_identity_review"])
        self.assertTrue(proof["independent_binary_reinspection"])
        different=png([(204,153,68),(153,119,68)])
        with self.assertRaises(AssetPixelError):
            compare_reused_asset(self.bible,"map_table",self.original,different)

    def test_unauthorized_colors_or_unreviewed_assets_fail(self):
        with self.assertRaises(AssetPixelError):
            inspect_png_against_canon(self.bible,"map_table",
                                      png([(255,0,0)]))
        with self.assertRaises(AssetPixelError):
            inspect_png_against_canon(self.bible,"borrowed_tower",self.original)
        with self.assertRaises(AssetPixelError):
            inspect_png_against_canon(self.bible,"fake_asset",self.original)

    def test_real_binary_corruption_and_image_bomb_prevention(self):
        for invalid in (b"not-png",
                        self.original[:-4],
                        self.original[:16]+b"tampered"+self.original[24:],
                        b"\x89PNG\r\n\x1a\n"+
                        _chunk(b"IHDR",struct.pack(">IIBBBBB",999999,2,8,2,0,0,0))+
                        _chunk(b"IDAT",zlib.compress(b"xxx"))+
                        _chunk(b"IEND",b"")):
            with self.subTest(size=len(invalid)),self.assertRaises(AssetPixelError):
                inspect_png_against_canon(self.bible,"map_table",invalid)

    def test_palette_tolerance_requires_explicit_small_review_budget(self):
        near=png([(153,119,69)])
        with self.assertRaises(AssetPixelError):
            inspect_png_against_canon(self.bible,"map_table",near)
        receipt=inspect_png_against_canon(self.bible,"map_table",near,
                                          max_channel_delta=1)
        self.assertEqual(receipt["allowed_channel_delta"],1)
        with self.assertRaises(AssetPixelError):
            inspect_png_against_canon(self.bible,"map_table",near,
                                      max_channel_delta=25)

if __name__=="__main__":
    unittest.main()
