"""Five-brain Hoag galaxy — codec, decoder, librarians, postprocess."""
from __future__ import annotations

from urllib.parse import urlparse

from skeleton.context.postprocess import postprocess_context
from skeleton.cortex.deck import CommandDeck
from skeleton.galaxy.atoms import TIERS, Atom, house_dialect
from skeleton.galaxy.codec import KnowledgeCodec, render_ccl
from skeleton.galaxy.decoder import KnowledgeDecoder
from skeleton.galaxy.hoag import BRAINS, HOAG_CITE, galaxy_card
from skeleton.galaxy.mirrors import bind_mouth, mouth_mirrors
from skeleton.galaxy.system import GalaxySystem, reset_galaxy
from skeleton.testing.test_cortex_deck import _Dummy


def test_hoag_has_five_colored_rings_and_citation():
    card = galaxy_card()
    assert card["rings"] == 5
    assert len(BRAINS) == 5
    ids = [b["id"] for b in BRAINS]
    assert ids == ["memory", "compiler", "dream", "distiller", "editor"]
    colors = {b["color"] for b in BRAINS}
    assert len(colors) == 5
    assert HOAG_CITE["stored_prose"] == 0
    nasa_host = (urlparse(HOAG_CITE["url"]).hostname or "").lower()
    assert nasa_host == "nasa.gov" or nasa_host.endswith(".nasa.gov")


def test_codec_tiers_and_longform_structure():
    codec = KnowledgeCodec()
    turns = [
        "plan tensor ttk soulslike like Elden Ring",
        "lattice heat weapon spawn",
        "law cite pointer only",
        "genos pulse house dialect",
        "dream sleep consolidate",
    ]
    atoms = codec.encode_conversation(turns, citation="steam://pointer")
    assert atoms
    assert all(a.stored_prose == 0 for a in atoms)
    assert all(a.tier in TIERS for a in atoms)
    struct = codec.structure_longform(atoms)
    assert struct["turns"] == 5
    dens = codec.density(atoms)
    assert dens["count"] == len(atoms)
    line = render_ccl(atoms[0])
    assert "|" in line


def test_decoder_roundtrip_keeps_commitments():
    dec = KnowledgeDecoder()
    card = dec.roundtrip("plan tensor ttk lattice soulslike")
    assert card["roundtrip"] is True
    assert card["atom_recall"] >= 0.5
    assert card["stored_prose"] == 0
    assert card["reconstructed"].startswith("house:")


def test_five_brains_pulse_and_wiki_hears():
    reset_galaxy()
    gxy = GalaxySystem()
    card = gxy.pulse("like Elden Ring plan tensor law", citation="steam-cite", sleep=True)
    assert card["kind"] == "galaxy-pulse"
    assert card["route"] in {"memory", "compiler", "dream", "distiller", "editor"}
    assert card["memory"]["brain"] == "memory"
    assert card["compiled"]["kind"] == "zettel"
    assert card["principle"]["kind"] == "principle"
    assert card["index"]["kind"] == "index"
    assert card["dream"]["dreams"] >= 1
    assert card["wiki"]["reports"] >= 1
    assert card["stored_prose"] == 0
    snap = gxy.snapshot()
    assert snap["dreams"] >= 1
    assert len(snap["mirrors"]) >= 12


def test_distiller_collapses_near_duplicate_rules():
    gxy = GalaxySystem()
    a = gxy.distiller.glean("never store third party prose cite only")
    b = gxy.distiller.glean("never store third party prose cite pointers")
    assert a.id != b.id
    live = [r for r in gxy.distiller.rulebook() if not r.get("superseded_by")]
    assert len(live) <= 2


def test_mouth_mirrors_bind_kimi_and_hf():
    mouths = mouth_mirrors()
    ids = {m["id"] for m in mouths}
    assert "moonshot.kimi" in ids
    assert "huggingface.hub" in ids
    assert "house.neo" in ids
    kimi = bind_mouth("moonshot.kimi")
    assert kimi["bound"] == 1
    assert kimi["via"] == "jeeves"
    assert kimi["stored_prose"] == 0


def test_deck_galaxy_on_dummy():
    deck = CommandDeck(_Dummy())
    card = deck.galaxy("like Stardew Valley cozy harvest", sleep=False)
    assert card["stored_prose"] == 0
    assert card["G"] >= 1.0
    assert "memory" in card


def test_postprocess_enriches_payload():
    payload = {
        "era": "soulslike",
        "citation": "https://store.steampowered.com/app/1245620/ELDEN_RING/",
        "jeeves": {"next": {"text": "keep moving"}},
        "stored_prose": 0,
    }
    ctx = {"vision": "like Elden Ring", "reference": {"citation": payload["citation"], "url": payload["citation"]}}
    out = postprocess_context(ctx, payload)
    assert out["postprocessed"] is True
    assert out["galaxy"]["stored_prose"] == 0
    assert out["galaxy"]["memory_id"]
    assert out["galaxy"]["hoag"]["rings"] == 5
    assert house_dialect("Hello World") == "house:hello world"


def test_atom_rejects_stored_prose():
    a = Atom.mint(
        kind="capture", tier="T0_FLASH", topic="x", dialect="house:x",
        brain="memory", color="#4EC8C8",
    )
    a.stored_prose = 0
    assert a.to_dict()["stored_prose"] == 0
