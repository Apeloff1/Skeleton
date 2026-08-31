"""Organismer 10x path + ArchiveX / social SOTA pointers."""
from __future__ import annotations

from skeleton.cortex.deck import CommandDeck
from skeleton.organism.organismer import Organismer, reset_organismer
from skeleton.social.archivex import parse_x_status, pointer
from skeleton.social.ingest import ingest
from skeleton.social.sota import sota_card
from skeleton.social.sources import catalog, classify
from skeleton.testing.test_cortex_deck import _Dummy


def test_classify_arxiv_and_xarchive():
    assert classify("https://arxiv.org/abs/2608.24876")["id"] == "arxiv"
    assert classify("https://xarchive.net/about")["id"] == "xarchive"
    assert classify("https://web.archive.org/web/2026/https://x.com/a/status/1")["id"] == "wayback"
    assert len(catalog()) >= 10


def test_archivex_status_pointer_stores_no_prose():
    raw = "see https://x.com/AleiahLock/status/2093311693010894922 on second brain"
    card = parse_x_status(raw)
    assert card is not None
    assert card["post_id"] == "2093311693010894922"
    assert "xarchive.net" in card["xarchive"]
    assert "web.archive.org" in card["cdx"]
    assert card["stored_prose"] == "0"
    p = pointer(raw)
    assert p["kind"] == "x-status"


def test_ingest_mixes_paper_and_post():
    stim = (
        "field https://arxiv.org/abs/2607.08716 and "
        "https://x.com/DhravyaShah/status/2035517012647272689"
    )
    card = ingest(stim)
    assert card["papers"] == 1
    assert card["x_posts"] == 1
    assert "arxiv" in card["houses"]
    assert "x-status" in card["houses"]
    assert card["stored_prose"] == 0


def test_sota_card_has_seeded_field_pointers():
    card = sota_card("https://arxiv.org/abs/2608.12428", G=1.4)
    assert card["kind"] == "social-sota"
    assert card["coverage"]["arxiv_seeded"] >= 6
    assert card["coverage"]["archive_seeded"] >= 2
    assert any("xarchive" in p["url"] for p in card["field_pointers"])
    assert card["stored_prose"] == 0
    assert card["toward_10x_pct"] > 0


def test_organismer_grows_but_does_not_overshoot():
    reset_organismer()
    org = Organismer()
    g0 = org.G
    card = org.step(
        "like Elden Ring https://arxiv.org/abs/2608.24876 https://x.com/a/status/1",
        neo=_Dummy(),
    )
    assert card["kind"] == "organismer"
    assert card["G"] >= g0
    assert card["G"] < 2.5
    assert card["toward_10x_pct"] < 20
    assert card["S"] >= 1.0
    assert card["social"]["papers"] == 1
    assert card["stored_prose"] == 0
    snap = org.snapshot()
    assert snap["target"] == 10.0


def test_deck_organismer_and_social():
    reset_organismer()
    deck = CommandDeck(_Dummy())
    soc = deck.social("https://xarchive.net/about")
    assert soc["bound_now"]["houses"]
    out = deck.organismer("plan tensor https://arxiv.org/abs/2509.24704")
    assert out["kind"] == "organismer"
    assert out["G"] >= 1.0
    assert out.get("write", {}).get("decision") in {"new", "update", "skip"}


def test_write_route_second_pulse_skips():
    from skeleton.organism.router import NEW, SKIP, route
    d1, _, _ = route("dual layer write routing CLS", [])
    assert d1 == NEW
    d2, score, _ = route("dual layer write routing CLS", ["dual layer write routing CLS"])
    assert d2 == SKIP
    assert score >= 0.72


def test_persist_and_ledger(tmp_path):
    from skeleton.galaxy.system import GalaxySystem, reset_galaxy
    from skeleton.organism.shelf import load
    reset_galaxy()
    org = Organismer(persist=True, root=tmp_path, galaxy=GalaxySystem())
    a = org.step("like Elden Ring https://arxiv.org/abs/2608.22215")
    assert a["write"]["decision"] == "new"
    assert a["ledger"]["sha"]
    b = org.step("like Elden Ring https://arxiv.org/abs/2608.22215")
    assert b["write"]["decision"] in {"skip", "update"}
    org2 = Organismer(persist=False, root=tmp_path)
    loaded = load(org2, root=tmp_path)
    assert loaded["loaded"] == 1
    assert org2.G >= 1.0


def test_product_card_shape():
    reset_organismer()
    deck = CommandDeck(_Dummy())
    card = deck.product()
    assert card["kind"] == "product"
    assert card["target"] == 10.0
    assert "GET /cortex/product" in card["endpoints"]
    assert any(p["topic"] == "mem0" for p in card["field"])
    assert card["stored_prose"] == 0
