"""Seven production quality gate regression contracts."""
import copy
import unittest

from skeleton.game.production_quality import (
    QualityGateError, audit_asset_integrity, audit_build_replay,
    audit_frame_budget, audit_release_candidate, audit_rights_provenance,
    audit_story_canon, audit_world_graph,
)


def candidate():
    digest = "a" * 64
    return {
        "world": {"nodes": [{"id": "camp"}, {"id": "exit"}],
                  "edges": [{"from": "camp", "to": "exit"}],
                  "start": "camp", "victory": "exit"},
        "story": {"cast": [{"id": "guide"}],
                  "scenes": [{"id": "intro", "speakers": ["guide"]},
                             {"id": "ending", "prerequisites": ["intro"]}]},
        "assets": [{"path": "meshes/guide.obj", "sha256": digest, "bytes": 10}],
        "builds": [{"source_sha256": digest, "files": {"scene": digest}},
                   {"source_sha256": digest, "files": {"scene": digest}}],
        "frames": [{"ms": 10.0, "draw_calls": 10}] * 100,
        "sources": [{"id": "mesh", "origin": "original", "reviewed": True,
                     "evidence_ref": "review/mesh"}],
    }


class ProductionQualityTests(unittest.TestCase):
    def test_clean_candidate_is_only_a_candidate(self):
        report = audit_release_candidate(candidate())
        self.assertTrue(report["candidate_passed"])
        self.assertFalse(report["release_certified"])
        self.assertEqual(6, len(report["gates"]))
        self.assertEqual(64, len(report["evidence_digest"]))

    def test_world_detects_unreachable_and_orphans(self):
        world = candidate()["world"]
        world["nodes"].append({"id": "orphan"})
        world["edges"].append({"from": "outside", "to": "exit"})
        codes = {f.code for f in audit_world_graph(world).findings}
        self.assertIn("orphan_edge", codes)
        self.assertIn("unreachable_node", codes)

    def test_canon_detects_forward_reference_and_unknown_actor(self):
        story = candidate()["story"]
        story["scenes"][0]["prerequisites"] = ["ending"]
        story["scenes"][0]["speakers"] = ["forged"]
        codes = {f.code for f in audit_story_canon(story).findings}
        self.assertEqual({"unmet_prerequisite", "unknown_speaker"}, codes)

    def test_assets_reject_parent_traversal_and_digest_forgery(self):
        assets = candidate()["assets"]
        assets[0]["path"] = "../outside"
        assets[0]["sha256"] = "not-sha"
        codes = {f.code for f in audit_asset_integrity(assets).findings}
        self.assertEqual({"unsafe_path", "invalid_digest"}, codes)

    def test_rebuild_detects_different_artifact(self):
        builds = candidate()["builds"]
        builds[1]["files"]["scene"] = "b" * 64
        self.assertFalse(audit_build_replay(builds).passed)

    def test_frame_p95_p99_and_draw_pressure(self):
        frames = [{"ms": 4., "draw_calls": 1} for _ in range(90)]
        frames.extend({"ms": 40., "draw_calls": 1400} for _ in range(10))
        codes = {f.code for f in audit_frame_budget(frames).findings}
        self.assertEqual({"p95_frame_budget", "p99_frame_budget", "draw_budget"}, codes)

    def test_rights_fail_closed_without_review(self):
        sources = candidate()["sources"]
        sources[0]["reviewed"] = False
        self.assertFalse(audit_rights_provenance(sources).passed)
        self.assertFalse(audit_rights_provenance([]).passed)

    def test_combined_rejects_every_mutated_plane(self):
        mutations = (
            lambda x: x["world"].update(victory="unknown"),
            lambda x: x["story"]["scenes"][0].update(speakers=["unknown"]),
            lambda x: x["assets"][0].update(sha256="0"),
            lambda x: x["builds"][0].update(source_sha256="f" * 64),
            lambda x: x["frames"][0].update(draw_calls=100000),
            lambda x: x["sources"][0].update(reviewed=False),
        )
        for modify in mutations:
            sample = copy.deepcopy(candidate())
            modify(sample)
            with self.subTest(modify=modify):
                self.assertFalse(audit_release_candidate(sample)["candidate_passed"])

    def test_bad_numeric_or_missing_evidence_is_rejected(self):
        with self.assertRaises(QualityGateError):
            audit_frame_budget([{"ms": float("nan"), "draw_calls": 1}])
        with self.assertRaises(QualityGateError):
            audit_release_candidate({"world": {}})


if __name__ == "__main__":
    unittest.main()
