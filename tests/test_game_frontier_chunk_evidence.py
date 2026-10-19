"""Chunk evidence receipts: geometry, lineage, movement, GDD and tamper proofs."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_engine_lab import EngineEra
from skeleton.jeeves.game_frontier_chunks import chunk_mesh
from skeleton.jeeves.game_frontier_chunk_evidence import (
    ChunkEvidenceError, build_mesh_chunk_receipts,
    verify_mesh_chunk_receipts, build_frame_chunk_receipts,
    verify_frame_chunk_receipts,
)
from skeleton.jeeves.game_frontier_frame_coherence import (
    FrameObject, GDDFrameNote, advance_frame, bind_signed_gdd,
)
from tests.test_game_frontier_position_frames import gdd
from tests.test_game_frontier_advanced_scene import scene_params
from skeleton.jeeves.game_frontier import compile_frontier_scene
from skeleton.jeeves.game_frontier_realism import audit_scene_realism
from skeleton.forge.game_frontier_studio import (
    StudioProject,StudioPrefab,StudioPlacement,MapLayer,compile_studio_frame,
)
from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily

def geometry():
    vertices=(Vec3(1,1,0),Vec3(2,1,0),Vec3(1,2,0),
              Vec3(35,1,0),Vec3(36,1,0),Vec3(35,2,0))
    faces=((0,1,2),(3,4,5))
    return vertices,faces

def entity(x=31.95):
    return (
        FrameObject("hero",Vec3(x,0,0),Vec3(6,0,0),"a"*64),
        FrameObject("island",Vec3(65,0,10),Vec3(0,0,0),"b"*64),
    )


class MeshChunkEvidenceTests(unittest.TestCase):
    def test_multi_era_face_coverage_and_dual_receipts(self):
        vertices,faces=geometry()
        for era in EngineEra:
            bundle=build_mesh_chunk_receipts(vertices,faces,era=era.value)
            self.assertEqual(bundle["source_triangle_count"],2)
            self.assertEqual(bundle["chunk_count"],2)
            self.assertTrue(bundle["coverage_exactly_once"])
            self.assertEqual(len(bundle["receipt_digest"]),64)
            self.assertEqual(
                verify_mesh_chunk_receipts(bundle,vertices,faces,era=era.value),
                (True,True))
            all_ids=[i for row in bundle["receipts"] for i in row["source_face_ids"]]
            self.assertEqual(sorted(all_ids),[0,1])
            self.assertTrue(all(row["verifier_a"]["passed"] and
                                row["verifier_b"]["passed"]
                                for row in bundle["receipts"]))

    def test_rejects_corrupted_mesh_chunk_payload_and_source_faces(self):
        vertices,faces=geometry()
        chunks=chunk_mesh(vertices,faces,era=EngineEra.MODERN)
        first=replace(chunks[0],vertices=(Vec3(100,0,0),*chunks[0].vertices[1:]))
        with self.assertRaises(ChunkEvidenceError):
            build_mesh_chunk_receipts(vertices,faces,era=EngineEra.MODERN.value,
                                      chunks=(first,*chunks[1:]))
        evidence=build_mesh_chunk_receipts(vertices,faces,era=EngineEra.MODERN.value)
        with self.assertRaises(ChunkEvidenceError):
            build_mesh_chunk_receipts(vertices,((0,1,2),(0,4,5)),
                                      era=EngineEra.MODERN.value,
                                      chunks=chunks)
        self.assertEqual(verify_mesh_chunk_receipts(
            evidence,vertices,((0,1,2),(0,4,5)),
            era=EngineEra.MODERN.value),(False,False))

    def test_evidence_cannot_be_reused_for_different_source(self):
        vertices,faces=geometry()
        evidence=build_mesh_chunk_receipts(vertices,faces,era=EngineEra.MODERN.value)
        altered=dict(evidence)
        altered["source_geometry_digest"]="0"*64
        self.assertEqual(verify_mesh_chunk_receipts(
            altered,vertices,faces,era=EngineEra.MODERN.value),(False,False))
        changed=tuple([Vec3(1.1,1,0),*vertices[1:]])
        self.assertEqual(verify_mesh_chunk_receipts(
            evidence,changed,faces,era=EngineEra.MODERN.value),(False,False))


class FrameChunkEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.gdd=bind_signed_gdd(gdd())

    def test_frame_zero_receipts_include_source_identity_and_gdd(self):
        frame=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=entity())
        proof=build_frame_chunk_receipts(frame,self.gdd)
        self.assertEqual(proof["object_count"],2)
        self.assertEqual(proof["chunk_count"],2)
        self.assertEqual(proof["source_frame_digest"],frame.receipt_digest)
        self.assertEqual(proof["signed_gdd_digest"],self.gdd.source_digest)
        self.assertEqual(verify_frame_chunk_receipts(proof,frame,self.gdd),
                         (True,True))
        for chunk in proof["receipts"]:
            self.assertTrue(chunk["verifier_a"]["passed"])
            self.assertTrue(chunk["verifier_b"]["passed"])
            self.assertEqual(len(chunk["receipt_digest"]),64)
            self.assertEqual(len(chunk["source_asset_digests"]),chunk["object_count"])

    def test_30_50_60_120fps_migration_proofs_and_gdd_note_references(self):
        for fps in (30,50,60,120):
            previous=advance_frame(frame_index=0,fps=fps,gdd=self.gdd,
                                   objects=entity(31.99))
            prior_proof=build_frame_chunk_receipts(previous,self.gdd)
            next_frame=advance_frame(
                frame_index=1,fps=fps,gdd=self.gdd,previous=previous,
                objects=entity(32.01),
                notes=(GDDFrameNote(1,"design_context",
                                   "Keep weather-aware route continuity."),))
            proof=build_frame_chunk_receipts(
                next_frame,self.gdd,previous=previous,
                previous_evidence=prior_proof)
            self.assertEqual(proof["cross_chunk_migrations"],1)
            self.assertEqual(proof["previous_evidence_digest"],prior_proof["receipt_digest"])
            self.assertEqual(verify_frame_chunk_receipts(
                proof,next_frame,self.gdd,previous=previous,
                previous_evidence=prior_proof),(True,True))
            arrive=[r for r in proof["receipts"] if "hero" in r["arriving_entities"]]
            leave=[r for r in proof["receipts"] if "hero" in r["departing_entities"]]
            leave += [r for r in proof["retired_chunks"]
                      if any(e["entity_id"]=="hero" for e in r["departing_entities"])]
            self.assertEqual(len(arrive),1)
            self.assertEqual(len(leave),1)
            self.assertEqual(proof["retired_chunk_count"],1)
            self.assertEqual(proof["source_note_count"],1)
            self.assertEqual(arrive[0]["gdd_world_law_links"][0]["world_law_index"],1)

    def test_prior_proof_cannot_be_forged_or_linked_to_another_frame(self):
        old=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=entity())
        initial=build_frame_chunk_receipts(old,self.gdd)
        newer=advance_frame(frame_index=1,fps=60,gdd=self.gdd,
                            objects=entity(32.05),previous=old)
        forged=dict(initial)
        forged["source_frame_digest"]="0"*64
        with self.assertRaises(ChunkEvidenceError):
            build_frame_chunk_receipts(newer,self.gdd,previous=old,
                                       previous_evidence=forged)
        forged_row=dict(initial)
        rows=list(initial["receipts"])
        first=dict(rows[0])
        first["source_entities"]=["fake"]
        forged_row["receipts"]=[first,*rows[1:]]
        with self.assertRaises(ChunkEvidenceError):
            build_frame_chunk_receipts(newer,self.gdd,previous=old,
                                       previous_evidence=forged_row)

    def test_reshashed_prior_evidence_with_wrong_source_ids_is_rejected(self):
        from skeleton.jeeves.game_frontier_chunk_evidence import _hash
        old=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=entity())
        previous_proof=build_frame_chunk_receipts(old,self.gdd)
        later=advance_frame(frame_index=1,fps=60,gdd=self.gdd,
                            previous=old,objects=entity(32.05))
        replaced=dict(previous_proof)
        rows=[dict(x) for x in previous_proof["receipts"]]
        rows[0]["source_entities"]=["forged-hero"]
        rows[0]["receipt_digest"]=_hash({
            k:v for k,v in rows[0].items() if k!="receipt_digest"})
        replaced["receipts"]=rows
        replaced["receipt_digest"]=_hash({
            k:v for k,v in replaced.items() if k!="receipt_digest"})
        with self.assertRaises(ChunkEvidenceError):
            build_frame_chunk_receipts(later,self.gdd,previous=old,
                                       previous_evidence=replaced)

    def test_tampering_pseudoproof_boolean_hash_or_gdd_detected(self):
        old=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=entity())
        proof=build_frame_chunk_receipts(old,self.gdd)
        for key,value in (
            ("object_count",42),("signed_gdd_digest","0"*64),
            ("verifier_b",False),("receipt_digest","1"*64),
        ):
            forged=dict(proof)
            forged[key]=value
            a,b=verify_frame_chunk_receipts(forged,old,self.gdd)
            self.assertFalse(a and b)
        changed_gdd=replace(self.gdd,source_digest="f"*64)
        self.assertEqual(verify_frame_chunk_receipts(
            proof,old,changed_gdd),(False,False))

    def test_prior_movement_outside_bound_fails_before_receipting(self):
        old=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=entity())
        forged=FrameObject("hero",Vec3(55,0,0),Vec3(6,0,0),"a"*64)
        with self.assertRaises(Exception):
            advance_frame(frame_index=1,fps=60,gdd=self.gdd,previous=old,
                          objects=(forged,entity()[1]))

    def test_incumbent_actors_unchanged_or_moved_within_chunk(self):
        old=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=entity(2))
        new=advance_frame(frame_index=1,fps=60,gdd=self.gdd,
                          previous=old,objects=entity(2.1))
        result=build_frame_chunk_receipts(new,self.gdd,previous=old)
        changed=[x for c in result["receipts"] for x in c["moved_within_chunk"]]
        self.assertEqual(changed,["hero"])
        self.assertEqual(result["cross_chunk_migrations"],0)

    def test_verified_many_frames_incremental_receipt_chain(self):
        earlier=None
        previous_proof=None
        for index in range(40):
            frame=advance_frame(frame_index=index,fps=60,gdd=self.gdd,
                objects=entity(2+index*.1),previous=earlier,
                notes=(GDDFrameNote(1,"continuity","Maintain the wind law."),)
                if earlier else ())
            proof=build_frame_chunk_receipts(frame,self.gdd,
                previous=earlier,previous_evidence=previous_proof)
            self.assertEqual(verify_frame_chunk_receipts(
                proof,frame,self.gdd,previous=earlier,
                previous_evidence=previous_proof),(True,True))
            earlier,previous_proof=frame,proof


class ChunkIntegrationTests(unittest.TestCase):
    def test_jeeves_scene_exposes_source_evidence_and_mesh_receipts(self):
        base=scene_params()
        base.update(verify_all_era_chunks=True,frame_gdd=bind_signed_gdd(gdd()),
                    frame_index=0,frame_objects=entity(2))
        scene=compile_frontier_scene(**base)
        manifest=scene.manifest
        self.assertEqual(len(manifest["mesh_chunk_evidence"]),len(EngineEra))
        self.assertTrue(manifest["frame_chunk_evidence"]["verifier_a"])
        self.assertTrue(manifest["frame_chunk_evidence"]["verifier_b"])
        self.assertEqual(manifest["frame_chunk_evidence"]["source_frame_digest"],
                         manifest["frame_progress"]["receipt_digest"])
        audit=manifest["realism_audit"]
        self.assertTrue(audit["reference_checks_passed"])
        self.assertIn("frame_chunk_evidence",audit["participating_domains"])
        self.assertIn("mesh_chunk_evidence",audit["participating_domains"])

    def test_secondary_auditor_detects_tampered_mesh_and_frame_receipts(self):
        base=scene_params()
        base.update(verify_all_era_chunks=True,frame_gdd=bind_signed_gdd(gdd()),
                    frame_index=0,frame_objects=entity(2))
        original=compile_frontier_scene(**base).manifest
        tamper=dict(original)
        change=dict(original["frame_chunk_evidence"])
        change["source_frame_digest"]="a"*64
        tamper["frame_chunk_evidence"]=change
        self.assertFalse(audit_scene_realism(tamper).reference_checks_passed)
        tamper=dict(original)
        mesh=list(original["mesh_chunk_evidence"])
        fake=dict(mesh[0])
        fake["coverage_exactly_once"]=False
        mesh[0]=fake
        tamper["mesh_chunk_evidence"]=mesh
        self.assertFalse(audit_scene_realism(tamper).reference_checks_passed)

    def test_studio_exports_digest_linked_chunk_evidence_to_ai_context(self):
        project=StudioProject("frontier","modern",ProjectionMode.DEPTH_29,
            WorldFamily.CELESTIAL,
            (MapLayer("land",1,1,("earth",),(0,)),),
            prefabs=(StudioPrefab("hero","character","modern","a"*64),),
            placements=(StudioPlacement("hero",0,0,1),))
        current=compile_studio_frame(
            project,gdd(),frame_index=0,fps=60,
            entity_velocities={"hero:0":(6,0,0)})
        self.assertEqual(current["chunk_evidence_digest"],
                         current["frame_chunk_evidence"]["receipt_digest"])
        self.assertEqual(current["gdd_ai_context"]["frame_chunk_evidence_digest"],
                         current["chunk_evidence_digest"])
        next_project=replace(project,placements=(StudioPlacement("hero",.1,0,1),))
        nxt=compile_studio_frame(
            next_project,gdd(),frame_index=1,fps=60,
            preceding_frames=(current["record"],),
            previous_chunk_evidence=current["frame_chunk_evidence"],
            entity_velocities={"hero:0":(6,0,0)},
            notes=(GDDFrameNote(1,"quality","Maintain signed sky-island routes."),))
        self.assertEqual(nxt["frame_chunk_evidence"]["previous_evidence_digest"],
                         current["chunk_evidence_digest"])
        self.assertEqual(nxt["gdd_ai_context"]["final_verified_frame"],1)


if __name__=="__main__":
    unittest.main()
