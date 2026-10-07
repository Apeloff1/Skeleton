"""Cross-plane regression contracts for the F-15 structural audit.

These tests deliberately stay dependency-light: they exercise pure/local contracts
across organism budgeting/config auditing, social pointer ingest, and galaxy
atom/codec handling.
"""

from skeleton.galaxy.atoms import Atom
from skeleton.galaxy.codec import KnowledgeCodec, parse_ccl, render_ccl
from skeleton.organism.budget import CITE, choose
from skeleton.organism.config_diff import ConfigDiff
from skeleton.social.ingest import extract_urls, ingest


def test_organism_budget_thresholds_are_fail_closed():
    assert choose(0.6199)["op"] == "retain"
    assert choose(0.62)["op"] == "consolidate"
    assert choose(0.0, atoms=84, atom_cap=100)["op"] == "retain"
    assert choose(0.0, atoms=85, atom_cap=100)["op"] == "consolidate"
    assert choose(0.0, stale_n=4)["op"] == "consolidate"


def test_organism_budget_card_keeps_provenance_without_stored_prose():
    card = choose(0.1, stale_n=1, atoms=2, atom_cap=10)
    assert card["cite"] == CITE
    assert card["stored_prose"] == 0
    assert card["pressure"] == 0.1
    assert card["fill"] == 0.2


def test_organism_config_diff_redacts_secrets_nested_in_sequences():
    diff = ConfigDiff().diff(
        {"providers": [{"name": "primary", "token": "old-secret"}]},
        {"providers": [{"name": "primary", "token": "new-secret"}]},
    )
    assert diff["max_risk"] == "critical"
    assert diff["requires_review"] is True
    assert diff["total"] == 1
    assert diff["changes"][0]["path"] == "providers"
    assert diff["changes"][0]["risk"] == "critical"
    assert diff["changes"][0]["old"] is None
    assert diff["changes"][0]["new"] is None
    assert "old-secret" not in repr(diff)
    assert "new-secret" not in repr(diff)


def test_social_url_extraction_strips_sentence_punctuation():
    text = "Read https://openai.com/index/example., then https://arxiv.org/abs/2607.17545!"
    assert extract_urls(text) == [
        "https://openai.com/index/example",
        "https://arxiv.org/abs/2607.17545",
    ]


def test_social_ingest_exposes_house_names_and_source_ids_separately():
    card = ingest("See https://arxiv.org/abs/2607.17545.")
    assert card["urls"] == ["https://arxiv.org/abs/2607.17545"]
    assert card["houses"] == ["arXiv"]
    assert card["source_ids"] == ["arxiv"]
    assert card["cards"][0]["house"] == "arXiv"
    assert card["cards"][0]["source_id"] == "arxiv"
    assert card["papers"] == 1
    assert card["stored_prose"] == 0


def test_galaxy_atom_restore_preserves_explicit_zero_values():
    atom = Atom.from_dict(
        {
            "id": "zero-contract",
            "kind": "capture",
            "tier": "T0_FLASH",
            "topic": "zero values",
            "dialect": "house:zero values",
            "brain": "memory",
            "color": "blue",
            "confidence": 0.0,
            "risk": 0.0,
            "ts": 0.0,
        }
    )
    assert atom.confidence == 0.0
    assert atom.risk == 0.0
    assert atom.ts == 0.0


def test_galaxy_atom_dict_round_trip_keeps_contract_fields():
    original = Atom.mint(
        kind="principle",
        tier="T4_PRINCIPLE",
        topic="bounded context",
        dialect="house:bounded context",
        brain="distiller",
        color="gold",
        citation="https://example.invalid/cite",
        tags=("audit", "f15"),
        confidence=0.0,
        risk=0.25,
    )
    restored = Atom.from_dict(original.to_dict())
    assert restored.id == original.id
    assert restored.kind == original.kind
    assert restored.tier == original.tier
    assert restored.topic == original.topic
    assert restored.tags == original.tags
    assert restored.confidence == 0.0
    assert restored.risk == 0.25
    assert restored.stored_prose == 0


def test_galaxy_codec_profiles_and_ccl_are_stable():
    codec = KnowledgeCodec()
    tight = codec.mix("Alpha beta gamma", profile="tight")
    mobile = codec.mix("Alpha beta gamma", profile="mobile")
    desktop = codec.mix("Alpha beta gamma", profile="desktop")

    assert [atom.depth for atom in tight] == [0, 4]
    assert [atom.depth for atom in mobile] == [0, 2, 4]
    assert [atom.depth for atom in desktop] == [0, 1, 2, 3, 4, 5]

    parsed = parse_ccl(render_ccl(tight[0]))
    assert parsed["tier_digit"] == "0"
    assert parsed["kind"] == "capture"
    assert parsed["topic"] == tight[0].topic
    assert parsed["confidence"] == "0.62"
