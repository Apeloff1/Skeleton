"""Frozen reference provenance, finite context and category-only isolation."""
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import date
from hashlib import sha256
import inspect
import json
from urllib.parse import urlsplit

import pytest

from skeleton.eval import game_builder_reference_pack as references


def test_pack_records_exact_version_date_and_review_provenance():
    pack = references.load_reference_pack("godot46")
    metadata = pack.to_wire()
    assert metadata["id"] == "godot46-game-building-basics"
    assert metadata["version"] == "1" and metadata["engine_version"] == "4.6"
    assert date.fromisoformat(metadata["reviewed_at"]) == date(2026, 11, 13)
    assert metadata["scope"] == "code_debugging"
    assert metadata["trust"] == "untrusted-source-data"
    assert "agent-written" in metadata["summary_origin"]
    assert "no human signoff" in metadata["summary_origin"]


def test_all_ten_facts_are_cited_to_explicit_official_versioned_sources():
    pack = references.load_reference_pack("godot46")
    assert len(pack.facts) == 10
    assert len({fact.fact_id for fact in pack.facts}) == 10
    assert [fact.kind for fact in pack.facts].count("api") == 8
    assert [fact.kind for fact in pack.facts].count("derived_pattern") == 2
    for fact in pack.facts:
        assert fact.statement and fact.fact_id
        assert fact.source_urls and isinstance(fact.source_urls, tuple)
        for source in fact.source_urls:
            url = urlsplit(source)
            assert url.scheme == "https" and url.netloc == "docs.godotengine.org"
            assert url.path.startswith("/en/4.6/")
            assert not url.query and not url.username and not url.password
    assert len(pack.to_wire()["source_urls"]) == 8


def test_user_context_is_complete_finite_and_explicitly_untrusted():
    pack = references.load_reference_pack("godot46")
    context = pack.context_text
    encoded = context.encode("utf-8", errors="strict")
    assert 1200 <= len(encoded) <= 1500 <= references.MAX_CONTEXT_BYTES
    assert pack.to_wire()["context_bytes"] == len(encoded)
    assert context.startswith("[Untrusted source notes: Godot 4.6;")
    assert context.endswith("[End untrusted source notes]")
    assert context.count("\nAPI: ") == 8
    assert context.count("\nDERIVED PATTERN: ") == 2
    for fact in pack.facts:
        assert fact.statement in context
    # Source URLs are retained in provenance instead of taking prompt budget.
    assert "https://" not in context
    assert "```" not in context and "func " not in context


def test_category_selection_keeps_controls_unchanged_and_selected_context_identical():
    pack = references.load_reference_pack("godot46")
    assert references.SELECTED_CATEGORIES == ("gdscript", "debugging")
    assert pack.context_for_category("gdscript") == pack.context_text
    assert pack.context_for_category("debugging") == pack.context_text
    for category in ("design", "narrative", "grounding", "iteration", "requirements", "code", ""):
        assert not pack.applies_to(category)
        assert pack.context_for_category(category) == ""
    for invalid in (None, True, 1, [], {}):
        with pytest.raises(ValueError):
            pack.context_for_category(invalid)


def test_canonical_digest_binds_metadata_sources_fact_text_scope_and_rendered_bytes():
    pack = references.load_reference_pack("godot46")
    wire = pack.to_wire()
    claimed = wire.pop("digest")
    encoded = json.dumps(wire, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert claimed == pack.digest == sha256(encoded).hexdigest()
    assert references.load_reference_pack("godot46").to_wire() == pack.to_wire()
    changed_fact = replace(pack.facts[0], statement=pack.facts[0].statement + " Revised.")
    changed = references.ReferencePack((changed_fact, *pack.facts[1:]))
    assert changed.digest != pack.digest and changed.context_text != pack.context_text
    changed_source = replace(pack.facts[0], source_urls=(
        "https://docs.godotengine.org/en/4.6/classes/class_node.html",))
    changed = references.ReferencePack((changed_source, *pack.facts[1:]))
    assert changed.digest != pack.digest and changed.context_text == pack.context_text


def test_over_budget_context_is_rejected_whole_without_truncating_source_facts():
    pack = references.load_reference_pack("godot46")
    huge = replace(pack.facts[0], statement="x" * (references.MAX_CONTEXT_BYTES + 1))
    invalid = references.ReferencePack((huge, *pack.facts[1:]))
    with pytest.raises(ValueError, match="finite UTF-8 budget"):
        invalid.context_text
    with pytest.raises(ValueError):
        invalid.to_wire()
    assert references.load_reference_pack("godot46").context_text == pack.context_text


def test_frozen_records_and_returned_metadata_do_not_create_mutable_authority():
    pack = references.load_reference_pack("godot46")
    with pytest.raises(FrozenInstanceError):
        pack.facts = ()
    with pytest.raises(FrozenInstanceError):
        pack.facts[0].statement = "replacement"
    metadata = pack.to_wire()
    metadata["facts"][0]["statement"] = "changed outside the pack"
    metadata["categories"].append("grounding")
    assert pack.to_wire()["facts"][0]["statement"] == pack.facts[0].statement
    assert pack.to_wire()["categories"] == ["gdscript", "debugging"]


def test_reference_data_has_no_taskbank_scorer_answer_keys_or_external_runtime_imports():
    source = inspect.getsource(references)
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            imports.extend(item.name for item in node.names)
    assert set(imports) <= {"__future__", "dataclasses", "hashlib", "json"}
    for forbidden in ("TASKSET_ID", "SCORER_ID", "QualityCheck", '"task_id"', '"expected"',
                      "game_builder_quality", "subprocess", "urlopen", "requests."):
        assert forbidden not in source
    json.dumps(references.load_reference_pack("godot46").to_wire(), allow_nan=False)


@pytest.mark.parametrize("name,scope", [
    ("", "code_debugging"), ("latest", "code_debugging"), ("godot46", "all"),
    ("godot46", "grounding"), (None, "code_debugging"), ("godot46", None),
])
def test_unknown_pack_or_scope_never_broadens_context(name, scope):
    with pytest.raises(ValueError):
        references.load_reference_pack(name, scope=scope)
