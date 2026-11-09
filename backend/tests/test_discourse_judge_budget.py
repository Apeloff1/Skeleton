"""Bounded deterministic multi-model judge context and exact execution admission.

The canonical LLM router rejects >40,000-character prompts. A 20k-character
brief plus five 5k candidate excerpts and critiques used to exceed that bound.
These tests prove the source brief is never silently dropped and all admitted
models remain represented in the judge evidence.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core.discourse_catalog import DeclaredModel, DeclaredPanel
from routes import discourse


ALICE = {"tenant_id": "tenant-budget", "owner_id": "alice@example.test"}


def _candidates(n=5, *, content_size=12_000, critique_size=2_000):
    return [
        {"model": "local:model-" + str(i),
         "content": ("draft" + str(i)) * (content_size // 6),
         "critique": "C" * critique_size}
        for i in range(n)
    ]


def test_long_full_brief_and_five_long_candidates_fit_router_budget():
    prompt = "A" * discourse.MAX_PROMPT_CHARS
    candidates = _candidates(5)
    result = discourse._judge_prompt(prompt, candidates)
    assert result.startswith("BRIEF:\n" + prompt + "\n\nCANDIDATES:\n")
    assert len(result) <= discourse.MAX_JUDGE_PROMPT_CHARS <= 40_000
    for index, item in enumerate(candidates):
        marker = "[CANDIDATE " + str(index) + "] (model=" + item["model"] + ")"
        assert result.count(marker) == 1
        assert "draft" + str(index) in result
    assert result.index("[CANDIDATE 0]") < result.index("[CANDIDATE 4]")


def test_budget_keeps_content_and_critique_with_short_brief():
    candidates = _candidates(3, content_size=900, critique_size=100)
    output = discourse._judge_prompt("Create an original game", candidates)
    for item in candidates:
        assert item["content"] in output
        assert item["critique"] in output
    assert output.count("\nCRITIQUE: ") == 3


def test_proportional_budget_is_stable_and_does_not_mutate_candidates():
    records = _candidates()
    before = [dict(record) for record in records]
    first = discourse._judge_prompt("B" * 20_000, records)
    second = discourse._judge_prompt("B" * 20_000, records)
    assert first == second
    assert records == before


@pytest.mark.parametrize("invalid", [
    None, [], [None], [1],
    [{"model": "bad", "content": 34}],
    [{"model": "", "content": "candidate"}],
    [{"model": "bad", "content": " "}],
    [{"model": "bad", "content": "candidate", "critique": {}}],
    _candidates(6),
])
def test_untrusted_candidate_shapes_rejected(invalid):
    with pytest.raises(ValueError):
        discourse._judge_prompt("Create original game", invalid)


def test_unavailable_budget_fails_before_provider_spend(monkeypatch):
    monkeypatch.setattr(discourse, "MAX_JUDGE_PROMPT_CHARS", 128)
    with pytest.raises(ValueError, match="insufficient"):
        discourse._judge_prompt("Create an original game", _candidates(5))


def test_bad_prompt_length_rejected_before_judge_composition():
    for prompt in ("", "abc", "x" * 20_001):
        with pytest.raises(ValueError, match="invalid judge"):
            discourse._judge_prompt(prompt, _candidates(2))


def test_actual_five_model_execution_builds_bounded_judge_prompt(monkeypatch):
    models = tuple(
        DeclaredModel(f"local:mod-{i}", "local", f"mod-{i}", i == 0)
        for i in range(5)
    )
    judge = DeclaredModel("local:judge", "local", "judge", False)
    panel = DeclaredPanel(models=models, judge=judge, mode="multiple_models_one_provider",
                          provider_diverse=False, independent_judge=True)
    called = []
    records = []

    async def resolve(**_kwargs):
        return panel

    async def complete(task, text, system="", **options):
        called.append((options["model_id"], len(text), text))
        if options["model_id"] == "judge":
            assert text.startswith("BRIEF:\n" + "U" * 20_000)
            assert len(text) <= 39_200
            return {"content": '{"scores":[' + ",".join(
                '{"index":' + str(i) + ',"quality":80,"fidelity":90}'
                for i in range(5)
            ) + '],"winner_index":2}'}
        return {"content": "E" * 12_000}

    class Collection:
        async def insert_one(self, record):
            records.append(record)
            return SimpleNamespace(acknowledged=True)

    monkeypatch.setattr(discourse, "tenant_panel", resolve)
    monkeypatch.setattr(discourse, "route_complete", complete)
    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_log=Collection()))
    result = asyncio.run(discourse.deliberate(
        "creative", "U" * 20_000, do_discord=False, identity=ALICE,
    ))
    assert result.get("error") is None
    assert result["winner_index"] == 2
    assert result["persistence_status"] == "durable"
    assert result["deliberation_mode"] == "multiple_models_one_provider"
    assert len(called) == 6
    assert len(records) == 1
    assert records[0]["tenant_id"] == "tenant-budget"
