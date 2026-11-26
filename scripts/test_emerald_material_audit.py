import io
import struct
import unittest
import zlib

from audit_emerald_materials import audit_materials,dimensions,PNG_MAGIC


def chunk(name,raw):
    return struct.pack(">I",len(raw))+name+raw+struct.pack(">I",zlib.crc32(name+raw)&0xffffffff)


def fixture(width=2,height=2):
    raw=PNG_MAGIC+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,6,0,0,0))+chunk(b"IEND",b"")
    doc={"bufferViews":[{"buffer":0,"byteLength":len(raw)}],
         "images":[{"bufferView":0,"mimeType":"image/png"}],"textures":[{"source":0}],
         "materials":[{"pbrMetallicRoughness":{"baseColorTexture":{"index":0}},"normalTexture":{"index":0}}],
         "meshes":[{"primitives":[{"material":0,"attributes":{"TEXCOORD_0":0}}]}]}
    return raw,doc


def inspect(raw,doc):
    return audit_materials(io.BytesIO(raw),doc,0,len(raw))


class MaterialTests(unittest.TestCase):
    def test_image_roles_and_dimensions(self):
        raw,doc=fixture()
        result=inspect(raw,doc)
        self.assertEqual(result["total_header_pixels"],4)
        self.assertEqual(result["material_bound_primitives"],1)
        self.assertTrue(result["images"][0]["multiple_color_interpretations"])

    def test_invalid_header_and_tail(self):
        raw,doc=fixture()
        bad=bytearray(raw);bad[20]^=1
        with self.assertRaisesRegex(ValueError,"CRC"):inspect(bytes(bad),doc)
        bad=bytearray(raw);bad[-1]^=1
        with self.assertRaisesRegex(ValueError,"IEND"):inspect(bytes(bad),doc)

    def test_oversized_and_external(self):
        with self.assertRaisesRegex(ValueError,"dimensions"):inspect(*fixture(32768,2))
        raw,doc=fixture();doc["images"][0]["uri"]="https://example.invalid/texture.png"
        with self.assertRaisesRegex(ValueError,"external"):inspect(raw,doc)

    def test_invalid_reference_and_missing_uv(self):
        raw,doc=fixture();doc["textures"][0]["source"]=1
        with self.assertRaisesRegex(ValueError,"texture source"):inspect(raw,doc)
        raw,doc=fixture();del doc["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"]
        with self.assertRaisesRegex(ValueError,"missing UV"):inspect(raw,doc)

    def test_jpeg_frame_header(self):
        sof=bytes([8])+struct.pack(">HHB",5,7,1)+bytes([1,0x11,0])
        raw=b"\xff\xd8\xff\xc0"+struct.pack(">H",len(sof)+2)+sof
        self.assertEqual(dimensions(raw,"image/jpeg"),(7,5,8,1))


if __name__=="__main__":
    unittest.main()
