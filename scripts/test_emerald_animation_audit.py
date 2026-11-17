from copy import deepcopy
import io
import math
import struct
import unittest

from audit_emerald_animation import audit_tracks


def sample(times=(0.0, 1.0), rotations=(0, 0, 0, 1, 0, 0, 0, 1)):
    raw = struct.pack("<" + "f" * (len(times) + len(rotations)), *times, *rotations)
    doc = {"nodes": [{}], "bufferViews": [{"buffer": 0, "byteLength": 4*len(times)},
             {"buffer": 0, "byteOffset": 4*len(times), "byteLength": 4*len(rotations)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(times), "type": "SCALAR"},
                         {"bufferView": 1, "componentType": 5126, "count": len(rotations)//4, "type": "VEC4"}],
           "animations": [{"name": "fixture", "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}],
                           "samplers": [{"input": 0, "output": 1}]}]}
    return raw, doc


def inspect(raw, doc):
    return audit_tracks(io.BytesIO(raw), doc, 0, len(raw))


class AuditTests(unittest.TestCase):
    def test_valid_sample_and_shared_accessors(self):
        raw, doc = sample()
        second = deepcopy(doc["animations"][0])
        second["name"] = "second"
        doc["animations"].append(second)
        result = inspect(raw, doc)
        self.assertEqual(result["tracks"], 2)
        self.assertEqual(result["float_components_examined"], 10)
        self.assertEqual(result["clips"][0]["channel_keys"], 2)

    def test_invalid_timestamps(self):
        for times in ((0, 0), (1, 0), (-1, 1), (0, math.inf)):
            with self.subTest(times=times), self.assertRaisesRegex(ValueError, "timestamps"):
                inspect(*sample(times))

    def test_nonfinite_and_bad_quaternion(self):
        with self.assertRaisesRegex(ValueError, "non-finite"):
            inspect(*sample(rotations=(0, 0, 0, 1, 0, 0, math.nan, 1)))
        with self.assertRaisesRegex(ValueError, "quaternion"):
            inspect(*sample(rotations=(0, 0, 0, 1, 0, 0, 0, 2)))

    def test_duplicate_target_and_out_of_bounds_view(self):
        raw, doc = sample()
        doc["animations"][0]["channels"].append(deepcopy(doc["animations"][0]["channels"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate node/path"):
            inspect(raw, doc)
        raw, doc = sample()
        doc["bufferViews"][1]["byteLength"] -= 4
        with self.assertRaisesRegex(ValueError, "exceeds view"):
            inspect(raw, doc)

    def test_cubic_rotation_tangents_not_required_to_be_unit(self):
        raw, doc = sample(rotations=(0,0,0,0, 0,0,0,1, 0,0,0,0,
                                     0,0,0,0, 0,0,0,1, 0,0,0,0))
        doc["animations"][0]["samplers"][0]["interpolation"] = "CUBICSPLINE"
        self.assertEqual(inspect(raw, doc)["clips"][0]["max_rotation_norm_error"], 0)

    def test_interleaved_animation_data(self):
        raw, doc = sample()
        interleaved = struct.pack("<ffff",0,99,1,99) + raw[8:]
        doc["bufferViews"][0].update(byteLength=16,byteStride=8)
        doc["bufferViews"][1]["byteOffset"] = 16
        self.assertEqual(inspect(interleaved,doc)["clips"][0]["end_seconds"],1)


if __name__ == "__main__":
    unittest.main()
