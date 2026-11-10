"""Finite SVG, PLY and OFF structures without rendering or network access."""
from __future__ import annotations
import unittest
from skeleton.ai.webcrawler.svg_inventory import extract_svg
from skeleton.ai.webcrawler.ply_inventory import extract_ply
from skeleton.ai.webcrawler.off_inventory import extract_off
from skeleton.ai.webcrawler.research_projection import ResearchFormatError

SVG=(
    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240" '
    'viewBox="0 0 320 240">'
    '<title>Original aircraft diagram</title>'
    '<rect x="0" y="0" width="320" height="240"/>'
    '<path d="M 0 0 L 30 30"/>'
    '<circle cx="10" cy="10" r="5"/>'
    '<image href="https://outside.example.net/private.png"/>'
    '</svg>'
)
PLY=(
    "ply\nformat ascii 1.0\n"
    "element vertex 3\n"
    "property float x\nproperty float y\nproperty float z\n"
    "element face 1\nproperty list uchar int vertex_indices\n"
    "end_header\n"
    "0 0 0\n2 0 0\n0 1 0\n3 0 1 2\n"
)
OFF="OFF\n3 1 3\n0 0 0\n2 0 0\n0 1 0\n3 0 1 2\n"


class SVGInventoryTests(unittest.TestCase):
    def test_shape_counts_without_remote_image_fetch(self):
        row=extract_svg(SVG)
        self.assertIn("Canvas width: 320; height: 240",row.text)
        self.assertIn("Vector primitive path: 1",row.text)
        self.assertIn("Vector primitive image: 1",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)
        self.assertFalse(row.reference_trusted)

    def test_external_entities_never_resolve(self):
        payload='<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg>&x;</svg>'
        with self.assertRaises(ResearchFormatError):
            extract_svg(payload)

    def test_script_and_foreign_object_denied(self):
        for markup in (
            '<svg><script>fetch("https://outside.example.net")</script></svg>',
            '<svg><foreignObject><div>bad</div></foreignObject></svg>',
            '<svg><rect onload="alert(1)"/></svg>',
        ):
            with self.subTest(markup=markup),self.assertRaises(ResearchFormatError):
                extract_svg(markup)

    def test_billion_pixel_viewbox_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_svg('<svg viewBox="0 0 1e40 1e40"></svg>')

    def test_unbounded_elements_rejected(self):
        raw="<svg>"+("<rect/>"*16385)+"</svg>"
        with self.assertRaises(ResearchFormatError):
            extract_svg(raw)

    def test_invalid_xml_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_svg("<svg><rect></svg>")


class PLYInventoryTests(unittest.TestCase):
    def test_xyz_bounds_and_faces(self):
        row=extract_ply(PLY)
        self.assertIn("Vertices: 3; polygon faces: 1",row.text)
        self.assertIn("2.00",row.text)
        self.assertEqual(row.links,())

    def test_binary_ply_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ply(PLY.replace("format ascii 1.0","format binary_little_endian 1.0"))

    def test_nonfinite_vertex_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ply(PLY.replace("2 0 0","NaN 0 0"))

    def test_truncated_body_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ply(PLY.replace("3 0 1 2\n",""))

    def test_face_index_out_of_range_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ply(PLY.replace("3 0 1 2","3 0 1 99"))

    def test_vertex_capacity_guard(self):
        with self.assertRaises(ResearchFormatError):
            extract_ply(PLY.replace("element vertex 3","element vertex 100001"))


class OFFInventoryTests(unittest.TestCase):
    def test_off_geometry_inventory(self):
        row=extract_off(OFF)
        self.assertIn("Vertices: 3; faces: 1",row.text)
        self.assertIn("2.00",row.text)
        self.assertEqual(row.links,())

    def test_off_out_of_range_face_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_off(OFF.replace("3 0 1 2","3 0 1 4"))

    def test_off_nonfinite_geometry_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_off(OFF.replace("2 0 0","Infinity 0 0"))

    def test_off_truncated_body_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_off(OFF.replace("0 1 0\n",""))


if __name__=="__main__":
    unittest.main()
