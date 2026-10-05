"""
Iteration 62 — Session 23: Consistency Auditor (NEW), plus regression of
GET /api/graph/{pid} and GET /api/rag/{pid}/retrieve used by the canon-graph UI.

Game under test: d02790d6d8174ff59bf7005221cd7609 (fully-built canon).
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

PID = "d02790d6d8174ff59bf7005221cd7609"
MISSING_PID = "ffffffffffffffffffffffffffffffff"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- AUDIT (new) ----------
class TestConsistencyAudit:
    def test_audit_shape_and_score(self, s):
        r = s.get(f"{BASE_URL}/api/graph/{PID}/audit", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        # required fields
        for k in ("game_id", "score", "issue_count", "errors", "warnings", "issues"):
            assert k in j, f"missing {k}: {j}"
        assert j["game_id"] == PID
        assert isinstance(j["issues"], list)
        # numeric sanity
        assert 0 <= j["score"] <= 100
        assert j["errors"] >= 0 and j["warnings"] >= 0
        assert j["issue_count"] == len(j["issues"]) or j["issue_count"] >= len(j["issues"])  # capped at 40

        # Score formula sanity: 100 - errors*25 - warns*8 - infos*2 floored at 0
        infos = j["issue_count"] - j["errors"] - j["warnings"]
        if infos >= 0:
            expected = max(0, 100 - j["errors"] * 25 - j["warnings"] * 8 - infos * 2)
            assert j["score"] == expected, (j["score"], expected, j)

        # Expected for this fully-built game: 0 errors, ~5 warnings, score ~54
        assert j["errors"] == 0, f"expected 0 errors, got {j['errors']}: {j}"
        assert j["warnings"] >= 3, f"expected at least 3 warnings: {j}"
        # Sanity: should be in low-medium band given orphans + stale
        assert 30 <= j["score"] <= 80, f"score out of expected band: {j['score']}"

    def test_audit_issue_types(self, s):
        r = s.get(f"{BASE_URL}/api/graph/{PID}/audit", timeout=30)
        j = r.json()
        sevs = {i["severity"] for i in j["issues"]}
        types = {i["type"] for i in j["issues"]}
        # Valid severities only
        assert sevs.issubset({"error", "warn", "info"}), sevs
        # Each issue carries a message string
        for it in j["issues"]:
            assert isinstance(it.get("message"), str) and it["message"], it
        # For this fully-built game we expect at least one orphan
        # and (per problem statement) a 'stale' issue for build_manifest
        assert "orphan" in types, f"no orphan issues: {types}"
        stale_msgs = [i for i in j["issues"] if i["type"] == "stale"]
        # build_manifest should appear in a stale message
        if stale_msgs:
            assert any("build_manifest" in m["message"] for m in stale_msgs), stale_msgs

        # Orphan Faction expected
        orphan_factions = [i for i in j["issues"]
                           if i["type"] == "orphan" and "Faction" in i["message"]]
        assert orphan_factions, f"no Faction orphan in issues: {j['issues']}"

    def test_audit_missing_game(self, s):
        r = s.get(f"{BASE_URL}/api/graph/{MISSING_PID}/audit", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"error": "game not found"} or r.json().get("error") == "game not found"


# ---------- GRAPH regression ----------
class TestGraphRegression:
    def test_graph_basic(self, s):
        r = s.get(f"{BASE_URL}/api/graph/{PID}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["game_id"] == PID
        assert "nodes" in j and "edges" in j and "by_type" in j
        assert j["node_count"] == len(j["nodes"])
        assert j["edge_count"] == len(j["edges"])
        # Iteration 61 confirmed 34 / 13
        assert j["node_count"] == 34, f"expected 34 nodes, got {j['node_count']}"
        assert j["edge_count"] == 13, f"expected 13 edges, got {j['edge_count']}"
        # Sanity: by_type counts must sum to node_count
        assert sum(j["by_type"].values()) == j["node_count"]
        # Each node has id/type/name
        for n in j["nodes"][:5]:
            assert n["id"] and n["type"] and n["name"]


# ---------- RAG retrieve regression ----------
class TestRagRetrieve:
    def test_rag_empty_query(self, s):
        r = s.get(f"{BASE_URL}/api/rag/{PID}/retrieve", params={"q": "", "k": 6}, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert "hits" in j
        assert j["hits"] == [] or len(j["hits"]) == 0

    def test_rag_real_query(self, s):
        # Pull a real canon name from the graph to guarantee overlap
        g = s.get(f"{BASE_URL}/api/graph/{PID}", timeout=30).json()
        STOP = {"the", "a", "an", "of", "in", "on", "and", "or", "to", "for"}
        name = None
        for n in g["nodes"]:
            if n["type"] not in ("Faction", "Region", "Character"):
                continue
            for tok in n["name"].split():
                clean = "".join(c for c in tok if c.isalnum())
                if len(clean) >= 4 and clean.lower() not in STOP:
                    name = clean
                    break
            if name:
                break
        assert name, "no canon name found to query"
        r = s.get(f"{BASE_URL}/api/rag/{PID}/retrieve",
                  params={"q": name, "k": 6}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j.get("hits"), list)
        # We don't strictly require >0 (RAG is lexical), but a real entity
        # name should retrieve at least 1 hit.
        assert len(j["hits"]) >= 1, f"expected hits for '{name}': {j}"
        # Score-sorted desc
        scores = [h.get("score", 0) for h in j["hits"]]
        assert scores == sorted(scores, reverse=True), scores
        # Each hit has type/name/text/score
        h = j["hits"][0]
        for k in ("type", "name", "text", "score"):
            assert k in h, (k, h)
