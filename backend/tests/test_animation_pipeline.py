"""
Tests for Text-to-Animation Pipeline
"""

import pytest
from fastapi.testclient import TestClient


class TestAnimationPipeline:
    """Test suite for Animation Pipeline endpoints."""

    @pytest.mark.unit
    def test_animation_overview(self, client: TestClient):
        """Test animation pipeline overview endpoint."""
        response = client.get("/api/animation-pipeline/overview")
        assert response.status_code == 200
        data = response.json()
        
        assert "pipeline" in data
        assert "capabilities" in data
        assert "rig_types" in data
        assert "animation_types" in data

    @pytest.mark.unit
    def test_generate_humanoid_rig(self, client: TestClient):
        """Test generating a humanoid skeleton."""
        response = client.post(
            "/api/animation-pipeline/rig/generate",
            json={
                "description": "humanoid character",
                "include_fingers": True,
                "include_face_rig": False
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        skeleton = data["skeleton"]
        assert "bones" in skeleton
        assert "ik_chains" in skeleton
        assert skeleton["type"] == "humanoid"
        assert len(skeleton["bones"]) > 20  # Humanoid has 24+ bones

    @pytest.mark.unit
    def test_generate_rig_with_fingers(self, client: TestClient):
        """Test that finger bones are added when requested."""
        response = client.post(
            "/api/animation-pipeline/rig/generate",
            json={
                "description": "human",
                "include_fingers": True
            }
        )
        data = response.json()
        
        skeleton = data["skeleton"]
        assert skeleton["metadata"]["has_fingers"] is True
        # Should have additional finger bones
        assert skeleton["metadata"]["bone_count"] > 24

    @pytest.mark.unit
    def test_generate_animation(self, client: TestClient, sample_animation_request: dict):
        """Test generating keyframe animation."""
        response = client.post(
            "/api/animation-pipeline/animation/generate",
            json=sample_animation_request
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        animation = data["animation"]
        assert "keyframes" in animation
        assert "duration" in animation
        assert animation["looping"] is True
        assert len(animation["keyframes"]) > 0

    @pytest.mark.unit
    def test_generate_blend_tree(self, client: TestClient):
        """Test generating a blend tree."""
        response = client.post(
            "/api/animation-pipeline/blend-tree/generate",
            json={
                "animations": ["idle", "walk", "run"],
                "blend_parameter": "speed",
                "blend_type": "1d"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        blend_tree = data["blend_tree"]
        assert blend_tree["parameter"] == "speed"
        assert len(blend_tree["nodes"]) == 3

    @pytest.mark.unit
    def test_generate_state_machine(self, client: TestClient):
        """Test generating an animation state machine."""
        response = client.post(
            "/api/animation-pipeline/state-machine/generate",
            json={
                "states": ["idle", "walk", "run", "jump"],
                "default_state": "idle",
                "transitions": []
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        sm = data["state_machine"]
        assert sm["default_state"] == "idle"
        assert "idle" in sm["states"]
        assert "parameters" in sm


ANIM = "/api/animation-pipeline"


def _combat(client: TestClient, **overrides) -> dict:
    payload = {"description": "character attack", "animation_type": "combat"}
    payload.update(overrides)
    response = client.post(f"{ANIM}/animation/generate", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["animation"]


class TestHitFrameContract:
    """Combat clips expose one frame-exact timing source for VFX and audio."""

    @pytest.mark.unit
    def test_contact_event_carries_integer_hit_frame(self, client: TestClient):
        animation = _combat(client)
        contacts = [e for e in animation["events"] if e["type"] == "contact"]
        assert len(contacts) == 1
        contact = contacts[0]
        assert isinstance(contact["hit_frame"], int)
        assert contact["hit_frame"] == animation["timing"]["hit_frame"]
        assert contact["frame"] == contact["hit_frame"]
        assert set(contact["cue_hooks"]) == {"vfx", "audio"}
        active = animation["timing"]["phases"]["active"]
        assert active["start_frame"] <= contact["hit_frame"] < active["end_frame"]

    @pytest.mark.unit
    def test_every_event_is_frame_stamped_and_ordered(self, client: TestClient):
        animation = _combat(client)
        frames = [e["frame"] for e in animation["events"]]
        assert all(isinstance(f, int) for f in frames)
        assert frames == sorted(frames)
        types = [e["type"] for e in animation["events"]]
        for expected in ("anticipation_start", "contact", "damage_start", "damage_end", "recovery_start"):
            assert expected in types
        fps = animation["fps"]
        for event in animation["events"]:
            assert event["time"] == pytest.approx(event["frame"] / fps, abs=1e-4)

    @pytest.mark.unit
    def test_light_attack_phases_follow_template_damage_window(self, client: TestClient):
        animation = _combat(client)  # no duration -> light attack template length (0.5s)
        timing = animation["timing"]
        assert animation["duration"] == pytest.approx(0.5)
        assert timing["weight_class"] == "light"
        assert timing["total_frames"] == 15
        phases = timing["phases"]
        assert phases["anticipation"]["frames"] == 6
        assert phases["active"]["frames"] == 4
        assert phases["recovery"]["frames"] == 5
        assert sum(p["frames"] for p in phases.values()) == timing["total_frames"]
        assert timing["readability"]["readable"] is True

    @pytest.mark.unit
    def test_powerful_attack_uses_heavy_budget(self, client: TestClient):
        animation = _combat(client, description="powerful attack")
        timing = animation["timing"]
        assert timing["weight_class"] == "heavy"
        assert timing["phases"]["anticipation"]["frames"] >= 10
        assert timing["readability"]["readable"] is True

    @pytest.mark.unit
    def test_hit_frame_scales_with_duration(self, client: TestClient):
        animation = _combat(client, duration=1.0)
        assert animation["timing"]["total_frames"] == 30
        assert animation["timing"]["hit_frame"] == 12

    @pytest.mark.unit
    def test_strike_keyframe_lands_on_hit_frame(self, client: TestClient):
        animation = _combat(client)
        hit_time = animation["timing"]["hit_frame"] / animation["fps"]
        times = [k["time"] for k in animation["keyframes"]]
        assert any(t == pytest.approx(hit_time, abs=1e-4) for t in times)
        assert times == sorted(times)

    @pytest.mark.unit
    def test_short_clip_flags_unreadable_timing(self, client: TestClient):
        animation = _combat(client, duration=0.1)
        readability = animation["timing"]["readability"]
        assert readability["valid"] is True
        assert readability["readable"] is False
        assert readability["warnings"]


class TestAnimationRequestValidation:
    @pytest.mark.unit
    @pytest.mark.parametrize("duration", [0, -1.0, 0.01, 10000])
    def test_out_of_range_duration_rejected(self, client: TestClient, duration):
        response = client.post(
            f"{ANIM}/animation/generate",
            json={"description": "humanoid idle", "duration": duration},
        )
        assert response.status_code == 422

    @pytest.mark.unit
    def test_minimum_duration_generates_frames(self, client: TestClient):
        response = client.post(
            f"{ANIM}/animation/generate",
            json={"description": "humanoid walking", "duration": 0.1},
        )
        assert response.status_code == 200
        assert len(response.json()["animation"]["keyframes"]) >= 2


class TestReducedMotion:
    @pytest.mark.unit
    def test_reduced_motion_removes_root_bob(self, client: TestClient):
        response = client.post(
            f"{ANIM}/animation/generate",
            json={"description": "humanoid walking", "reduced_motion": True},
        )
        animation = response.json()["animation"]
        assert animation["accessibility"]["reduced_motion"] is True
        assert animation["accessibility"]["timing_preserved"] is True
        assert all(k["root_position"][1] == 0 for k in animation["keyframes"])

    @pytest.mark.unit
    def test_reduced_motion_keeps_stride_timing(self, client: TestClient):
        def walk(reduced: bool) -> dict:
            return client.post(
                f"{ANIM}/animation/generate",
                json={"description": "humanoid walking", "reduced_motion": reduced},
            ).json()["animation"]

        full, reduced = walk(False), walk(True)
        assert [k["time"] for k in full["keyframes"]] == [k["time"] for k in reduced["keyframes"]]
        assert [k["root_position"][2] for k in full["keyframes"]] == [
            k["root_position"][2] for k in reduced["keyframes"]
        ]

    @pytest.mark.unit
    def test_reduced_motion_never_moves_hit_frame(self, client: TestClient):
        full = _combat(client)
        reduced = _combat(client, reduced_motion=True)
        assert full["timing"]["hit_frame"] == reduced["timing"]["hit_frame"]
        assert full["events"] == reduced["events"]


class TestTimingEndpoints:
    @pytest.mark.unit
    def test_budgets_endpoint(self, client: TestClient):
        data = client.get(f"{ANIM}/timing/budgets").json()
        assert data["default_fps"] == 30
        assert set(data["combat_budgets"]) == {"light", "heavy"}
        for preset in data["presets"].values():
            assert isinstance(preset["hit_frame"], int)

    @pytest.mark.unit
    def test_presets_are_within_budget(self, client: TestClient):
        presets = client.get(f"{ANIM}/timing/budgets").json()["presets"]
        for preset in presets.values():
            phases = preset["phases"]
            response = client.post(
                f"{ANIM}/timing/validate",
                json={
                    "weight_class": preset["weight_class"],
                    "anticipation_frames": phases["anticipation"]["frames"],
                    "active_frames": phases["active"]["frames"],
                    "recovery_frames": phases["recovery"]["frames"],
                    "hit_frames": [preset["hit_frame"]],
                    "total_frames": preset["total_frames"],
                },
            )
            assert response.json()["readable"] is True, (preset["move"], response.json())

    @pytest.mark.unit
    def test_validate_accepts_readable_timing(self, client: TestClient):
        response = client.post(
            f"{ANIM}/timing/validate",
            json={"anticipation_frames": 6, "active_frames": 4, "recovery_frames": 5, "hit_frames": [6]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["readable"] is True
        assert data["active_window"] == [6, 10]

    @pytest.mark.unit
    @pytest.mark.parametrize("hit_frames", [[5], [10], [], [8, 7], [7, 7]])
    def test_validate_rejects_bad_hit_frames(self, client: TestClient, hit_frames):
        data = client.post(
            f"{ANIM}/timing/validate",
            json={"anticipation_frames": 6, "active_frames": 4, "recovery_frames": 5, "hit_frames": hit_frames},
        ).json()
        assert data["valid"] is False
        assert data["errors"]

    @pytest.mark.unit
    def test_validate_rejects_phase_total_mismatch(self, client: TestClient):
        data = client.post(
            f"{ANIM}/timing/validate",
            json={
                "anticipation_frames": 6, "active_frames": 4, "recovery_frames": 5,
                "hit_frames": [6], "total_frames": 20,
            },
        ).json()
        assert data["valid"] is False

    @pytest.mark.unit
    def test_validate_warns_on_unreadable_anticipation(self, client: TestClient):
        data = client.post(
            f"{ANIM}/timing/validate",
            json={"anticipation_frames": 2, "active_frames": 4, "recovery_frames": 5, "hit_frames": [2]},
        ).json()
        assert data["valid"] is True
        assert data["readable"] is False
        assert any("anticipation" in w for w in data["warnings"])

    @pytest.mark.unit
    def test_budget_scales_with_fps(self, client: TestClient):
        data = client.post(
            f"{ANIM}/timing/validate",
            json={
                "fps": 60, "anticipation_frames": 6, "active_frames": 4, "recovery_frames": 5,
                "hit_frames": [6],
            },
        ).json()
        assert data["budget"]["anticipation_min"] == 8
        assert data["readable"] is False


class TestStateMachineGuards:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "payload",
        [
            {"states": ["idle", "walk"], "default_state": "run"},
            {"states": ["idle", "idle"], "default_state": "idle"},
            {"states": ["idle"], "default_state": "idle", "transitions": [{"from": "idle", "to": "ghost"}]},
            {"states": ["idle"], "default_state": "idle", "transitions": [{"from": "ghost", "to": "idle"}]},
            {"states": ["idle", "walk"], "default_state": "idle",
             "transitions": [{"from": "idle", "to": "walk", "duration": -0.1}]},
            {"states": ["idle", "walk"], "default_state": "idle",
             "transitions": [{"from": "idle", "to": "walk", "duration": 5}]},
            {"states": ["idle", "death"], "default_state": "idle",
             "transitions": [{"from": "death", "to": "idle"}]},
            {"states": ["idle", "walk"], "default_state": "idle",
             "transitions": [{"from": "any", "to": "walk", "priority": "high"}]},
        ],
    )
    def test_invalid_graphs_rejected(self, client: TestClient, payload):
        response = client.post(f"{ANIM}/state-machine/generate", json=payload)
        assert response.status_code == 422

    @pytest.mark.unit
    def test_auto_machine_has_no_dead_ends(self, client: TestClient):
        sm = client.post(
            f"{ANIM}/state-machine/generate",
            json={"states": ["idle", "walk", "run", "jump", "attack", "dodge", "hit_react", "death"],
                  "default_state": "idle"},
        ).json()["state_machine"]
        validation = sm["validation"]
        assert validation["valid"] is True
        assert validation["dead_end_states"] == []
        assert validation["unreachable_states"] == []
        assert sm["states"]["attack"]["transitions"][0]["has_exit_time"] is True
        assert sm["states"]["jump"]["transitions"][0]["condition"] == "grounded"
        assert sm["states"]["death"]["transitions"] == []
        assert sm["states"]["death"]["terminal"] is True

    @pytest.mark.unit
    def test_any_state_parameters_and_guards(self, client: TestClient):
        sm = client.post(
            f"{ANIM}/state-machine/generate",
            json={"states": ["idle", "walk", "jump", "attack", "death"], "default_state": "idle"},
        ).json()["state_machine"]
        params = {p["name"]: p["type"] for p in sm["parameters"]}
        assert params["attack_trigger"] == "trigger"
        assert params["jump_trigger"] == "trigger"
        assert params["speed"] == "float"
        assert params["health"] == "float"
        assert params["grounded"] == "bool"
        assert "anim_complete" not in params
        priorities = [t["priority"] for t in sm["any_state_transitions"]]
        assert priorities == sorted(priorities, reverse=True)
        assert sm["any_state_transitions"][0]["to"] == "death"
        for trans in sm["any_state_transitions"]:
            assert trans["can_transition_to_self"] is False
            assert trans["excluded_source_states"] == ["death"]

    @pytest.mark.unit
    def test_locomotion_thresholds_have_hysteresis(self, client: TestClient):
        sm = client.post(
            f"{ANIM}/state-machine/generate",
            json={"states": ["idle", "walk", "run"], "default_state": "idle"},
        ).json()["state_machine"]

        def threshold(src: str, dst: str) -> float:
            cond = next(t["condition"] for t in sm["states"][src]["transitions"] if t["to"] == dst)
            return float(cond.split()[-1])

        assert threshold("walk", "idle") < threshold("idle", "walk")
        assert threshold("run", "walk") < threshold("walk", "run")

    @pytest.mark.unit
    def test_authored_dead_end_is_reported(self, client: TestClient):
        sm = client.post(
            f"{ANIM}/state-machine/generate",
            json={"states": ["idle", "walk", "attack", "emote"], "default_state": "idle",
                  "transitions": [{"from": "idle", "to": "attack", "condition": "attack_trigger"},
                                  {"from": "idle", "to": "walk", "condition": "speed > 0.1"},
                                  {"from": "walk", "to": "idle", "condition": "speed < 0.05"}]},
        ).json()["state_machine"]
        validation = sm["validation"]
        assert validation["valid"] is False
        assert "attack" in validation["dead_end_states"]
        assert "emote" in validation["unreachable_states"]


class TestBlendTreeCoverage:
    @pytest.mark.unit
    def test_2d_blend_keeps_cardinal_positions(self, client: TestClient):
        tree = client.post(
            f"{ANIM}/blend-tree/generate",
            json={"animations": ["fwd", "right", "back", "left"], "blend_type": "2d"},
        ).json()["blend_tree"]
        assert [tuple(n["position"]) for n in tree["nodes"]] == [(0, 1), (1, 0), (0, -1), (-1, 0)]

    @pytest.mark.unit
    def test_2d_blend_does_not_drop_clips(self, client: TestClient):
        clips = [f"dir_{i}" for i in range(8)]
        tree = client.post(
            f"{ANIM}/blend-tree/generate", json={"animations": clips, "blend_type": "2d"}
        ).json()["blend_tree"]
        assert [n["animation"] for n in tree["nodes"]] == clips
        positions = {tuple(n["position"]) for n in tree["nodes"]}
        assert len(positions) == 8


class TestAIFallback:
    @pytest.mark.unit
    @pytest.mark.parametrize("mode", ["unsuccessful", "raises"])
    def test_ai_animation_falls_back_to_templates(self, client: TestClient, monkeypatch, mode):
        import routes.animation_pipeline as animation_pipeline

        class _FakeLLM:
            async def generate_animation_sequence(self, **_kwargs):
                if mode == "raises":
                    raise RuntimeError("provider down")
                return {"success": False}

        monkeypatch.setattr(animation_pipeline, "get_game_llm_service", lambda: _FakeLLM())
        response = client.post(
            f"{ANIM}/ai/animation/generate",
            json={"character_type": "humanoid", "animation_name": "attack"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ai_generated"] is False
        assert data["animation"]["type"] == "combat"
        assert isinstance(data["animation"]["timing"]["hit_frame"], int)
