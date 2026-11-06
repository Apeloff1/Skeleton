"""Real Dragon Atlas backend adapter qualification without real external I/O.

Calls DragonCrawlerApplication.campaign_atlas, not the pure composition
function. Only Mongo collection access is replaced by a deterministic owned
row provider. The real policy-first Atlas, source hashes, metadata envelope,
second-read race fencing and reviewed-knowledge holds remain in play.

This is an application bridge test, not device/network/Mongo E2E evidence.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from types import MethodType
import sys
from pathlib import Path
import unittest

from core import dragon_crawler as core_crawler

_ROOT = Path(__file__).resolve().parents[2]
for parent in (_ROOT / "tests", _ROOT):
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))

from test_ai_webcrawler_dragon_atlas import (  # noqa: E402
    DragonAtlasRegression, research_text,
)


class AtlasOwnerBridgeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.fixtures = DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.fixtures.setUp()
        self.snapshot = self.fixtures.with_sources(
            ("https://example.com/archive", research_text("backend"))
        )
        self.owner = {
            "tenant_id": self.fixtures.scope.tenant_id,
            "owner_id": self.fixtures.scope.owner_id,
        }
        self.session = "owned-atlas-session"
        self.original = {
            "version": 1,
            "snapshot": self.snapshot,
            "source_use_policies": {},
            "policy_revision": 1,
            "_source_state": "current",
        }
        self.next_row = None
        self.owned_reads = 0
        self.application = object.__new__(core_crawler.DragonCrawlerApplication)

        async def owned(scope, identifier):
            if scope != self.owner or identifier != self.session:
                raise core_crawler.CrawlerError(
                    "crawler_not_found", "No owned session exists.", 404,
                )
            self.owned_reads += 1
            return deepcopy(
                self.original
                if self.owned_reads == 1 or self.next_row is None
                else self.next_row
            )

        def authority(_app, row):
            return row["snapshot"], ()

        def mandate(_scope, _row):
            return self.fixtures.mandate

        def freshness(_app, row, source):
            del source
            return {
                "state": row.get("_source_state", "current"),
                "valid_until": datetime.fromtimestamp(
                    self.fixtures.now + 1800, timezone.utc,
                ).isoformat(),
            }

        def source_policy(_app, row, source):
            del source
            return {
                "version": row["policy_revision"],
                "enabled": row.get("_source_state", "current") == "current",
                "max_age_seconds": 3600,
                "changed_at": None,
            }

        self.application._owned = owned
        self.application._campaign_authority = MethodType(
            authority, self.application,
        )
        self.application._campaign_mandate = mandate
        self.application._capture_freshness = MethodType(
            freshness, self.application,
        )
        self.application._capture_policy = MethodType(
            source_policy, self.application,
        )

    def goals(self):
        goal = asdict(self.fixtures.objective())
        goal["required_terms"] = list(goal["required_terms"])
        goal["blocked_terms"] = list(goal["blocked_terms"])
        return (goal,)

    async def atlas(self, **kwargs):
        return await self.application.campaign_atlas(
            self.owner, self.session, self.goals(), **kwargs,
        )

    async def test_actual_backend_atlas_exposes_all_23_pinned_stages(self):
        result = await self.atlas()
        self.assertTrue(result["ok"])
        report = result["report"]
        self.assertEqual(self.owned_reads, 2)
        self.assertEqual(report["schema_version"],
                         "skeleton.dragon.campaign_atlas_dashboard.v1")
        self.assertEqual(len(report["stages"]), 25)
        self.assertEqual(report["source_similarity"]["retrieval_digest"], report["retrieval"]["digest"])
        self.assertEqual(report["source_similarity"]["policy_digest"], report["source_policy"]["digest"])
        self.assertFalse(report["source_similarity"]["network_used"])
        self.assertFalse(report["source_similarity"]["lineage_verified"])
        self.assertEqual(report["stages"][-1]["name"], "selected_evidence_host_ablation_and_reuse")
        self.assertEqual(report["retrieval_robustness"]["retrieval_digest"], report["retrieval"]["digest"])
        self.assertTrue(report["retrieval_robustness"]["source_bodies_excluded"])
        self.assertFalse(report["retrieval_robustness"]["verified_independence"])
        self.assertFalse(report["retrieval_robustness"]["network_or_reranking_executed"])
        self.assertEqual(report["retrieval_robustness"]["distinct_content_families"], 1)
        self.assertEqual(report["retrieval_robustness"]["cross_host_exact_copy_groups"], 0)
        self.assertEqual(report["session_id"], self.session)
        self.assertEqual(report["retrieval"]["mode"], "fusion")
        self.assertEqual(report["source_policy"]["included_source_count"], 1)
        self.assertGreater(report["retrieval"]["retained_hits"], 0)
        self.assertEqual(report["citation_manifest"]["body_redacted"], True)
        self.assertEqual(report["jeeves_handoff"]["body_excluded"], True)
        self.assertFalse(report["publication_granted"])
        self.assertFalse(report["training_permission"])
        self.assertFalse(report["network_executed"])
        self.assertFalse(report["dispatch_recovery"]["mongo_commit_confirmed"])
        self.assertEqual(len(report["dashboard_digest"]), 64)
        self.assertNotIn("Archive capture methodology", repr(report))

    async def test_actual_backend_bm25_routes_to_second_ranker(self):
        response = await self.atlas(retrieval_mode="lexical_bm25")
        report = response["report"]
        self.assertEqual(report["retrieval"]["mode"], "lexical_bm25")
        self.assertIsNotNone(report["lexical_ranking"])
        self.assertGreater(report["lexical_ranking"]["scored_query_receipts"], 0)
        self.assertFalse(report["lexical_ranking"]["ai_embedding_used"])
        self.assertFalse(report["jeeves_handoff"]["network_called"])
        self.assertEqual(self.owned_reads, 2)

    async def test_backend_generates_bounded_unpersisted_review_plan(self):
        effort = (
            {"task_type": "passage_integrity", "estimated_minutes": 12,
             "estimate_basis": "operator_estimate"},
            {"task_type": "objective_gap", "estimated_minutes": 15,
             "estimate_basis": "operator_estimate"},
        )
        response = await self.atlas(
            review_effort=effort,
            review_budget_minutes=60,
        )
        portfolio = response["report"]["review_portfolio"]
        self.assertIsNotNone(portfolio)
        self.assertLessEqual(portfolio["estimated_minutes"], 60)
        self.assertFalse(portfolio["persistence_performed"])
        self.assertFalse(portfolio["effort_is_observed"])

    async def test_backend_restricts_source_policy_withdrawal(self):
        self.original["_source_state"] = "withdrawn"
        response = await self.atlas()
        report = response["report"]
        self.assertEqual(report["source_policy"]["included_source_count"], 0)
        self.assertEqual(report["source_policy"]["excluded_source_count"], 1)
        self.assertEqual(report["retrieval"]["retained_hits"], 0)
        self.assertEqual(report["jeeves_handoff"]["citation_count"], 0)
        self.assertTrue(report["review_required"])

    async def test_backend_rejects_changed_snapshot_after_composition(self):
        self.next_row = deepcopy(self.original)
        self.next_row["snapshot"] = deepcopy(self.snapshot)
        self.next_row["snapshot"]["snapshot_digest"] = "d" * 64
        with self.assertRaises(core_crawler.CrawlerError) as error:
            await self.atlas()
        self.assertEqual(error.exception.code, "crawler_research_revision_changed")
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.owned_reads, 2)

    async def test_backend_rejects_source_policy_changed_during_read(self):
        self.next_row = deepcopy(self.original)
        self.next_row["source_use_policies"] = {
            next(iter(self.snapshot["sources"])): {
                "enabled": False, "version": 2,
                "max_age_seconds": 3600, "changed_at": None,
            },
        }
        with self.assertRaises(core_crawler.CrawlerError) as error:
            await self.atlas()
        self.assertEqual(error.exception.code, "crawler_research_revision_changed")
        self.assertEqual(self.owned_reads, 2)

    async def test_backend_rejects_late_source_withdrawal_even_without_version_change(self):
        self.next_row = deepcopy(self.original)
        self.next_row["_source_state"] = "withdrawn"
        with self.assertRaises(core_crawler.CrawlerError) as error:
            await self.atlas()
        self.assertEqual(error.exception.code, "crawler_research_source_changed")
        self.assertEqual(error.exception.status, 409)

    async def test_backend_denies_cross_tenant_session_referencing(self):
        with self.assertRaises(core_crawler.CrawlerError) as error:
            await self.application.campaign_atlas(
                {"tenant_id": "foreign", "owner_id": self.owner["owner_id"]},
                self.session, self.goals(),
            )
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(self.owned_reads, 0)

    async def test_backend_rejects_unsupported_remote_embedding_mode(self):
        with self.assertRaises(ValueError):
            await self.atlas(retrieval_mode="remote_embeddings")

    async def test_backend_rejects_review_workload_over_capacity(self):
        with self.assertRaises(ValueError):
            await self.atlas(review_effort=tuple(
                {"task_type": "passage_integrity", "estimated_minutes": 5,
                 "estimate_basis": "operator_estimate"} for _ in range(8)
            ))


if __name__ == "__main__":
    unittest.main()
