"""Deterministic regressions for complete GameForge review evidence and source custody."""
from __future__ import annotations

import asyncio
import json

import pytest

from core.forge_quality_contract import (
    MAX_ARTIFACT_CHARS, artifact_text, checked_json, compatible_rewrite,
    review_scores, source_digest,
)


FACTORS = ["coherence", "depth", "originality", "polish", "consistency", "completeness"]


def judgment(score=97, *, factors=None, overall=None):
    return json.dumps({
        "overall": score if overall is None else overall,
        "factors": {key: score for key in FACTORS} if factors is None else factors,
        "feedback": "Improve the weakest feature.",
    })


@pytest.mark.parametrize("text", [
    '{"a":1,"a":2}',
    '{"nested":{"a":1,"a":2}}',
    '{"x":NaN}',
    '{"x":1e9999}',
    '{"x":"\\ud800"}',
    '{"\\ud800":1}',
    'prefix {"a":1}',
    '{"a":1} tail',
    "[" * 30 + "0" + "]" * 30,
    '{"text":"' + "x" * MAX_ARTIFACT_CHARS + '"}',
])
def test_invalid_or_unbounded_document_rejected(text):
    with pytest.raises(ValueError):
        checked_json(text)


@pytest.mark.parametrize("value", [None, [], {}, 2, True, float("inf"), {"a": float("nan")}])
def test_artifact_must_be_nonempty_bounded_structure(value):
    with pytest.raises(ValueError):
        artifact_text(value)


def test_canonical_mapping_and_exact_string_source():
    a, value = artifact_text({"z": [1, 2], "a": "æ"})
    b, _ = artifact_text({"a": "æ", "z": [1, 2]})
    assert a == b
    assert value == {"a": "æ", "z": [1, 2]}
    original = '{ "z": [1, 2], "a": "æ" }'
    text, parsed = artifact_text(original)
    assert text == original and parsed == value
    assert source_digest(text) != source_digest(a)


@pytest.mark.parametrize("score", [True, 95.0, -1, 101, "99", None])
def test_scores_require_real_integers_in_range(score):
    entries = {key: 97 for key in FACTORS}
    entries["depth"] = score
    with pytest.raises(ValueError):
        review_scores(judgment(factors=entries), FACTORS)


def test_exact_required_dimensions_and_envelope():
    assert review_scores(judgment(), FACTORS)[0] == 97
    with pytest.raises(ValueError):
        review_scores(judgment(factors={"depth": 100}), FACTORS)
    with pytest.raises(ValueError):
        review_scores(judgment(factors={**{key: 99 for key in FACTORS}, "extra": 100}), FACTORS)
    with pytest.raises(ValueError):
        review_scores(judgment()[:-1] + ', "passed": true}', FACTORS)


def test_compatible_rewrite_preserves_nested_schema_and_array_prefix():
    original = {"quests": [{"name": "A", "steps": [1, 2]}], "enabled": True}
    assert compatible_rewrite(original, {"quests": [{"name": "B", "steps": [3, 4, 5]}], "enabled": False})
    assert not compatible_rewrite(original, {"quests": [], "enabled": True})
    assert not compatible_rewrite(original, {"quests": [{"name": "A", "steps": [1]}], "enabled": True})
    assert not compatible_rewrite(original, {"quests": [{"name": "A", "steps": [1, 2]}], "enabled": 1})
    assert not compatible_rewrite(original, {"quests": [{"name": "A"}], "enabled": True})


def test_incomplete_judgment_never_passes(monkeypatch):
    from routes import quality

    monkeypatch.setattr(quality, "_llm_in_thread", lambda *_: {"content": judgment(factors={"depth": 100})})
    result = asyncio.run(quality.audit_quality("narrative", '{"key":1}'))
    assert result["passed"] is False
    assert result["audit_complete"] is False
    assert result["score"] == 0
    assert result["source_sha256"] == source_digest('{"key":1}')


def test_oversized_source_never_reaches_judge(monkeypatch):
    from routes import quality

    def forbidden(*_):
        pytest.fail("over-budget content reached the model")

    monkeypatch.setattr(quality, "_llm_in_thread", forbidden)
    result = asyncio.run(quality.audit_quality("narrative", "x" * (MAX_ARTIFACT_CHARS + 1)))
    assert not result["passed"] and not result["audit_complete"]


def test_simulation_uses_exact_candidate_and_cannot_rescue_weak_factor(monkeypatch):
    from core import forge_validator
    from routes import quality

    entries = {key: 100 for key in FACTORS}
    entries["depth"] = 94
    monkeypatch.setattr(quality, "_llm_in_thread", lambda *_: {"content": judgment(factors=entries)})
    observed = []

    def simulate(kind, candidate):
        observed.append((kind, candidate))
        return {"sim_score": 100}

    monkeypatch.setattr(forge_validator, "simulation_metrics", simulate)
    source = '{"physics":{"solver":"new"}}'
    result = asyncio.run(quality.audit_quality("physics", source, simulate=True, artifact={"old": True}))
    assert observed == [("physics", {"physics": {"solver": "new"}})]
    assert result["source_sha256"] == source_digest(source)
    assert result["score"] == 94 and result["passed"] is False
    assert result["audit_complete"] is True


def test_required_simulation_failure_is_not_a_pass(monkeypatch):
    from core import forge_validator
    from routes import quality

    monkeypatch.setattr(quality, "_llm_in_thread", lambda *_: {"content": judgment(100)})

    def unavailable(*_):
        raise RuntimeError("test unavailable")

    monkeypatch.setattr(forge_validator, "simulation_metrics", unavailable)
    result = asyncio.run(quality.audit_quality("physics", '{"x":1}', simulate=True))
    assert not result["passed"] and not result["audit_complete"]


def test_polish_rejects_dropped_schema_then_accepts_exact_improvement(monkeypatch):
    from routes import quality, quality_polish

    sources = []
    rewrites = iter(['{"name":"improved"}', '{"name":"improved","steps":[1,2,3]}'])

    async def audit(kind, content, *, simulate=False):
        sources.append(content)
        score = 90 if len(sources) == 1 else 98
        return {"passed": score >= 95, "audit_complete": True, "score": score,
                "source_sha256": source_digest(content),
                "factors": {key: score for key in quality.QUALITY_FACTORS}, "feedback": "Improve"}

    monkeypatch.setattr(quality_polish, "audit_quality", audit)
    monkeypatch.setattr(quality_polish, "_llm_in_thread", lambda *_: {"content": next(rewrites)})
    result = asyncio.run(quality_polish.polish_pass("narrative", {"name": "old", "steps": [1, 2]}, max_passes=2))
    assert result["passed"] is True and result["score"] == 98
    assert result["source_sha256"] == source_digest(result["content"])
    assert len(sources) == 2 and result["passes"][1]["accepted"] is False
    assert result["passes"][2]["accepted"] is True


def test_uncertain_model_dispatch_is_propagated_without_retry(monkeypatch):
    from routes import quality_polish
    from routes.playable import PlayableModelFailure

    calls = []

    async def audit(kind, content, *, simulate=False):
        return {"passed": False, "score": 91, "audit_complete": True,
                "source_sha256": source_digest(content), "factors": {}, "feedback": "Improve"}

    def fail(*_):
        calls.append(True)
        raise PlayableModelFailure("project_model_execution_unconfirmed", unconfirmed=True)

    monkeypatch.setattr(quality_polish, "audit_quality", audit)
    monkeypatch.setattr(quality_polish, "_llm_in_thread", fail)
    with pytest.raises(PlayableModelFailure):
        asyncio.run(quality_polish.polish_pass("narrative", {"name": "old"}, max_passes=5))
    assert len(calls) == 1
