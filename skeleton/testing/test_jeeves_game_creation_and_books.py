"""Jeeves book-coverage, native questionnaire and authorized-creator contracts."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.training.jeeves_book_curriculum import (
    SCHEMA as BOOK_SCHEMA, compile_books, publish,
)
from skeleton.ai.training.jeeves_game_corpus import RIGHTS_SCHEMA
from skeleton.ai.training.jeeves_production_game_train import ProductionCheckpointError
from skeleton.jeeves.game_creation_dialogue import (
    FACETS, catalog, questionnaire, compose, register_dialogue_tools,
)
from skeleton.jeeves.agent.tools import ToolRegistry
from skeleton.jeeves.agent.types import RiskTier


def approved_book():
    rights = {"schema_version": RIGHTS_SCHEMA, "source_kind": "original_authoring",
              "rights_holder": "Original studio", "rights_basis": "Studio-authored original",
              "review_id": "human-review-2026", "training_permitted": True}
    return {"schema_version": BOOK_SCHEMA, "books": [
        {"book_id": "book-one", "title": "Original World Design",
         "rights": rights,
         "review": {"reviewer_id": "reviewer-one", "quality_approved": True,
                    "note": "I independently reviewed original source text and scope."},
         "chapters": [
             {"chapter_id": "chapter-one", "family": "world",
              "text": "An original world has connected, traversable regions. " * 30},
             {"chapter_id": "chapter-two", "family": "narrative",
              "text": "Original narrative scenes honor consequences and causality. " * 30},
         ]}
    ]}


def test_full_source_covered_gaplessly_and_hash_linked():
    source = approved_book()
    rows, proof = compile_books(source, 256)
    assert len(rows) == len(proof["segments"])
    assert proof["book_count"] == 1
    assert proof["chapter_count"] == 2
    assert proof["record_count"] == len(rows)
    for chapter in source["books"][0]["chapters"]:
        spans = [record for record in proof["segments"]
                 if record["chapter_id"] == chapter["chapter_id"]]
        assert spans[0]["start"] == 0
        assert spans[-1]["end"] == len(chapter["text"])
        assert "".join(chapter["text"][span["start"]:span["end"]]
                       for span in spans) == chapter["text"]
        assert all(span["chain_sha256"] for span in spans)
    assert proof["training_started"] is False
    assert proof["model_promoted"] is False


def test_unauthorized_and_unreviewed_books_rejected():
    invalid = approved_book()
    invalid["books"][0]["rights"]["training_permitted"] = False
    with pytest.raises(ProductionCheckpointError):
        compile_books(invalid)
    invalid = approved_book()
    invalid["books"][0]["review"]["quality_approved"] = False
    with pytest.raises(ProductionCheckpointError):
        compile_books(invalid)
    invalid = approved_book()
    invalid["books"][0]["chapters"].append({
        "chapter_id": "chapter-one", "family": "world", "text": "repeated" * 30})
    with pytest.raises(ProductionCheckpointError):
        compile_books(invalid)


def test_immutable_pinned_source_publish(tmp_path):
    raw = json.dumps(approved_book()).encode()
    source = tmp_path / "book_source.json"
    source.write_bytes(raw)
    intake = tmp_path / "intake.jsonl"
    coverage = tmp_path / "coverage.json"
    value = publish(source=source, expected_source_sha256=sha256(raw).hexdigest(),
                    intake=intake, coverage=coverage, segment_chars=256)
    assert sha256(intake.read_bytes()).hexdigest() == value["intake_sha256"]
    assert json.loads(coverage.read_text())["chain_sha256"] == value["chain_sha256"]
    assert value["training_started"] is False
    with pytest.raises(ProductionCheckpointError):
        publish(source=source, expected_source_sha256=sha256(raw).hexdigest(),
                intake=intake, coverage=coverage)


def test_30_native_facet_questions_and_compiler_no_execution():
    assert len(FACETS) == 30
    assert catalog()["count"] == 30
    assert questionnaire("world")["complete"] is False
    answers = {"intent": "Build an original island world",
               "constraints": "Continuity and traversal must be consistent",
               "variants": "Sky islands, valleys and secret routes"}
    assert questionnaire("world", answers)["complete"]
    flow = compose("my-game", {"world": answers})
    assert flow["dispatch_performed"] is False
    assert flow["plan"]["steps"][0]["command"]["operation"] == "create"
    assert flow["plan_sha256"] == flow["plan"]["plan_sha256"]
    with pytest.raises(ValueError):
        compose("my-game", {"world": {"intent": "Partial"}})
    with pytest.raises(ValueError):
        questionnaire("world", {"grant": "everything"})


def test_multimodal_provenance_required():
    answers = {"intent": "Design original 3D props",
               "constraints": "Rights reviewed and texture budget",
               "variants": "Multiple LODs and animations"}
    asset = {"modality": "image", "asset_sha256": "a" * 64,
             "source_id": "capture-001", "rights_review_id": "review-001"}
    assert compose("my-game", {"asset": answers}, [asset])["media_sha256"]
    with pytest.raises(ValueError):
        compose("my-game", {"asset": answers},
                [{**asset, "rights_review_id": ""}])


def test_host_model_tools_are_only_read_only():
    registry = ToolRegistry()
    tools = register_dialogue_tools(registry)
    assert len(tools) == 3
    assert all(registry.get(name).spec.risk is RiskTier.READ_ONLY for name in tools)
