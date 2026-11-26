import io
import math
import struct
import unittest

from audit_emerald_skin import audit_geometry


def fixture(joints=(0,0,0,0)*3,weights=(255,0,0,0)*3,indices=(0,1,2)):
    raw=bytearray()
    views=[];access=[]
    def add(fmt,data,kind,component,count,normalized=False):
        while len(raw)%4:raw.append(0)
        offset=len(raw);raw.extend(struct.pack("<"+fmt*len(data),*data))
        views.append({"buffer":0,"byteOffset":offset,"byteLength":len(raw)-offset})
        access.append({"bufferView":len(views)-1,"componentType":component,"type":kind,"count":count,"normalized":normalized})
    add("f",(0,0,0,1,0,0,0,1,0),"VEC3",5126,3)
    add("B",joints,"VEC4",5121,3)
    add("B",weights,"VEC4",5121,3,True)
    add("H",indices,"SCALAR",5123,len(indices))
    return bytes(raw),{"nodes":[{"mesh":0,"skin":0},{}],"skins":[{"joints":[1]}],
                      "meshes":[{"primitives":[{"attributes":{"POSITION":0,"JOINTS_0":1,"WEIGHTS_0":2},"indices":3}]}],
                      "accessors":access,"bufferViews":views}


def inspect(raw,doc):
    return audit_geometry(io.BytesIO(raw),doc,0,len(raw))


class SkinTests(unittest.TestCase):
    def test_geometry_bounds_and_weights(self):
        r=inspect(*fixture())
        p=r["primitives"][0]
        self.assertEqual(p["local_max"],[1,1,0])
        self.assertEqual(p["max_weight_sum_error"],0)
        self.assertEqual(p["max_nonzero_skin_influences"],1)

    def test_wrong_joint_and_zero_weights(self):
        with self.assertRaisesRegex(ValueError,"joint palette"):
            inspect(*fixture(joints=(1,0,0,0)*3))
        with self.assertRaisesRegex(ValueError,"sum to one"):
            inspect(*fixture(weights=(0,0,0,0)*3))

    def test_invalid_index_and_degenerate_report(self):
        with self.assertRaisesRegex(ValueError,"index out of bounds"):
            inspect(*fixture(indices=(0,1,3)))
        self.assertEqual(inspect(*fixture(indices=(0,0,2)))["primitives"][0]["repeated_triangle_indices"],1)

    def test_truncated_view_and_missing_weights(self):
        raw,doc=fixture()
        doc["bufferViews"][0]["byteLength"]-=4
        with self.assertRaisesRegex(ValueError,"exceeds view"):inspect(raw,doc)
        raw,doc=fixture()
        del doc["meshes"][0]["primitives"][0]["attributes"]["WEIGHTS_0"]
        with self.assertRaisesRegex(ValueError,"unmatched"):inspect(raw,doc)

    def test_nonfinite_positions(self):
        raw,doc=fixture()
        data=bytearray(raw);struct.pack_into("<f",data,0,math.nan)
        with self.assertRaisesRegex(ValueError,"non-finite"):inspect(bytes(data),doc)


if __name__=="__main__":
    unittest.main()
