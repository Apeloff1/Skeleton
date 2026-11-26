"""Independent Scholar wingfold candidate verification against immutable V4 bytes."""
from __future__ import annotations
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct
import numpy as np

from emerald_v5_scholar_wingfold import (
    SOURCE_SHA, SOURCE_BYTES, OUTPUT_SHA, OUTPUT_BYTES, DONOR_SHA, ANGLE,
    TARGET_SKIN_JOINTS, corrected_quaternions, parse_model, rotation_accessor,
    hash_file, require,
)

def verify(source, corrected):
    src = Path(source)
    dest = Path(corrected)
    require(dest.is_file() and not dest.is_symlink() and
            dest.stat().st_size == OUTPUT_BYTES and
            hash_file(dest) == OUTPUT_SHA, "corrected candidate identity mismatch")
    source_file, raw, doc, source_offset, source_length = parse_model(src)
    output_file = dest.open("rb")
    output = mmap.mmap(output_file.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        magic, version, length, json_len, js_tag = struct.unpack_from("<4sIIII", output)
        require((magic, version, length, js_tag) ==
                (b"glTF", 2, len(output), 0x4e4f534a), "candidate GLB header mismatch")
        length_bin, bin_tag = struct.unpack_from("<II", output, 20+json_len)
        output_offset = 28+json_len
        require(bin_tag == 0x004e4942 and length_bin+output_offset == len(output),
                "candidate binary chunk mismatch")
        after = json.loads(output[20:20+json_len])
        original_keys = set(doc) - {"asset", "extras", "animations",
                                     "accessors", "bufferViews", "buffers"}
        require({k: after[k] for k in original_keys} ==
                {k: doc[k] for k in original_keys}, "model or material declaration modified")
        require(after["asset"]["version"] == doc["asset"]["version"] and
                after["extras"]["stage"] == doc["extras"]["stage"] and
                after["extras"]["donorSha256"] == DONOR_SHA,
                "source lineage mismatch")
        correction = after["extras"]["wingFoldCorrection"]
        require(correction["source_model_sha256"] == SOURCE_SHA and
                correction["source_donor_sha256"] == DONOR_SHA and
                correction["local_z_radians"] == ANGLE and
                correction["joint_ids"] == list(TARGET_SKIN_JOINTS) and
                correction["equipment_enabled"] is False and
                correction["continuous_clearance_verified"] is False and
                correction["artist_approved"] is False and
                correction["physical_rtx_verified"] is False and
                correction["release_qualified"] is False,
                "unapproved correction metadata or qualification assertion")
        require(len(after["accessors"]) == len(doc["accessors"])+760 and
                len(after["bufferViews"]) == len(doc["bufferViews"])+760,
                "wrong append-only accessor counts")
        require(after["accessors"][:len(doc["accessors"])] == doc["accessors"] and
                after["bufferViews"][:len(doc["bufferViews"])] == doc["bufferViews"],
                "original accessor or view modified")
        require(after["animations"][-1] == doc["animations"][-1],
                "growth clip no longer bit-identical")
        require(len(after["animations"]) == len(doc["animations"]) == 381,
                "original 381-clip catalogue lost")
        require(output[output_offset:output_offset+source_length] ==
                raw[source_offset:source_offset+source_length],
                "original geometry, texture or animation binary prefix changed")
        original_ids = {doc["skins"][0]["joints"][x] for x in TARGET_SKIN_JOINTS}
        changed = 0
        max_abs_error = 0.
        unchanged = 0
        for left, right in zip(doc["animations"][:380], after["animations"][:380]):
            require(left["name"] == right["name"] and
                    len(left["channels"]) == len(right["channels"]) and
                    len(left["samplers"]) == len(right["samplers"]),
                    "clip name or channel layout differs")
            modified = set()
            for lc, rc in zip(left["channels"], right["channels"]):
                require(lc == rc, "original animation target changed")
                node = lc["target"]["node"]
                prop = lc["target"]["path"]
                left_sampler = left["samplers"][lc["sampler"]]
                right_sampler = right["samplers"][rc["sampler"]]
                require(left_sampler["input"] == right_sampler["input"] and
                        left_sampler["interpolation"] == right_sampler["interpolation"],
                        "timebase or interpolation modified")
                if node in original_ids and prop == "rotation":
                    require(node not in modified, "duplicate terminal rotation")
                    modified.add(node)
                    old = rotation_accessor(raw, doc, source_offset,
                                            left_sampler["output"]).copy()
                    actual = rotation_accessor(output, after, output_offset,
                                               right_sampler["output"]).copy()
                    expected = corrected_quaternions(old)
                    error = float(np.max(np.abs(expected-actual)))
                    require(error <= 4e-7, "quaternion correction mismatch")
                    max_abs_error = max(error, max_abs_error)
                    changed += 1
                else:
                    require(left_sampler == right_sampler,
                            "unreviewed animation target modified")
                    unchanged += 1
            require(modified == original_ids, "missing one terminal joint")
        require(changed == 760 and
                after["buffers"][0]["byteLength"] >=
                doc["buffers"][0]["byteLength"], "incomplete corrected streams")
        return {
            "schema": "skeleton.emerald.scholar-wingfold-independent.v1",
            "source_sha256": SOURCE_SHA,
            "candidate_sha256": OUTPUT_SHA,
            "candidate_bytes": OUTPUT_BYTES,
            "donor_sha256": DONOR_SHA,
            "corrected_rotation_tracks": changed,
            "unchanged_other_tracks": unchanged,
            "max_corrected_quaternion_error": max_abs_error,
            "growth_clip_document_exact": True,
            "original_embedded_binary_prefix_exact": True,
            "original_geometry_and_materials_exact": True,
            "equipment_enabled": False,
            "continuous_clearance_qualified": False,
            "artist_approved": False,
            "unreal_compiled": False,
            "physical_rtx_verified": False,
            "release_qualified": False,
        }
    finally:
        output.close()
        output_file.close()
        raw.close()
        source_file.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    args = p.parse_args()
    require(args.receipt.parent.is_dir() and not args.receipt.exists(),
            "must create new receipt")
    result = verify(args.source, args.candidate)
    with args.receipt.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
