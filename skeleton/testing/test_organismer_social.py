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
    assert card["coverage_score"] >= 0
    assert card["coverage"]["pointers"] >= 16


def test_budget_choose_splits():
    from skeleton.organism.budget import choose, walk_limit
    tight = choose(0.80, stale_n=0, atoms=90, atom_cap=100)
    slack = choose(0.10, stale_n=0, atoms=10, atom_cap=100)
    assert tight["op"] == "consolidate"
    assert slack["op"] == "retain"
    assert walk_limit("tiny", 8) == 3
    assert walk_limit("max", 8) == 8
    assert tight["stored_prose"] == 0


def test_nucleus_bind_and_mhc(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.mhc import mhc_card
    from skeleton.organism.organismer import Organismer
    from skeleton.social.nucleus import bind_if_empty, wiki_urls
    from skeleton.social.seed import seed_field
    gxy = GalaxySystem()
    seed_field(gxy)
    assert wiki_urls(gxy.mesh)
    filled = bind_if_empty({"cards": []}, gxy.mesh)
    assert filled.get("cards")
    org = Organismer(root=tmp_path, persist=False, galaxy=gxy)
    card = mhc_card(org)
    assert card["kind"] == "mhc"
    assert card["stored_prose"] == 0


def test_walk_is_bounded(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.organismer import Organismer
    from skeleton.organism.runloop import walk
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = walk(org, persist=False, n=3)
    assert card["kind"] == "run"
    assert card["n"] <= 3
    assert card["limit"] == 3
    assert card["stored_prose"] == 0


def test_pulse_obeys_next(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.organismer import Organismer
    from skeleton.organism.pulse import pulse
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = pulse(org, persist=False)
    assert card["kind"] == "pulse"
    assert card["acted"]["code"] in {"tighten", "dream", "bind-source", "contact", "hold", "pulse"}
    assert card["stored_prose"] == 0
    again = pulse(org, persist=False, stimulus="plan tensor")
    assert again["kind"] == "pulse"


def test_ready_card_seeds_then_reports(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.organismer import Organismer
    from skeleton.organism.ready import ready_card
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = ready_card(org)
    assert card["kind"] == "ready"
    assert card["ok"] == 1
    assert card["seed"]["minted"] >= 1
    again = ready_card(org)
    assert again["seed"]["minted"] == 0
    assert card["stored_prose"] == 0


def test_seed_field_is_idempotent():
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.social.seed import seed_field
    gxy = GalaxySystem()
    a = seed_field(gxy)
    b = seed_field(gxy)
    assert a["minted"] >= 1
    assert b["minted"] == 0
    assert b["skipped"] >= a["minted"]
    assert a["stored_prose"] == 0


def test_next_hint_and_journal(tmp_path):
    from skeleton.organism.journal import append, tail
    from skeleton.organism.next import hint
    from skeleton.organism.organismer import Organismer
    org = Organismer(root=tmp_path, persist=False)
    card = hint(org)
    assert card["kind"] == "next"
    assert card["code"] in {"tighten", "dream", "bind-source", "contact", "hold", "pulse"}
    assert card["stored_prose"] == 0
    append({"step": 1, "G": 1.0, "decision": "new", "coverage": 0.2, "pressure": 0.1}, root=tmp_path)
    rows = tail(2, root=tmp_path)
    assert rows and rows[-1]["decision"] == "new"


def test_coverage_and_path10_and_freshness():
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.organismer import Organismer
    from skeleton.organism.path10 import path_card
    from skeleton.social.coverage import coverage_card
    cov = coverage_card("https://arxiv.org/abs/2608.26983")
    assert cov["kind"] == "field-coverage"
    assert cov["score"] > 0
    assert "arXiv" in cov["bound"]
    org = Organismer()
    p = path_card(org)
    assert p["target"] == 10.0
    assert p["gap"] >= 0
    gxy = GalaxySystem()
    gxy.pulse("index freshness topic")
    fresh = gxy.editor.freshness(max_age=10**12)
    assert fresh["kind"] == "editor-freshness"
    assert fresh["stored_prose"] == 0


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
    assert "GET /cortex/ready" in card["endpoints"]
    assert card.get("version")
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
    assert due(0, 0, cadence=4) is False
    assert due(4, 0, cadence=4) is True
    assert due(5, 4, cadence=4) is False
    assert due(8, 4, cadence=4) is True


def test_ccl_vault_roundtrip(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.galaxy.vault import dump, load
    gxy = GalaxySystem()
    gxy.pulse("plan tensor ttk lattice")
    card = dump(gxy.mesh, root=tmp_path)
    assert card["n"] >= 1
    rows = load(root=tmp_path)
    assert rows and "kind" in rows[0]
    assert card["stored_prose"] == 0


def test_prior_stays_cpu_without_mouth():
    from skeleton.galaxy.atoms import Atom
    from skeleton.galaxy.prior import blend
    atom = Atom.mint(kind="capture", tier="T0_FLASH", topic="plan tensor",
                     dialect="house:plan tensor", brain="memory", color="cyan")
    card = blend("plan tensor", [atom])
    assert card["prior"] == "cpu-jaccard"
    assert card["device"] == "cpu"
    assert card["stored_prose"] == 0


def test_caps_headroom_below_wall():
    from skeleton.organism.caps import compute
    tiny = compute(avail_mb=900, ram_mb=1024, cpus=2, gpu=False, headroom=0.62, tier="tiny")
    huge = compute(avail_mb=48000, ram_mb=65536, cpus=16, gpu=True, headroom=0.62, tier="max")
    assert tiny.atoms < huge.atoms
    assert tiny.rules < huge.rules
    assert tiny.growth_clip <= huge.growth_clip
    assert tiny.headroom <= 0.85
    assert huge.atoms <= 1800
    assert tiny.tier == "tiny"
    tight = compute(avail_mb=900, ram_mb=1024, cpus=2, gpu=False, headroom=0.62, tier="tiny", load=8.0)
    calm = compute(avail_mb=900, ram_mb=1024, cpus=2, gpu=False, headroom=0.62, tier="tiny", load=0.1)
    assert tight.pressure > calm.pressure
    assert tight.atoms <= calm.atoms


def test_health_ok_on_fresh_organism(tmp_path):
    from skeleton.organism.health import health_card
    from skeleton.organism.organismer import Organismer
    org = Organismer(root=tmp_path, persist=False)
    card = health_card(org)
    assert card["kind"] == "health"
    assert card["ok"] == 1
    assert card["stored_prose"] == 0
    assert card["kv_bound"] == 0


def test_lattice_and_unbound_kv():
    from skeleton.galaxy.kv import archive
    from skeleton.galaxy.lattice import card as lcard
    from skeleton.galaxy.system import GalaxySystem
    gxy = GalaxySystem()
    gxy.pulse("plan tensor ttk")
    lat = lcard(gxy.mesh)
    assert lat["kind"] == "lattice"
    assert "nucleus" in lat["ascii"]
    assert lat["stored_prose"] == 0
    kv = archive(gxy.mesh, neo=None)
    assert kv["bound"] == 0
    assert kv["n"] == 0


def test_caps_adapt_hysteresis():
    from skeleton.organism.caps import adapt, compute, reset_caps
    reset_caps()
    wide = compute(avail_mb=20000, ram_mb=32000, cpus=8, gpu=False, headroom=0.62, tier="large", load=0.2)
    adapt(probe=wide)
    thin = compute(avail_mb=800, ram_mb=32000, cpus=8, gpu=False, headroom=0.62, tier="tiny", load=6.0)
    card = adapt(probe=thin)
    assert card["action"] == "tighten"
    reset_caps()


def test_wiki_query_selects_principle():
    from skeleton.galaxy.query import run
    from skeleton.galaxy.system import GalaxySystem
    gxy = GalaxySystem()
    gxy.pulse("law like Elden Ring contact rule")
    card = run(gxy.mesh, "SELECT * WHERE kind=principle")
    assert card["kind"] == "wiki-query"
    assert card["stored_prose"] == 0


def test_banks_and_writeback_mark():
    from skeleton.galaxy.banks import card as bcard
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.writeback import absorb, should_suppress, topics
    gxy = GalaxySystem()
    gxy.pulse("law principle house contact mag")
    wb = absorb(gxy.mesh)
    assert wb["marked"] >= 1
    banks = bcard(gxy.mesh)
    assert banks["kind"] == "memory-banks"
    assert banks["stored_prose"] == 0
    held = topics(gxy.mesh)
    assert held
    assert should_suppress(next(iter(held)), held)
