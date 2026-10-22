"""Adversarial 2026 source-bound descriptor, PBR GLB and real export tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import zipfile

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_asset_descriptors import (
    AssetDescriptorError, catalog_bytes, compile_asset_catalog,
    gltf_extras_for_asset, search_asset_catalog, verify_asset_catalog,
)
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_original_audio import compile_original_sound
from skeleton.jeeves.ai.studio_original_mesh import (
    OriginalMeshError, compile_original_mesh, compile_original_mesh_collection,
    verify_original_mesh,
)
from skeleton.jeeves.ai.studio_sprite_forge import compile_authored_sprite
from skeleton.testing.test_jeeves_original_audio import sound_record
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record


def original_mesh(primitive: str = "box") -> dict:
    return {
        "kind": "procedural_mesh",
        "asset_id": "trial-mesh",
        "primitive": primitive,
        "size_mm": [1750, 2100, 850],
        "segments": 24,
        "color_rgba": "#cc8866ff",
        "metallic_per_mille": 250,
        "roughness_per_mille": 600,
    }


def mesh_record(primitive: str = "box") -> dict:
    doc = original_mesh(primitive)
    record = {
        "record_id": "trial-model-source", "facet": "asset_forge",
        "revision": 1, "depends_on": [], "document": doc,
    }
    return reseal(record)


def reseal(record: dict) -> dict:
    record["source_sha256"] = digest([
        record["record_id"], record["facet"], record["revision"],
        record["document"], record["depends_on"],
    ])
    return record


def descriptor_record() -> dict:
    record = {
        "record_id": "trial-description", "facet": "asset_forge",
        "revision": 1, "depends_on": ["trial-model-source"],
        "document": {
            "kind": "asset_descriptor",
            "target_record_id": "trial-model-source",
            "target_asset_id": "trial-mesh",
            "title": "Original temple pedestal",
            "description": "An authored stone pedestal for the temple area.",
            "alt_text": "Low rectangular stone pedestal with four corners.",
            "tags": ["temple", "pedestal", "original"],
            "roles": ["environment", "prop"],
            "locale": "en",
            "rights_status": "self_authored_asserted",
            "attribution": "",
        },
    }
    return reseal(record)


def _parse_glb(glb: bytes) -> tuple[dict, bytes]:
    magic, version, size = struct.unpack_from("<4sII", glb, 0)
    assert magic == b"glTF" and version == 2 and size == len(glb)
    size_json, kind = struct.unpack_from("<I4s", glb, 12)
    assert kind == b"JSON"
    position = 20 + size_json
    size_bin, kind = struct.unpack_from("<I4s", glb, position)
    assert kind == b"BIN\x00"
    return json.loads(glb[20:position]), glb[position + 8:position + 8 + size_bin]


class MeshCompiler2026Tests(unittest.TestCase):
    def test_all_four_authored_primitives_emit_real_glb(self):
        shapes = {"box", "plane", "cylinder", "uv_sphere"}
        for shape in sorted(shapes):
            with self.subTest(shape=shape):
                record = mesh_record(shape)
                compiled = compile_original_mesh(record)
                proof = compiled["metadata"]
                glb = compiled["glb"]
                content, binary = _parse_glb(glb)
                self.assertEqual(content["asset"]["version"], "2.0")
                self.assertEqual(content["buffers"][0]["byteLength"], len(binary))
                self.assertEqual(proof["primitive"], shape)
                self.assertGreater(proof["vertices"], 0)
                self.assertGreater(proof["triangles"], 0)
                self.assertEqual(
                    content["accessors"][0]["count"], proof["vertices"],
                )
                self.assertEqual(
                    content["accessors"][3]["count"], proof["triangles"] * 3,
                )
                self.assertEqual(
                    proof["glb_sha256"], sha256(glb).hexdigest(),
                )
                self.assertTrue(verify_original_mesh(
                    record, glb, proof,
                )["glb_buffer_and_index_geometry_replayed"])
                self.assertFalse(proof["godot_native_import_verified"])

    def test_pbr_factor_material_and_uv_indices_are_real(self):
        content, binary = _parse_glb(compile_original_mesh(
            mesh_record("box"),
        )["glb"])
        mat = content["materials"][0]["pbrMetallicRoughness"]
        self.assertEqual(mat["metallicFactor"], 0.25)
        self.assertEqual(mat["roughnessFactor"], 0.6)
        self.assertEqual(len(mat["baseColorFactor"]), 4)
        self.assertEqual(content["meshes"][0]["primitives"][0]["mode"], 4)
        for accessor in content["accessors"]:
            self.assertIn(accessor["bufferView"], range(4))
        indices = content["accessors"][3]["count"]
        offset = content["bufferViews"][3]["byteOffset"]
        self.assertLess(max(
            struct.unpack_from("<" + "H" * indices, binary, offset),
        ), content["accessors"][0]["count"])

    def test_anisotropic_sphere_normals_are_unit_length(self):
        content, binary = _parse_glb(compile_original_mesh(
            mesh_record("uv_sphere"),
        )["glb"])
        view = content["bufferViews"][1]
        for i in range(content["accessors"][1]["count"]):
            nx, ny, nz = struct.unpack_from(
                "<fff", binary, view["byteOffset"] + i * 12,
            )
            self.assertAlmostEqual(nx * nx + ny * ny + nz * nz, 1.0, places=5)

    def test_ellipsoid_and_cylinder_have_nonuniform_normals(self):
        for shape in ("uv_sphere", "cylinder"):
            result = compile_original_mesh(mesh_record(shape))
            content, binary = _parse_glb(result["glb"])
            view = content["bufferViews"][1]
            vectors = [
                struct.unpack_from("<fff", binary, view["byteOffset"] + i * 12)
                for i in range(content["accessors"][1]["count"])
            ]
            self.assertTrue(any(
                abs(nx) > .01 and abs(nz) > .01 for nx, ny, nz in vectors
            ))

    def test_mesh_reproduction_is_bit_for_bit_deterministic(self):
        record = mesh_record("cylinder")
        self.assertEqual(compile_original_mesh(record), compile_original_mesh(record))

    def test_source_measurement_change_invalidates_binary(self):
        a = mesh_record()
        b = deepcopy(a)
        b["document"]["size_mm"][0] += 1
        reseal(b)
        self.assertNotEqual(
            compile_original_mesh(a)["metadata"]["glb_sha256"],
            compile_original_mesh(b)["metadata"]["glb_sha256"],
        )

    def test_altered_glb_or_resealed_gibberish_refused(self):
        record = mesh_record()
        original = compile_original_mesh(record)
        damaged = bytearray(original["glb"])
        damaged[-12] ^= 16
        with self.assertRaises(OriginalMeshError):
            verify_original_mesh(record, bytes(damaged), original["metadata"])

    def test_fake_engine_execution_claim_refused(self):
        record = mesh_record()
        emitted = compile_original_mesh(record)
        altered = deepcopy(emitted["metadata"])
        altered["godot_native_import_verified"] = True
        altered["receipt_sha256"] = digest({
            k: v for k, v in altered.items() if k != "receipt_sha256"
        })
        with self.assertRaises(OriginalMeshError):
            verify_original_mesh(record, emitted["glb"], altered)

    def test_illegal_geometry_and_color_do_not_compile(self):
        for key, value in (
            ("segments", 1), ("size_mm", [0, 2, 3]),
            ("size_mm", [True, 2, 3]),
            ("color_rgba", "#qqqqqqff"),
            ("metallic_per_mille", 1001),
            ("primitive", "unsafe_mesh"),
        ):
            with self.subTest(field=key, value=value):
                record = mesh_record()
                record["document"][key] = value
                with self.assertRaises(OriginalMeshError):
                    compile_original_mesh(reseal(record))

    def test_primitive_inventory_enforces_unique_asset_ids(self):
        one = mesh_record()
        two = deepcopy(one)
        two["record_id"] = "second-mesh"
        reseal(two)
        with self.assertRaises(OriginalMeshError):
            compile_original_mesh_collection({
                "first": one, "second": two,
            })


class DescriptorCompiler2026Tests(unittest.TestCase):
    def setUp(self):
        self.sprite = compile_authored_sprite(original_record())
        self.sound = compile_original_sound(sound_record())
        self.record = mesh_record()
        self.mesh = compile_original_mesh(self.record)

    def catalog(self, records=None):
        return compile_asset_catalog(
            project_id="original-game", source_head_sha256="a" * 64,
            records=records or {}, sprites=[self.sprite],
            sounds=[self.sound], meshes=[self.mesh],
        )

    def test_generate_three_distinct_descriptors_with_real_structural_data(self):
        catalog = self.catalog()
        self.assertEqual(catalog["descriptor_count"], 3)
        kinds = {d["kind"] for d in catalog["descriptors"]}
        self.assertEqual(kinds, {
            "pixel_sprite", "procedural_sound", "procedural_mesh",
        })
        metrics = {d["kind"]: d["metrics"] for d in catalog["descriptors"]}
        self.assertEqual(metrics["pixel_sprite"]["frame_count"], 2)
        self.assertGreater(metrics["procedural_sound"]["sample_count"], 100)
        self.assertEqual(metrics["procedural_mesh"]["material_model"],
                         "glTF_metallic_roughness")
        self.assertFalse(catalog["rights_clearance_certified"])
        self.assertFalse(catalog["narrative_meaning_inferred_from_pixels"])

    def test_authored_overlay_adds_explicit_semantics_and_rights_assertion(self):
        record = descriptor_record()
        catalog = self.catalog({record["record_id"]: record})
        mesh = next(d for d in catalog["descriptors"]
                    if d["kind"] == "procedural_mesh")
        self.assertEqual(mesh["title"], "Original temple pedestal")
        self.assertIn("pedestal", mesh["tags"])
        self.assertEqual(mesh["rights"]["status"], "self_authored_asserted")
        self.assertFalse(mesh["rights"]["legally_cleared_by_compiler"])
        self.assertEqual(mesh["semantic_evidence"]["status"],
                         "authored_reviewed_source")
        result = search_asset_catalog(catalog, "temple pedestal", limit=2)
        self.assertEqual(result["results"][0]["asset_id"], "trial-mesh")
        self.assertEqual(result["result_receipts"][0],
                         mesh["receipt_sha256"])

    def test_replay_proves_index_bytes_and_all_three_modalities(self):
        catalog = self.catalog({"trial-description": descriptor_record()})
        checked = verify_asset_catalog(
            catalog_bytes(catalog),
            project_id="original-game", source_head_sha256="a" * 64,
            sprites=[self.sprite], sounds=[self.sound], meshes=[self.mesh],
        )
        self.assertEqual(checked["descriptor_count"], 3)
        self.assertTrue(checked["pixels_samples_descriptors_and_index_replayed"])

    def test_modified_index_rehashed_metadata_is_rejected_by_reconstruction(self):
        catalog = self.catalog()
        changed = deepcopy(catalog)
        changed["inverted_index"]["trial"] = ["pixel_sprite:hero-idle"]
        changed["receipt_sha256"] = sha256(
            json.dumps({k: v for k, v in changed.items()
                        if k != "receipt_sha256"},
                       sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest()
        with self.assertRaises(AssetDescriptorError):
            verify_asset_catalog(
                catalog_bytes(changed), project_id="original-game",
                source_head_sha256="a" * 64,
                sprites=[self.sprite], sounds=[self.sound], meshes=[self.mesh],
            )

    def test_glTF_extras_preserve_verified_source_identity(self):
        asset = next(d for d in self.catalog()["descriptors"]
                     if d["kind"] == "procedural_mesh")
        extras = gltf_extras_for_asset(asset)["skeletonJeevesAsset"]
        self.assertEqual(extras["assetId"], "trial-mesh")
        self.assertEqual(extras["descriptorReceiptSha256"],
                         asset["receipt_sha256"])
        self.assertEqual(extras["contentSha256"], self.mesh["metadata"]["glb_sha256"])

    def test_forged_gltf_descriptor_fails(self):
        asset = deepcopy(self.catalog()["descriptors"][0])
        asset["title"] = "Impossible"
        with self.assertRaises(AssetDescriptorError):
            gltf_extras_for_asset(asset)

    def test_cross_project_replay_is_denied(self):
        catalog = catalog_bytes(self.catalog())
        with self.assertRaises(AssetDescriptorError):
            verify_asset_catalog(catalog, project_id="foreign",
                                 source_head_sha256="a" * 64,
                                 sprites=[self.sprite], sounds=[self.sound],
                                 meshes=[self.mesh])

    def test_rights_assertions_reject_unattributed_external_sources(self):
        overlay = descriptor_record()
        overlay["document"]["rights_status"] = "third_party_permission_asserted"
        with self.assertRaises(AssetDescriptorError):
            self.catalog({"trial-description": reseal(overlay)})

    def test_wrong_target_does_not_invent_descriptor(self):
        overlay = descriptor_record()
        overlay["document"]["target_asset_id"] = "foreign-art"
        with self.assertRaises(AssetDescriptorError):
            self.catalog({"trial-description": reseal(overlay)})

    def test_ambiguous_reviewer_overlays_are_denied(self):
        a = descriptor_record()
        b = deepcopy(a)
        b["record_id"] = "another-description"
        with self.assertRaises(AssetDescriptorError):
            self.catalog({a["record_id"]: a, b["record_id"]: reseal(b)})

    def test_search_filters_by_modality_without_hallucinating_art(self):
        catalog = self.catalog()
        result = search_asset_catalog(catalog, "original", kind="procedural_mesh")
        self.assertTrue(result["results"])
        self.assertEqual({row["kind"] for row in result["results"]},
                         {"procedural_mesh"})
        self.assertFalse(result["neural_retrieval_performed"])


class SourceOwnedDescriptorExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.export_root = self.root / "exports"
        self.export_root.mkdir()
        self.store = CreatorProjectSourceStore(
            self.root / "store.sqlite", project_id="original-game",
            export_root=self.export_root,
        )
        self.addCleanup(self.store.close)

    def create(self, record: dict):
        return self.store.create(build_creator_command(
            "create", project_id="original-game",
            payload={"intent": {
                "record_id": record["record_id"], "facet": record["facet"],
                "document": record["document"],
                "depends_on": record["depends_on"],
            }},
        ))

    def test_source_store_assembles_semantics_from_real_mesh(self):
        self.create(mesh_record())
        self.create(descriptor_record())
        result = self.store.search_original_assets("temple", kind="procedural_mesh")
        self.assertEqual(result["asset_count"], 1)
        self.assertEqual(result["results"][0]["title"], "Original temple pedestal")
        self.assertEqual(result["source_head_sha256"], self.store.head_identity())
        self.assertEqual(len(result["retrieval_receipt_sha256"]), 64)

    def test_mesh_create_denies_invalid_source_before_sqlite_mutation(self):
        invalid = mesh_record()
        invalid["document"]["segments"] = 1000
        with self.assertRaises(OriginalMeshError):
            self.create(invalid)
        self.assertEqual(self.store.snapshot()["source_count"], 0)

    def test_descriptor_create_denies_uncreated_dependency(self):
        with self.assertRaises(Exception):
            self.create(descriptor_record())
        self.assertEqual(self.store.snapshot()["source_count"], 0)

    def test_standalone_sprite_package_contains_verified_catalog(self):
        self.create(original_record())
        exported = self.store.export(build_creator_command(
            "export", project_id="original-game",
            payload={"format": "sprite-atlas-zip", "artifact_name": "sprite"},
        ))
        with zipfile.ZipFile(self.export_root / exported["artifact_name"]) as z:
            data = z.read("assets/catalog.json")
        catalog = json.loads(data)
        self.assertEqual(catalog["descriptor_count"], 1)
        self.assertTrue(exported["disk_verification"][
            "all_rgba_hitbox_and_resource_bytes_replayed"])
        self.assertEqual(exported["disk_verification"][
            "descriptors_independently_replayed"], 1)


if __name__ == "__main__":
    unittest.main()
