"""Binary STL finite triangles, invalid mesh and coordinate rejection."""
from __future__ import annotations
import struct
import unittest
from skeleton.ai.webcrawler.stl_metadata import extract_binary_stl
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def stl():
    values=(0,0,1,0,0,0,2,0,0,0,1,0)
    return b"\x00"*80+struct.pack("<I",1)+struct.pack("<12fH",*values,0)


class STLTests(unittest.TestCase):
    def test_triangle_count_and_bounds(self):
        row=extract_binary_stl(stl())
        self.assertIn("Triangles: 1",row.text)
        self.assertIn("2.00",row.text)
        self.assertEqual(row.links,())

    def test_declared_count_mismatch_rejected(self):
        value=stl()[:80]+struct.pack("<I",2)+stl()[84:]
        with self.assertRaises(ResearchFormatError):
            extract_binary_stl(value)

    def test_nonfinite_mesh_coordinate_rejected(self):
        data=bytearray(stl())
        data[96:100]=struct.pack("<f",float("nan"))
        with self.assertRaises(ResearchFormatError):
            extract_binary_stl(bytes(data))

    def test_malformed_triangle_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_binary_stl(stl()[:-2])


if __name__=="__main__":
    unittest.main()
