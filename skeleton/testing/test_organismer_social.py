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
    assert a["galaxy"]["atom_ids"]
    from skeleton.galaxy.shelf import load as gload
    g2 = GalaxySystem()
    info = gload(g2, root=tmp_path)
    assert info["loaded"] == 1
    assert info["n"] >= 1
    assert len(g2.mesh.wiki.topics) >= 1


def test_cdx_probe_parses_rows_without_body():
    from skeleton.social.cdx import probe, reset_throttle
    reset_throttle()
    sample = '[["timestamp","original","statuscode","mimetype"],["20260830112233","https://x.com/a/status/1","200","text/html"]]'
    card = probe("https://x.com/a/status/1", live=True, opener=lambda url: sample)
    assert card["live"] == 1
    assert card["timestamp"] == "20260830112233"
    assert card["status"] == "200"
    assert card["stored_prose"] == 0
    again = probe("https://x.com/a/status/1", live=True, opener=lambda url: sample)
    assert again.get("reason") == "throttled"


def test_teacher_sync_fail_closed_and_glean():
    from skeleton.cortex.contact import ContactEngine
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.teachers import glean_rule, sync

    class _LM:
        lora = None

        def perplexity(self, texts):
            return 3.5

        def fit(self, texts, lr=0.05, schedule="cosine"):
            return 1

        def hidden(self, s):
            return [0.1] * 8

    class _Port:
        name = "huggingface"
        standin = _LM()

        def snapshot(self):
            return {"kind": "standin"}

    class _Neo(_Dummy):
        slots = {"hf": _Port()}

        def contact(self, slot, stimulus=""):
            self.contact_engine = getattr(self, "contact_engine", ContactEngine())
            return self.contact_engine.touch(self, slot, stimulus)

    card = sync(_Neo(), "plan tensor ttk")
    assert card["contacted"] == 1
    assert card["magnitude"] > 0
    rule = glean_rule(GalaxySystem(), stimulus="plan tensor ttk", contact=card)
    assert rule and rule["kind"] == "principle"
    assert rule["stored_prose"] == 0
    empty = sync(_Dummy(), "plan tensor ttk")
    assert empty["contacted"] == 0


def test_product_card_shape():
    reset_organismer()
    deck = CommandDeck(_Dummy())
    card = deck.product()
    assert card["kind"] == "product"
    assert card["target"] == 10.0
    assert "GET /cortex/product" in card["endpoints"]
    assert any(p["topic"] == "mem0" for p in card["field"])
    assert card["stored_prose"] == 0


def test_mad_kills_near_duplicate_principle():
    from skeleton.galaxy.atoms import Atom
    from skeleton.galaxy.mad import audit
    a = Atom.mint(kind="principle", tier="T4_PRINCIPLE", topic="contact rule mag house",
                  dialect="house:contact rule mag", brain="distiller", color="gold")
    b = Atom.mint(kind="principle", tier="T4_PRINCIPLE", topic="contact rule mag house",
                  dialect="house:contact rule mag", brain="distiller", color="gold")
    a.confidence = 0.9
    b.confidence = 0.4
    card = audit([a, b])
    assert card["killed"] >= 1
    assert a.superseded_by or b.superseded_by
    assert card["stored_prose"] == 0


def test_idle_due_cadence():
    from skeleton.organism.idle import due
    assert due(0, 0) is False
    assert due(4, 0) is True
    assert due(5, 4) is False
    assert due(8, 4) is True
