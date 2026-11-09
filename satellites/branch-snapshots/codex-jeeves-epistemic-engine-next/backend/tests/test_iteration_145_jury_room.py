"""
Iteration 145 — Adversarial Jury Room adjudication pipeline.

Covers:
  • POST /submit (queued/duplicate)
  • POST /context-note (agent-to-agent)
  • POST /feed (universal drop-box)
  • POST /tick (ingest + adjudicate; strong → accepted, thin → rejected)
  • GET /verdicts (defense/prosecution/jury structure)
  • GET /status (numeric counters + roles + wiki_size)
  • WIKI GATE (accepted → in jeeves_knowledge; rejected → NOT)
  • GET /case/{id}
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
J = f"{BASE_URL}/api/gameforge/jury"
S = f"{BASE_URL}/api/gameforge/studio"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Basic /status ────────────────────────────────────────────────────────────
def test_status_active_and_shape(sess):
    r = sess.get(f"{J}/status", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["active"] is True
    for k in ("pending", "adjudicated", "accepted", "rejected", "revise", "wiki_size"):
        assert isinstance(d[k], int), f"{k} not int: {d[k]}"
    assert "accept_rate" in d
    assert d["roles"]["defense"] == "grader"
    assert d["roles"]["prosecution"] == "library"


# ── /submit new + duplicate ──────────────────────────────────────────────────
def test_submit_new_and_duplicate(sess):
    topic = f"TEST_iter145_topic_{uuid.uuid4().hex[:8]}"
    content = "TEST_iter145 baseline claim body for duplicate check."
    r1 = sess.post(f"{J}/submit", json={"topic": topic, "content": content, "source": "manual"}, timeout=30)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["ok"] is True and d1["queued"] is True and d1["duplicate"] is False
    assert d1["id"]

    r2 = sess.post(f"{J}/submit", json={"topic": topic, "content": content, "source": "manual"}, timeout=30)
    d2 = r2.json()
    assert d2["ok"] is True
    assert d2["queued"] is False and d2["duplicate"] is True


# ── /context-note ────────────────────────────────────────────────────────────
def test_context_note(sess):
    r = sess.post(f"{J}/context-note", json={
        "from_agent": "jeeves", "to_agent": "jury",
        "topic": f"TEST_iter145_ctx_{uuid.uuid4().hex[:6]}",
        "note": "TEST_iter145 agent-to-agent context note for jury pipeline."
    }, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["note"]["from"] == "jeeves" and d["note"]["to"] == "jury"


# ── /feed ────────────────────────────────────────────────────────────────────
def test_feed_dropbox(sess):
    r = sess.post(f"{J}/feed", json={
        "source": "mastermap",
        "topic": f"TEST_iter145_feed_{uuid.uuid4().hex[:6]}",
        "content": "TEST_iter145 universal drop-box candidate content."
    }, timeout=30)
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ── /tick strong claim → accepted, thin → rejected ───────────────────────────
def test_tick_strong_accepted_and_thin_rejected(sess):
    pre_status = sess.get(f"{J}/status?auto_tick=false", timeout=30).json()
    pytest._iter145_wiki_before = pre_status["wiki_size"]
    pytest._iter145_accepted_before = pre_status["accepted"]

    strong_topic = f"TEST_iter145_strong_{uuid.uuid4().hex[:8]}"
    strong_content = (
        f"{strong_topic}: This claim is supported by evidence and a verifiable source. "
        "Reference: http://example.com/study — the study data indicates a clear because-therefore "
        "chain of reasoning. Additional citation and reference materials support this substantive body "
        "with more than two hundred characters of detail and depth."
    )
    thin_topic = f"TEST_iter145_thin_{uuid.uuid4().hex[:8]}"
    thin_content = "maybe good"

    r_s = sess.post(f"{J}/submit", json={"topic": strong_topic, "content": strong_content, "source": "wikipedia"}, timeout=30)
    assert r_s.json()["queued"] is True
    strong_id = r_s.json()["id"]

    r_t = sess.post(f"{J}/submit", json={"topic": thin_topic, "content": thin_content, "source": "manual"}, timeout=30)
    assert r_t.json()["queued"] is True
    thin_id = r_t.json()["id"]

    tick = sess.post(f"{J}/tick", json={"max_items": 10}, timeout=45)
    assert tick.status_code == 200
    td = tick.json()
    assert td["ok"] is True
    assert "ingested" in td and "context" in td["ingested"] and "candidates" in td["ingested"]
    assert isinstance(td["processed"], list) and len(td["processed"]) >= 2
    for p in td["processed"]:
        assert "topic" in p and "verdict" in p and "scrutiny" in p

    # verify verdicts
    strong_case = sess.get(f"{J}/case/{strong_id}", timeout=30).json()
    thin_case = sess.get(f"{J}/case/{thin_id}", timeout=30).json()
    assert strong_case["ok"] is True
    assert thin_case["ok"] is True
    assert strong_case["case"]["verdict"] == "accepted", strong_case
    assert thin_case["case"]["verdict"] == "rejected", thin_case

    # save for wiki test
    pytest._iter145_strong_topic = strong_topic
    pytest._iter145_thin_topic = thin_topic


# ── /verdicts shape ──────────────────────────────────────────────────────────
def test_verdicts_shape(sess):
    r = sess.get(f"{J}/verdicts?limit=25", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and isinstance(d["verdicts"], list) and len(d["verdicts"]) > 0
    v = d["verdicts"][0]
    assert "defense" in v and "prosecution" in v and "jury" in v
    assert "pro_score" in v["defense"] and isinstance(v["defense"]["arguments"], list)
    assert "con_score" in v["prosecution"] and isinstance(v["prosecution"]["arguments"], list)
    assert "rubric" in v["jury"] and "scrutiny_score" in v["jury"] and v["jury"]["verdict"] in ("accepted", "revise", "rejected")


# ── WIKI GATE ────────────────────────────────────────────────────────────────
def test_wiki_gate(sess):
    strong_topic = getattr(pytest, "_iter145_strong_topic", None)
    thin_topic = getattr(pytest, "_iter145_thin_topic", None)
    assert strong_topic and thin_topic

    # Primary signal: wiki_size + accepted counters increased after adjudication.
    post_status = sess.get(f"{J}/status?auto_tick=false", timeout=30).json()
    wiki_before = getattr(pytest, "_iter145_wiki_before", 0)
    accepted_before = getattr(pytest, "_iter145_accepted_before", 0)
    assert post_status["wiki_size"] > wiki_before, f"wiki_size did not grow: {wiki_before} → {post_status['wiki_size']}"
    assert post_status["accepted"] > accepted_before

    # Secondary signal: /studio/jeeves/knowledge returns up to 60 rows. Since the
    # collection may contain many rows, we can't rely on the trimmed listing to
    # contain our fresh topic. But the rejected topic must NEVER appear.
    r = sess.get(f"{S}/jeeves/knowledge", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    kb = data.get("knowledge") or []
    topics_norm = {x.get("topic") for x in kb if isinstance(x, dict)}
    assert thin_topic not in topics_norm, "rejected topic must NOT appear in wiki"


# ── /case/{id} ───────────────────────────────────────────────────────────────
def test_case_detail(sess):
    r = sess.get(f"{J}/verdicts?limit=1", timeout=30).json()
    if not r["verdicts"]:
        pytest.skip("no verdicts yet")
    cid = r["verdicts"][0]["id"]
    d = sess.get(f"{J}/case/{cid}", timeout=30).json()
    assert d["ok"] is True and d["case"]["id"] == cid
    assert "defense" in d["case"] and "prosecution" in d["case"] and "jury" in d["case"]
