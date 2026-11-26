"""Run original-byte qualification as an offline evidence conveyor.

The input must be a verified delivery. A private exact snapshot is used for
every structural audit. Does not execute Unreal, publish a release, qualify a
GPU, infer artistic quality, or mutate crawler/application state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import audit_emerald_animation as animation
import audit_emerald_skin as skin
import audit_emerald_materials as materials
from dragon_atelier_admit import inspect_glb, verify_peak_receipt
from emerald_asset_preflight import PIN
from prepare_emerald_delivery import verify as verify_delivery
from recover_emerald_assets import copy_exact
from verify_emerald_native_stage import verify as verify_stage

MODEL = "emerald_continuum.glb"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical_sha(value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                     sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def qualify_model(model, pin):
    with tempfile.TemporaryDirectory(prefix="emerald-model-audit-") as directory:
        private = Path(directory) / MODEL
        copy_exact(model, private, pin["modelBytes"], pin["modelSha256"])
        structure = verify_peak_receipt(inspect_glb(private, pin["modelSha256"]), pin)
        reports = {
            "animation": animation.audit_pinned(private, pin),
            "mesh_skin": skin.audit_pinned(private, pin),
            "materials": materials.audit_pinned(private, pin),
        }
    for name, result in reports.items():
        require(result["model_sha256"] == pin["modelSha256"] and
                result["model_bytes"] == pin["modelBytes"], name + " identity mismatch")
    clips = [row["name"] for row in reports["animation"]["clips"]]
    require(len(clips) == 380 and len(set(clips)) == 380 and
            set(clips) == set(structure["clips"]), "clip catalogue mismatch")
    require(structure["joints"] == 108 and
            max(reports["mesh_skin"]["skin_palette_sizes"]) == 108, "joint census mismatch")
    require(reports["mesh_skin"]["total_vertices_by_primitive"] > 0 and
            reports["mesh_skin"]["total_index_or_vertex_count"] > 0, "geometry census empty")
    require(len(reports["materials"]["images"]) == 4 and
            reports["materials"]["unique_image_hashes"] == 4, "original image census mismatch")
    return {
        "structure": structure, **reports,
        "report_digests": {name: canonical_sha(result) for name, result in {"structure": structure, **reports}.items()},
    }


def qualify(delivery, pin, *, staged=None):
    delivery = Path(delivery)
    delivery_receipt = verify_delivery(delivery, pin)
    model = qualify_model(delivery / MODEL, pin["native"])
    native = None
    if staged is not None:
        native = verify_stage(Path(staged), delivery / "emerald-atelier-fold-source.zip", pin["native"])
        require(native["model_sha256"] == pin["native"]["modelSha256"] and
                native["source_sha256"] == pin["native"]["sourceSha256"] and
                native["native_staging_qualified"] is True, "native staging evidence mismatch")
    return {
        "schema": "skeleton.emerald.original-byte-qualification.v1",
        "asset_set": pin["assetSet"],
        "delivery": delivery_receipt,
        "model_sha256": pin["native"]["modelSha256"],
        "model_bytes": pin["native"]["modelBytes"],
        "source_file_structure_qualified": True,
        "sampled_animation_qualified": True,
        "mesh_skin_bytes_qualified": True,
        "embedded_image_bytes_qualified": True,
        "native_staging_qualified": native is not None,
        "native_staging": native,
        "model_audits": model,
        "continuous_collision_verified": False,
        "physical_deformation_verified": False,
        "fully_decoded_textures_verified": False,
        "actual_renderer_verified": False,
        "engine_compiled": False,
        "physical_rtx_verified": False,
        "artist_approved": False,
        "release_qualified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--staged", type=Path)
    args = parser.parse_args()
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    print(json.dumps(qualify(args.delivery, pin, staged=args.staged),
                     ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
