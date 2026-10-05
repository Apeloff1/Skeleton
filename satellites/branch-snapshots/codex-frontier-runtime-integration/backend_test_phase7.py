#!/usr/bin/env python3
"""
Phase 7 Agent Mesh verification tests.
Tests the new /api/galaxy-studio/swarm/mesh/* endpoints + regressions.
"""
import os
import sys
import json
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

results = []

def log(num, name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append((num, name, ok, detail))
    print(f"[{status}] {num}. {name} — {detail}")

def _get(url, **kw):
    return requests.get(url, timeout=60, **kw)

def _post(url, **kw):
    return requests.post(url, timeout=120, **kw)

# Prime cache / ensure built
print(f"== BASE: {BASE} ==")

# 1. POST /mesh/rebuild
try:
    r = _post(f"{API}/galaxy-studio/swarm/mesh/rebuild")
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    d = r.json()
    conds = [
        d.get("nodes") == 482,
        d.get("edges", 0) >= 4000,
        d.get("avg_degree", 0) >= 15,
        d.get("min_degree", 0) >= 5,
        d.get("max_degree", 0) <= 50,
        d.get("reachable_from_first_agent_within_5_hops") == 481,
    ]
    ok = all(conds)
    log(1, "POST /mesh/rebuild",
        ok,
        f"nodes={d.get('nodes')} edges={d.get('edges')} avg={d.get('avg_degree')} min={d.get('min_degree')} max={d.get('max_degree')} reach5={d.get('reachable_from_first_agent_within_5_hops')}")
    REBUILD_STATS = d
except Exception as e:
    log(1, "POST /mesh/rebuild", False, f"ERROR: {e}")
    REBUILD_STATS = {}

# 2. GET /mesh/stats - same shape & consistent
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/stats")
    assert r.status_code == 200
    d = r.json()
    consistent = (d.get("nodes") == REBUILD_STATS.get("nodes") and
                  d.get("edges") == REBUILD_STATS.get("edges") and
                  d.get("avg_degree") == REBUILD_STATS.get("avg_degree"))
    shape_ok = all(k in d for k in ["nodes","edges","avg_degree","min_degree","max_degree","reachable_from_first_agent_within_5_hops"])
    log(2, "GET /mesh/stats", shape_ok and consistent,
        f"consistent={consistent} nodes={d.get('nodes')} edges={d.get('edges')}")
except Exception as e:
    log(2, "GET /mesh/stats", False, f"ERROR: {e}")

# 3. GET /mesh/neighbors/A0001?k=8
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/neighbors/A0001", params={"k": 8})
    assert r.status_code == 200
    d = r.json()
    nb = d.get("neighbors", [])
    ok = (d.get("code") == "A0001" and d.get("count") == 8 and len(nb) == 8)
    if ok:
        for n in nb:
            if not all(k in n for k in ["code","agent","team_id","legion_id","weight"]):
                ok = False; break
            if not isinstance(n["weight"], (int, float)):
                ok = False; break
    log(3, "GET /mesh/neighbors/A0001?k=8", ok,
        f"count={d.get('count')} sample={nb[0] if nb else None}")
except Exception as e:
    log(3, "GET /mesh/neighbors/A0001?k=8", False, f"ERROR: {e}")

# 4. GET /mesh/neighbors/A0300?k=5
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/neighbors/A0300", params={"k": 5})
    assert r.status_code == 200
    d = r.json()
    ok = d.get("code") == "A0300" and d.get("count", 0) >= 1 and len(d.get("neighbors", [])) >= 1
    log(4, "GET /mesh/neighbors/A0300?k=5", ok, f"count={d.get('count')}")
except Exception as e:
    log(4, "GET /mesh/neighbors/A0300?k=5", False, f"ERROR: {e}")

# 5. /mesh/reach/A0001?depth=2 — coverage_pct >= 25
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/reach/A0001", params={"depth": 2})
    assert r.status_code == 200
    d = r.json()
    cov = d.get("coverage_pct", 0)
    log(5, "GET /mesh/reach/A0001?depth=2", cov >= 25, f"coverage_pct={cov}")
except Exception as e:
    log(5, "GET /mesh/reach/A0001?depth=2", False, f"ERROR: {e}")

# 6. depth=3 >= 85
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/reach/A0001", params={"depth": 3})
    d = r.json()
    cov = d.get("coverage_pct", 0)
    log(6, "GET /mesh/reach/A0001?depth=3", cov >= 85, f"coverage_pct={cov}")
except Exception as e:
    log(6, "GET /mesh/reach/A0001?depth=3", False, f"ERROR: {e}")

# 7. depth=4 == 100.0
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/reach/A0001", params={"depth": 4})
    d = r.json()
    cov = d.get("coverage_pct", 0)
    total = d.get("total_reached", 0)
    log(7, "GET /mesh/reach/A0001?depth=4", cov == 100.0 and total == 481,
        f"coverage_pct={cov} total_reached={total}")
except Exception as e:
    log(7, "GET /mesh/reach/A0001?depth=4", False, f"ERROR: {e}")

# 8. /mesh/path/A0001/A0480
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/path/A0001/A0480")
    d = r.json()
    pd = d.get("path_details") or []
    ok = d.get("found") is True and d.get("hops", 99) <= 4 and len(pd) > 0
    if ok:
        for step in pd:
            if not all(k in step for k in ["code","agent","team_id","legion_id"]):
                ok = False; break
    log(8, "GET /mesh/path/A0001/A0480", ok,
        f"found={d.get('found')} hops={d.get('hops')} steps={len(pd)}")
except Exception as e:
    log(8, "GET /mesh/path/A0001/A0480", False, f"ERROR: {e}")

# 9. /mesh/path/A0200/A0100
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/path/A0200/A0100")
    d = r.json()
    ok = d.get("found") is True and d.get("hops", 99) <= 5
    log(9, "GET /mesh/path/A0200/A0100", ok,
        f"found={d.get('found')} hops={d.get('hops')}")
except Exception as e:
    log(9, "GET /mesh/path/A0200/A0100", False, f"ERROR: {e}")

# 10. /mesh/path/A0001/A0001 - {found=true, hops=0, path=["A0001"]}
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/path/A0001/A0001")
    d = r.json()
    ok = d.get("found") is True and d.get("hops") == 0 and d.get("path") == ["A0001"]
    log(10, "GET /mesh/path/A0001/A0001", ok,
        f"found={d.get('found')} hops={d.get('hops')} path={d.get('path')}")
except Exception as e:
    log(10, "GET /mesh/path/A0001/A0001", False, f"ERROR: {e}")

# 11. /mesh/path/A0001/A9999 - {found=false}
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/path/A0001/A9999")
    d = r.json()
    ok = d.get("found") is False
    log(11, "GET /mesh/path/A0001/A9999", ok, f"found={d.get('found')}")
except Exception as e:
    log(11, "GET /mesh/path/A0001/A9999", False, f"ERROR: {e}")

# 12. /mesh/hubs?top=5
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/hubs", params={"top": 5})
    d = r.json()
    hubs = d.get("hubs", [])
    ok = d.get("top") == 5 and len(hubs) == 5
    if ok:
        for h in hubs:
            if not all(k in h for k in ["code","agent","team_id","legion_id","degree"]):
                ok = False; break
            if not isinstance(h["degree"], int) or h["degree"] < 15:
                ok = False; break
    log(12, "GET /mesh/hubs?top=5", ok,
        f"degrees={[h.get('degree') for h in hubs]}")
except Exception as e:
    log(12, "GET /mesh/hubs?top=5", False, f"ERROR: {e}")

# 13. /mesh/reach/A9999?depth=2 - graceful
try:
    r = _get(f"{API}/galaxy-studio/swarm/mesh/reach/A9999", params={"depth": 2})
    d = r.json()
    ok = d.get("total_reached") == 0 and d.get("layers") == []
    log(13, "GET /mesh/reach/A9999?depth=2 (unknown)", ok,
        f"total_reached={d.get('total_reached')} layers={d.get('layers')}")
except Exception as e:
    log(13, "GET /mesh/reach/A9999?depth=2 (unknown)", False, f"ERROR: {e}")

# 14. After rebuild, agent/by-number/1 must include neighbors_codes and degree
try:
    r2 = _post(f"{API}/galaxy-studio/swarm/mesh/rebuild")
    assert r2.status_code == 200
    r = _get(f"{API}/galaxy-studio/swarm/agents/by-number/1")
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    d = r.json()
    agent = d.get("agent") or d
    nc = agent.get("neighbors_codes")
    deg = agent.get("degree")
    ok = isinstance(nc, list) and len(nc) >= 8 and isinstance(deg, int)
    log(14, "agents/by-number/1 has neighbors_codes+degree", ok,
        f"neighbors_codes(len)={len(nc) if isinstance(nc, list) else 'N/A'} degree={deg}")
except Exception as e:
    log(14, "agents/by-number/1 has neighbors_codes+degree", False, f"ERROR: {e}")

# 15. Regression: capabilities/roster/coverage
try:
    r = _get(f"{API}/galaxy-studio/swarm/capabilities/roster/coverage")
    assert r.status_code == 200
    d = r.json()
    ok = d.get("total_agents") == 482 and d.get("coverage_pct") == 100
    log(15, "capabilities/roster/coverage (regression)", ok,
        f"total_agents={d.get('total_agents')} coverage_pct={d.get('coverage_pct')}")
except Exception as e:
    log(15, "capabilities/roster/coverage (regression)", False, f"ERROR: {e}")

# 16. Regression: census - total_agents>=480
try:
    r = _get(f"{API}/galaxy-studio/swarm/census")
    assert r.status_code == 200
    d = r.json()
    ok = d.get("total_agents", 0) >= 480
    log(16, "swarm/census (regression)", ok, f"total_agents={d.get('total_agents')}")
except Exception as e:
    log(16, "swarm/census (regression)", False, f"ERROR: {e}")

# Summary
passed = sum(1 for _, _, ok, _ in results if ok)
total = len(results)
print(f"\n== SUMMARY: {passed}/{total} passed ==")
for num, name, ok, detail in results:
    print(f"  {'✅' if ok else '❌'} {num}. {name} — {detail}")

sys.exit(0 if passed == total else 1)
