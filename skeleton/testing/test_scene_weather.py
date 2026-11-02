"""Replay, authoring, weather penalties, provenance and portable acceptance."""
from __future__ import annotations

import copy
import unittest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    _advance, export_weather, forecast, import_weather, new_weather,
    normalize_weather, original_weather, resume_weather, simulate_weather,
    verify_weather,
)
from skeleton.game.gameplay.scene_weather_author import edit_weather, preview_weather


class WeatherProductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source, self.actions = original_weather()

    def test_complete_playable_journey_replay_and_export(self) -> None:
        result = simulate_weather(self.source, self.actions)
        self.assertEqual(verify_weather(result), result)
        self.assertEqual(import_weather(export_weather(result)), result)
        self.assertEqual(result["state"]["phase"], "won")
        self.assertEqual(result["state"]["equipped"], "stormcloak")
        self.assertEqual(len(result["journal"]), len(self.actions))
        self.assertEqual(result["save"]["state_digest"], result["state_digest"])

    def test_restart_at_each_action_is_deterministic(self) -> None:
        full = simulate_weather(self.source, self.actions)
        for index in range(len(self.actions) + 1):
            checkpoint = simulate_weather(self.source, self.actions[:index])
            restored = resume_weather(checkpoint, self.actions[index:])
            self.assertEqual(restored, full)

    def test_gear_cannot_be_equipped_before_canonical_pickup(self) -> None:
        session = new_weather(self.source)
        with self.assertRaisesRegex(SceneTravelError, "not been earned"):
            _advance(session, {"kind": "equip", "gear_id": "stormcloak"})
        self.assertEqual(session["state"]["owned_gear"], [])

    def test_canonical_collision_does_not_charge_stamina(self) -> None:
        session = new_weather(self.source)
        with self.assertRaisesRegex(SceneTravelError, "collision"):
            _advance(session, {
                "kind": "survival",
                "action": {"kind": "tile", "action": {
                    "kind": "move", "direction": "west"}},
            })
        self.assertEqual(session["state"]["stamina"], self.source["max_stamina"])
        self.assertEqual(session["journal"], [])

    def test_weather_is_pure_clock_and_no_external_rng(self) -> None:
        spec = normalize_weather(self.source)
        self.assertEqual(forecast(spec, "quay", 1)["kind"], "rain")
        self.assertEqual(forecast(spec, "quay", 2)["kind"], "frost")
        self.assertEqual(forecast(spec, "quay", 3)["kind"], "rain")
        self.assertEqual(forecast(spec, "gate", 8)["kind"], "clear")

    def test_equipment_reduces_penalties_but_never_grants_stamina(self) -> None:
        first = simulate_weather(self.source, self.actions[:2])
        self.assertEqual(first["state"]["owned_gear"], ["stormcloak"])
        equipped = _advance(first, {"kind": "equip", "gear_id": "stormcloak"})
        self.assertEqual(equipped["state"]["stamina"], first["state"]["stamina"])
        self.assertEqual(equipped["state"]["equipped"], "stormcloak")

    def test_unearned_equipment_source_rejected(self) -> None:
        forged = copy.deepcopy(self.source)
        forged["gear"][0]["pickup"] = "quay:imaginary"
        with self.assertRaisesRegex(SceneTravelError, "unearned"):
            normalize_weather(forged)

    def test_missing_scene_weather_rejected(self) -> None:
        forged = copy.deepcopy(self.source)
        forged["climates"].pop()
        with self.assertRaisesRegex(SceneTravelError, "every tile scene"):
            normalize_weather(forged)

    def test_nonfinite_boolean_and_overbudget_inputs_rejected(self) -> None:
        forged = copy.deepcopy(self.source)
        forged["max_stamina"] = True
        with self.assertRaises(SceneTravelError):
            normalize_weather(forged)
        forged = copy.deepcopy(self.source)
        forged["climates"][0]["phases"] *= 20
        with self.assertRaises(SceneTravelError):
            normalize_weather(forged)

    def test_invalid_actions_reject_without_mutation(self) -> None:
        original = new_weather(self.source)
        for action in (
            {"kind": "equip", "gear_id": "unearned"},
            {"kind": "unequip"},
            {"kind": "survival", "action": {"kind": "tile", "action": {
                "kind": "move", "direction": "invalid"}}},
            {"kind": "equip", "gear_id": "unearned", "extra": True},
        ):
            with self.assertRaises(SceneTravelError):
                _advance(original, action)
        self.assertEqual(original, new_weather(self.source))

    def test_forged_journal_and_save_are_rejected(self) -> None:
        saved = simulate_weather(self.source, self.actions[:3])
        variants = []
        forged = copy.deepcopy(saved)
        forged["state"]["stamina"] = 64
        variants.append(forged)
        forged = copy.deepcopy(saved)
        forged["journal"][-1]["receipt"] = "0" * 64
        variants.append(forged)
        forged = copy.deepcopy(saved)
        forged["save"]["parent_save_digest"] = "0" * 64
        variants.append(forged)
        forged = copy.deepcopy(saved)
        forged["source"]["gear"][0]["damage_reduction"] = 8
        variants.append(forged)
        for variant in variants:
            with self.subTest(variant=variants.index(variant)):
                with self.assertRaises(SceneTravelError):
                    verify_weather(variant)

    def test_bundle_checksum_is_not_a_signature(self) -> None:
        session = simulate_weather(self.source, self.actions[:2])
        bundle = export_weather(session)
        bundle["checksum"] = "0" * 64
        with self.assertRaisesRegex(SceneTravelError, "checksum"):
            import_weather(bundle)
        bundle = export_weather(session)
        bundle["session"]["state"]["stamina"] = 100
        bundle["checksum"] = dig({
            k: v for k, v in bundle.items() if k != "checksum"})
        with self.assertRaises(SceneTravelError):
            import_weather(bundle)

    def test_editor_transactional_lease_and_invalid_batch(self) -> None:
        source_before = copy.deepcopy(self.source)
        spec = normalize_weather(self.source)
        edit = [{
            "kind": "replace_phase", "scene_id": "quay", "index": 0,
            "phase": {"kind": "rain", "damage": 1, "stamina_cost": 1},
        }]
        updated = edit_weather(self.source, edit, expected_digest=dig(spec))
        self.assertNotEqual(updated["source_digest"], dig(spec))
        self.assertEqual(self.source, source_before)
        with self.assertRaisesRegex(SceneTravelError, "stale"):
            edit_weather(self.source, edit, expected_digest="0" * 64)
        with self.assertRaises(SceneTravelError):
            edit_weather(self.source, edit + [{
                "kind": "replace_phase", "scene_id": "unknown",
                "index": 0, "phase": edit[0]["phase"],
            }])
        self.assertEqual(self.source, source_before)

    def test_preview_uses_same_canonical_gameplay(self) -> None:
        result = preview_weather(self.source, self.actions)
        self.assertEqual(result["session"]["state_digest"], result["state_digest"])
        self.assertEqual(result["phase"], "won")


if __name__ == "__main__":
    unittest.main()
