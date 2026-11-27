"""Restored read-only Epic adapter uses the real graph owner and scoped source."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import game_frontier_authoring as authoring
from core.game_learning import GameLearningError
from routes import game_frontier_authoring as routes
from routes.gameforge_auth import get_current_user
from skeleton.forge.game_frontier_studio_document import create_authoring_project, authored_document


class EpicRouteAdapterTests(unittest.TestCase):
    def setUp(self):
        self.principal = {"tenant_id": "epic-tenant", "email": "epic-owner@example.test", "role": "viewer"}
        base = create_authoring_project("epic-owned", width=7, height=7)
        self.source = replace(base, layers=(base.layers[0], replace(base.layers[0], layer_id="sky", elevation_m=12)))
        self.body = {"layer_ids": ["ground", "sky"], "connectors": [{
            "connector_id": "lift", "from": {"layer": "ground", "x": 3, "y": 3},
            "to": {"layer": "sky", "x": 3, "y": 3}, "mode": "elevator", "bidirectional": True}],
            "itineraries": [{"journey_id": "Crossing", "start": {"layer": "ground", "x": 0, "y": 3},
                             "goal": {"layer": "sky", "x": 6, "y": 3}, "require_alternate": False}]}
        self.app = FastAPI()
        self.app.include_router(routes.router, prefix="/api")
        self.app.dependency_overrides[get_current_user] = lambda: self.principal
        self.lookup = AsyncMock(return_value=({"version": 7}, self.source))
        self.boundary = patch.object(authoring, "_source", self.lookup)
        self.boundary.start()
        self.client = TestClient(self.app)
        self.url = "/api/game-frontier-authoring/projects/epic-owned/epic-routes/audit"

    def tearDown(self):
        self.client.close()
        self.boundary.stop()

    def test_real_graph_replay_preserves_source_and_never_claims_native_transfer(self):
        before = authored_document(self.source)
        response = self.client.post(self.url, json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report["schema"], "skeleton.forge.epic_interlayer_reference.v1")
        self.assertEqual(report["project_id"], "epic-owned")
        self.assertEqual(report["source_version"], 7)
        self.assertEqual(report["passed_count"], 1)
        self.assertEqual(report["journeys"][0]["primary"]["connector_ids"], ["lift"])
        self.assertTrue(report["verified_against_authoritative_source"])
        for key in ("native_engine_executed", "transport_actions_applied", "release_certified"):
            self.assertIs(report[key], False)
        self.assertTrue(report["source_reference_only"])
        self.assertEqual(authored_document(self.source), before)
        self.assertEqual(self.lookup.await_args.args[0], {
            "tenant_id": "epic-tenant", "owner_id": "epic-owner@example.test"})

    def test_unauthenticated_and_foreign_scope_are_denied(self):
        self.principal = None
        self.assertEqual(self.client.post(self.url, json=self.body).status_code, 401)
        self.lookup.assert_not_awaited()
        self.principal = {"tenant_id": "other", "email": "other@example.test", "role": "viewer"}
        self.lookup.side_effect = GameLearningError("project_not_found", "Project is not owned.", 404)
        self.assertEqual(self.client.post(self.url, json=self.body).status_code, 404)

    def test_closed_transport_and_graph_shapes_reject_unknown_or_invalid_proposals(self):
        for body in [{**self.body, "provider": "hosted"}, {**self.body, "layer_ids": []},
                     {**self.body, "connectors": [{}] * 65}, {**self.body, "itineraries": []}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.url, json=body).status_code, 422)
        self.lookup.assert_not_awaited()
        wrong = deepcopy(self.body)
        wrong["connectors"][0]["from"]["x"] = True
        self.assertEqual(self.client.post(self.url, json=wrong).status_code, 422)

    def test_divergent_independent_replay_cannot_return_a_successful_report(self):
        with patch("skeleton.forge.game_frontier_studio_epic_route_graph.verify_epic_interlayer_routes", return_value=False):
            response = self.client.post(self.url, json=self.body)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "workspace_input_rejected")
        self.assertNotIn("journeys", response.json())


if __name__ == "__main__":
    unittest.main()
