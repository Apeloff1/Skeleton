"""HTTP discovery pages the real virtual catalogs without invoking a writer."""
from __future__ import annotations

from contextlib import ExitStack
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import game_frontier_authoring as owner
from routes import game_frontier_authoring as routes
from routes.gameforge_auth import get_current_user
from skeleton.forge import game_frontier_studio_authoring as canonical
from skeleton.forge.game_frontier_studio_continuity_production import search_continuities
from skeleton.forge.game_frontier_studio_epic_variations import search_epics
from skeleton.forge.game_frontier_studio_production_recipes import search_recipes
from skeleton.forge.game_frontier_studio_saga_production import search_sagas


SEARCHES = {"saga": search_sagas, "epic": search_epics}
REGISTRIES = {"saga": canonical.SAGA_ACTIONS, "epic": canonical.EPIC_ACTIONS}
FILTER_OPTIONS = {
    "domain": "domains", "system_layer": "system_layers", "director": "directors",
    "finish": "finishes", "worldline": "worldlines", "phase": "phases",
    "campaign": "campaigns", "chronicle": "chronicles", "epoch": "epochs",
    "saga": "sagas", "epic": "epics",
}


class GameFrontierRecipeDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.principal = {
            "tenant_id": "recipe-reader", "email": "reader@example.test", "role": "viewer",
        }
        self.app = FastAPI()
        self.app.include_router(routes.router, prefix="/api")
        self.app.dependency_overrides[get_current_user] = lambda: self.principal
        self.boundaries = ExitStack()
        self.addCleanup(self.boundaries.close)
        self.forbidden = []
        # A read-only catalog request must not load/save a project, schedule work,
        # compile a game or apply any proposed operation. The real search owner runs.
        for target, name, asynchronous in (
            (owner, "apply_authoring_batch", False),
            (owner, "compile_studio_expedition", False),
            (owner.workspace, "get_project", True),
            (owner.workspace, "save_editor", True),
            (owner.workspace, "start_job", True),
            (owner.workspace, "_admit", True),
        ):
            mock = (AsyncMock if asynchronous else Mock)(
                side_effect=AssertionError(f"discovery invoked {name}"))
            self.boundaries.enter_context(patch.object(target, name, mock))
            self.forbidden.append(mock)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.base = "/api/game-frontier-authoring"

    def tearDown(self):
        for boundary in self.forbidden:
            boundary.assert_not_called()

    def page(self, **params):
        response = self.client.get(self.base + "/recipes", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def exact_filters(self, generation):
        catalog = SEARCHES[generation](limit=1)
        return {name: catalog[options][2] for name, options in FILTER_OPTIONS.items()
                if options in catalog}

    def assert_search_error(self, **params):
        response = self.client.get(self.base + "/recipes", params=params)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"]["code"], "invalid_forge_recipe_search")

    def test_catalog_counts_are_current_and_do_not_double_count_supplemental_continuity(self):
        response = self.client.get(self.base + "/actions")
        self.assertEqual(response.status_code, 200, response.text)
        catalog = response.json()
        self.assertEqual(catalog["schema"], "skeleton.game.frontier_studio_authoring_catalog.v1")
        self.assertEqual(catalog["actions"], list(canonical.AUTHORING_ACTIONS[:500]))
        self.assertEqual(catalog["core_action_count"], 500)
        self.assertEqual(catalog["action_count"], len(canonical.AUTHORING_ACTIONS))
        self.assertEqual(catalog["action_count"], 50_000_000_000_000)
        self.assertEqual(catalog["recipe_count"], catalog["action_count"] - 500)
        generations = {
            "classic": canonical.RECIPE_ACTIONS, "expanded": canonical.EXPANDED_RECIPE_ACTIONS,
            "directed": canonical.DIRECTED_ACTIONS, "final": canonical.FINAL_PRODUCTION_ACTIONS,
            "worldline": canonical.WORLDLINE_ACTIONS, "phase": canonical.PHASE_ACTIONS,
            "campaign": canonical.CAMPAIGN_ACTIONS, "chronicle": canonical.CHRONICLE_ACTIONS,
            "epoch": canonical.EPOCH_ACTIONS, "saga": canonical.SAGA_ACTIONS,
            "epic": canonical.EPIC_ACTIONS,
        }
        for generation, registry in generations.items():
            self.assertEqual(catalog[generation + "_recipe_count"], len(registry))
        self.assertEqual(sum(catalog[name + "_recipe_count"] for name in generations),
                         catalog["recipe_count"])
        self.assertEqual(catalog["continuity_recipe_count"], len(canonical.CONTINUITY_ACTIONS))
        self.assertEqual(catalog["recipe_search_path"], self.base + "/recipes")

    def test_saga_and_epic_exact_filters_preserve_the_real_owner_projection(self):
        for generation, search in SEARCHES.items():
            with self.subTest(generation=generation):
                filters = self.exact_filters(generation)
                result = self.page(generation=generation, **filters, offset=13, limit=3)
                expected = search(**filters, offset=13, limit=3)
                self.assertEqual(result, json.loads(json.dumps(expected)))
                self.assertEqual(result["matched"], 450)
                self.assertEqual(result["total_catalog"], len(REGISTRIES[generation]))
                for item in result["items"]:
                    self.assertIn(item["operation"], REGISTRIES[generation])
                    self.assertIn(item["operation"], canonical.AUTHORING_ACTIONS)
                    self.assertIs(item["actual_project_mutation"], True)
                    for name, value in filters.items():
                        self.assertEqual(item["direction" if name == "director" else name], value)
                    if generation == "epic":
                        self.assertIn(item["base_operation"], canonical.SAGA_ACTIONS)
                    else:
                        self.assertIn(item["base_operation"], canonical.EPOCH_ACTIONS)

    def test_pages_are_stable_disjoint_and_stop_at_the_filtered_boundary(self):
        for generation in SEARCHES:
            with self.subTest(generation=generation):
                filters = self.exact_filters(generation)
                first = self.page(generation=generation, **filters, limit=3)
                again = self.page(generation=generation, **filters, limit=3)
                second = self.page(generation=generation, **filters,
                                   offset=first["next_offset"], limit=3)
                self.assertEqual(first, again)
                self.assertEqual(first["next_offset"], 3)
                self.assertTrue({row["operation"] for row in first["items"]}.isdisjoint(
                    row["operation"] for row in second["items"]))
                tail = self.page(generation=generation, **filters, offset=448, limit=64)
                self.assertEqual(len(tail["items"]), 2)
                self.assertIsNone(tail["next_offset"])
                exhausted = self.page(generation=generation, **filters, offset=450, limit=1)
                self.assertEqual(exhausted["items"], [])
                self.assertIsNone(exhausted["next_offset"])

    def test_last_virtual_catalog_page_uses_exact_large_integer_rank(self):
        for generation, registry in REGISTRIES.items():
            with self.subTest(generation=generation):
                # These trillion-scale ranks must remain O(page), not enumerate.
                page = self.page(generation=generation, offset=len(registry) - 2, limit=3)
                self.assertEqual([row["operation"] for row in page["items"]],
                                 list(registry[len(registry) - 2:]))
                self.assertIsNone(page["next_offset"])
                empty = self.page(generation=generation, offset=len(registry), limit=1)
                self.assertEqual(empty["items"], [])
                self.assertIsNone(empty["next_offset"])

    def test_default_classic_and_separate_continuity_remain_compatible(self):
        self.assertEqual(self.page(), json.loads(json.dumps(search_recipes())))
        continuity = search_continuities(limit=1)["continuities"][3]
        result = self.page(generation="continuity", continuity=continuity, offset=7, limit=2)
        self.assertEqual(result, json.loads(json.dumps(
            search_continuities(continuity=continuity, offset=7, limit=2))))
        self.assertNotIn("sagas", result)
        self.assertNotIn("epics", result)
        for item in result["items"]:
            self.assertEqual(item["continuity"], continuity)
            self.assertIn(item["operation"], canonical.CONTINUITY_ACTIONS)
            self.assertIn(item["operation"], canonical.AUTHORING_ACTIONS)

    def test_unknown_hostile_or_cross_generation_filters_are_rejected(self):
        for generation in SEARCHES:
            for name in self.exact_filters(generation):
                for value in ("not_a_canonical_option", "../provider/execute", "x" * 41):
                    with self.subTest(generation=generation, filter=name, value=value):
                        self.assert_search_error(generation=generation, **{name: value})
            for extra in ({"query": "create now"}, {"continuity": "narrative_recall"}):
                with self.subTest(generation=generation, extra=extra):
                    self.assert_search_error(generation=generation, **extra)
        for generation in ("classic", "expanded", "directed", "final", "worldline",
                           "phase", "campaign", "chronicle", "epoch", "continuity"):
            with self.subTest(generation=generation):
                self.assert_search_error(generation=generation, saga="homecoming")
                self.assert_search_error(generation=generation, epic="continental_odyssey")
        self.assert_search_error(generation="saga", epic="continental_odyssey")
        self.assert_search_error(generation="unknown")

    def test_offset_and_page_size_are_bounded_without_boolean_coercion(self):
        for generation, registry in REGISTRIES.items():
            for params in ({"offset": -1}, {"offset": len(registry) + 1},
                           {"offset": 10 ** 30}, {"limit": 0}, {"limit": 65}):
                with self.subTest(generation=generation, params=params):
                    self.assert_search_error(generation=generation, **params)
            for params in ({"offset": "true"}, {"offset": "False"}, {"limit": "true"}):
                with self.subTest(generation=generation, params=params):
                    response = self.client.get(self.base + "/recipes",
                                               params={"generation": generation, **params})
                    self.assertEqual(response.status_code, 422, response.text)

    def test_an_authenticated_viewer_is_required_even_for_pure_discovery(self):
        for principal, status in (
            (None, 401),
            ({"email": "reader@example.test", "role": "viewer", "dev_mode": True}, 401),
            ({"email": "reader@example.test", "role": "viewer", "disabled": True}, 401),
            ({"tenant_id": "recipe-reader", "role": "viewer"}, 403),
            ({"email": "reader@example.test", "role": "unrecognized"}, 403),
        ):
            self.principal = principal
            for path in ("/recipes?generation=saga", "/recipes?generation=epic", "/actions"):
                with self.subTest(principal=principal, path=path):
                    response = self.client.get(self.base + path)
                    self.assertEqual(response.status_code, status, response.text)


if __name__ == "__main__":
    unittest.main()
