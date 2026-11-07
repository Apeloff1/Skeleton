"""The shared ``run`` command drives the full ten-stage GameForge pipeline."""

from __future__ import annotations

from skeleton.application import build_runtime_command_service

TEN_STAGES = ["ingest", "detect", "tensor", "lattice", "oracle", "forge", "jeeves", "sim", "emit", "seal"]


class _BareState:
    pass


class _QuestionnaireForge:
    def run(self, answers, title=None, target="json", repair=False):
        return {"answers": dict(answers), "title": title, "target": target, "repair": repair}


class _QuestionnaireState:
    gameforge = _QuestionnaireForge()


def test_vision_runs_all_ten_stages_in_order():
    result = build_runtime_command_service(_BareState()).execute(
        "run", {"vision": "neon extraction raid under a dying city", "archetype": "extraction"}
    )
    assert result.ok, result.to_payload()
    data = result.data
    assert data["status"] == "generated"
    assert data["mode"] == "pipeline"
    pipeline = data["pipeline"]
    assert [stage["name"] for stage in pipeline["stages"]] == TEN_STAGES
    assert all(stage["status"] == "SUCCEEDED" for stage in pipeline["stages"])
    assert pipeline["succeeded"] is True and pipeline["complete"] is True
    assert pipeline["mass"] == 1.0
    assert pipeline["ledger"]["valid"] is True
    assert "project.godot" in pipeline["file_names"]
    assert "files" not in data


def test_pipeline_runner_is_cached_on_state_and_files_opt_in():
    state = _BareState()
    service = build_runtime_command_service(state)
    first = service.execute("run", {"mode": "pipeline", "vision": "arena brawler", "include_files": True})
    assert first.ok, first.to_payload()
    runner = state.gameforge_run
    assert "project.godot" in first.data["files"]
    second = build_runtime_command_service(state).execute("run", {"mode": "pipeline", "vision": "arena brawler"})
    assert second.ok
    assert state.gameforge_run is runner


def test_questionnaire_path_is_preserved_without_vision():
    result = build_runtime_command_service(_QuestionnaireState()).execute("run", {"answers": {"seed": 1}})
    assert result.ok
    assert result.data == {"game": {"answers": {"seed": 1}, "title": None, "target": "json", "repair": False}, "status": "generated"}


def test_explicit_questionnaire_mode_ignores_vision():
    result = build_runtime_command_service(_QuestionnaireState()).execute(
        "run", {"mode": "questionnaire", "answers": {}, "vision": "ignored"}
    )
    assert result.ok
    assert "game" in result.data


def test_pipeline_rejects_bad_arguments():
    service = build_runtime_command_service(_BareState())
    for payload in (
        {"mode": "pipeline"},
        {"mode": "warp"},
        {"mode": "pipeline", "vision": 7},
        {"mode": "pipeline", "vision": "x", "playtest": "always"},
        {"mode": "pipeline", "vision": "x", "include_files": "yes"},
        {"mode": "pipeline", "vision": "x" * 5000},
    ):
        result = service.execute("run", payload)
        assert result.ok is False, payload
        assert result.to_payload()["error"]["code"] == "invalid_argument"


def test_incomplete_pipeline_is_a_conflict_not_a_success():
    result = build_runtime_command_service(_BareState()).execute("run", {"vision": "x", "target": "json"})
    assert result.ok is False
    error = result.to_payload()["error"]
    assert error["code"] == "conflict"
    assert "emit" in error["details"]["failed_stages"]
    assert result.http_status == 409


def test_missing_runtime_without_vision_or_answers_is_unavailable():
    result = build_runtime_command_service(_BareState()).execute("run", {})
    assert result.ok is False
    assert result.to_payload()["error"]["code"] == "unavailable"
