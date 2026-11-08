"""Read-only ICO directory resource bounds and non-overlap."""
from __future__ import annotations
import struct
import unittest
from skeleton.ai.webcrawler.ico_metadata import extract_ico
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def ico(offset=22,length=8):
    return (struct.pack("<HHH",0,1,1)+struct.pack("<BBBBHHII",
            32,32,0,0,1,32,length,offset)+b"\x89PNG1234")


class ICOTests(unittest.TestCase):
    def test_index_dimensions_and_size(self):
        row=extract_ico(ico())
        self.assertIn("32 x 32",row.text)
        self.assertIn("bytes: 8",row.text)
        self.assertEqual(row.links,())

    def test_directory_points_before_header_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_ico(ico(offset=0))

    def test_resource_length_out_of_bounds_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_ico(ico(length=100))

    def test_wrong_icon_container_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_ico(ico().replace(struct.pack("<HHH",0,1,1),
                                      struct.pack("<HHH",0,2,1),1))


if __name__=="__main__":
    unittest.main()
