"""
Session 22 (iteration 61) — Canon Graph + RAG memory + Multi-Agent GroupChat orchestrator.

Tests:
- /api/graph/{pid}              : typed nodes + inferred relationships
- /api/rag/{pid}/memory         : chunk store stats
- /api/rag/{pid}/retrieve       : top-k retrieval (scored, sorted desc)
- /api/groupchat/{pid}/run/async + /api/groupchat/job/{job_id} : pipeline auto-run

Game used: d02790d6d8174ff59bf7005221cd7609 (fully built).
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")

PID = "d02790d6d8174ff59bf7005221cd7609"
MISSING_PID = "ghost_game_does_not_exist_xyz_12345"

EXPECTED_NODE_TYPES = {"Faction", "Region", "Character", "Quest", "Creature", "Mechanic"}
EXPECTED_REL_TYPES = {"involves", "set_in", "concerns", "member_of", "controls", "from"}


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# -- Canon Graph -------------------------------------------------------------

class TestCanonGraph:
    def test_graph_ok(self, s):
        r = s.get(f"{BASE_URL}/api/graph/{PID}", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "error" not in d, d
        for k in ("node_count", "edge_count", "nodes", "edges", "by_type"):
            assert k in d, f"missing {k}"
        assert isinstance(d["nodes"], list) and len(d["nodes"]) > 0
        assert d["node_count"] == len(d["nodes"])
        assert d["edge_count"] == len(d["edges"])
        # main agent expects ~34 nodes, ~13 edges. Allow generous tolerance.
        assert d["node_count"] >= 20, f"unexpectedly low node_count={d['node_count']}"
        assert d["edge_count"] >= 5, f"unexpectedly low edge_count={d['edge_count']}"
        # Node shape
        for n in d["nodes"][:5]:
            for k in ("id", "type", "name", "text"):
                assert k in n
        # Edge shape
        for e in d["edges"][:5]:
            for k in ("source", "target", "rel"):
                assert k in e
        # Some expected node types present
        present_types = set(d["by_type"].keys())
        assert present_types & EXPECTED_NODE_TYPES, f"no expected node types in {present_types}"
        # Some expected relationship types present
        rel_types = {e["rel"] for e in d["edges"]}
        assert rel_types & EXPECTED_REL_TYPES, f"no expected rel types in {rel_types}"
        # Edge endpoints exist
        node_ids = {n["id"] for n in d["nodes"]}
        for e in d["edges"]:
            assert e["source"] in node_ids
            assert e["target"] in node_ids

    def test_graph_missing(self, s):
        r = s.get(f"{BASE_URL}/api/graph/{MISSING_PID}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("error") == "game not found", d


# -- RAG Memory --------------------------------------------------------------

class TestRagMemory:
    def test_memory_stats(self, s):
        r = s.get(f"{BASE_URL}/api/rag/{PID}/memory", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "chunks" in d and "by_type" in d and "indexed_artifacts" in d
        assert d["chunks"] > 0, "expected canon chunks"
        # main agent expects ~44 chunks
        assert d["chunks"] >= 20, f"unexpectedly low chunks={d['chunks']}"
        assert isinstance(d["by_type"], dict) and len(d["by_type"]) > 0
        assert isinstance(d["indexed_artifacts"], list) and len(d["indexed_artifacts"]) > 0

    def test_retrieve_relevant(self, s):
        # First pull a node name from the graph so we have a real canon term
        g = s.get(f"{BASE_URL}/api/graph/{PID}", timeout=30).json()
        candidate = None
        # prefer Faction → Quest → Character names
        for prefer in ("Faction", "Quest", "Character", "Region"):
            for n in g.get("nodes", []):
                if n.get("type") == prefer and n.get("name") and len(n["name"]) >= 4:
                    candidate = n["name"]
                    break
            if candidate:
                break
        assert candidate, "couldn't pick a query term from graph"
        r = s.get(f"{BASE_URL}/api/rag/{PID}/retrieve",
                  params={"q": candidate, "k": 3}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and "hits" in d
        assert d["count"] >= 1, f"no hits for '{candidate}': {d}"
        assert len(d["hits"]) <= 3
        # sorted by score desc
        scores = [h["score"] for h in d["hits"]]
        assert scores == sorted(scores, reverse=True), f"hits not sorted: {scores}"
        # each hit has expected shape
        for h in d["hits"]:
            for k in ("type", "name", "text", "score"):
                assert k in h
            assert isinstance(h["score"], (int, float))

    def test_retrieve_empty_query(self, s):
        r = s.get(f"{BASE_URL}/api/rag/{PID}/retrieve", params={"q": "", "k": 3}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("count", 0) == 0
        assert d.get("hits", []) == []

    def test_retrieve_irrelevant(self, s):
        r = s.get(f"{BASE_URL}/api/rag/{PID}/retrieve",
                  params={"q": "zzqqxxnotarealword99", "k": 3}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # irrelevant → 0 hits is valid
        assert d.get("count", 0) == 0


# -- GroupChat orchestrator --------------------------------------------------

class TestGroupChat:
    def test_run_only_missing_completes_fast(self, s):
        r = s.post(f"{BASE_URL}/api/groupchat/{PID}/run/async?only_missing=true",
                   timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "job_id" in d, d
        assert d.get("total") == 9
        job_id = d["job_id"]

        # Poll until done (fully built + only_missing → fast)
        last = None
        deadline = time.time() + 60
        while time.time() < deadline:
            jr = s.get(f"{BASE_URL}/api/groupchat/job/{job_id}", timeout=15)
            assert jr.status_code == 200
            last = jr.json()
            if last.get("job_status") == "done":
                break
            time.sleep(1.5)
        assert last and last.get("job_status") == "done", f"didn't finish: {last}"
        assert last.get("done") == 9, f"done!=9: {last.get('done')}"
        assert last.get("total") == 9

        transcript = last.get("transcript") or []
        assert isinstance(transcript, list) and len(transcript) > 0
        for m in transcript[:3]:
            for k in ("agent", "text", "kind", "at"):
                assert k in m, f"missing {k} in {m}"

        agents = {m["agent"] for m in transcript}
        kinds = {m["kind"] for m in transcript}
        # Orchestrator hands off / skips
        assert "Orchestrator" in agents
        assert {"handoff", "skip"} & kinds, f"no handoff/skip in {kinds}"

    def test_run_missing_game(self, s):
        r = s.post(f"{BASE_URL}/api/groupchat/{MISSING_PID}/run/async?only_missing=true",
                   timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("error") == "game not found", d

    def test_job_not_found(self, s):
        r = s.get(f"{BASE_URL}/api/groupchat/job/nonexistent_job_xyz", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("error") == "job not found", d
