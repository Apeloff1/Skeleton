"""Phase-8 backend regression test.

Tests the 4 new extracted modules (quantum_compiler_svc, language_packs,
algorithms, expansion_packs) plus a regression sweep over the previously
verified Phase-7 surface.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import requests

BASE = "https://gemini-game-craft.preview.emergentagent.com/api"
TIMEOUT = 30

results: List[Tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    icon = "✅" if ok else "❌"
    print(f"{icon} {name} — {detail}")


def get(path: str, **kw) -> requests.Response:
    return requests.get(BASE + path, timeout=TIMEOUT, **kw)


def post(path: str, json_body: Any = None, **kw) -> requests.Response:
    return requests.post(BASE + path, json=json_body, timeout=TIMEOUT, **kw)


# =========================================================================
# 1. QuantumCompilerService extraction
# =========================================================================
print("\n=== 1. QuantumCompilerService /api/compiler/* ===")

try:
    r = get("/compiler/sanitizers")
    body = r.json() if r.ok else {}
    sans = body.get("sanitizers") or body.get("data") or []
    check("GET /compiler/sanitizers", r.status_code == 200 and len(sans) > 0,
          f"status={r.status_code} len={len(sans)}")
except Exception as e:
    check("GET /compiler/sanitizers", False, str(e))

try:
    r = get("/compiler/optimizers")
    body = r.json() if r.ok else {}
    opts = body.get("optimizers") or body.get("data") or []
    check("GET /compiler/optimizers", r.status_code == 200 and len(opts) > 0,
          f"status={r.status_code} len={len(opts)}")
except Exception as e:
    check("GET /compiler/optimizers", False, str(e))

try:
    payload = {"code": "x=1", "language": "python", "sanitizers": [],
               "optimizers": [], "target_arch": "x86_64",
               "optimization_level": "O2"}
    r = post("/compiler/compile", payload)
    check("POST /compiler/compile", r.status_code == 200,
          f"status={r.status_code} body={r.text[:120]}")
except Exception as e:
    check("POST /compiler/compile", False, str(e))

try:
    r = post("/compiler/analyze-structure",
             {"code": "def hello(): pass", "language": "python"})
    body = r.json() if r.ok else {}
    funcs = body.get("functions") or body.get("data", {}).get("functions") or []
    check("POST /compiler/analyze-structure",
          r.status_code == 200 and "hello" in funcs,
          f"status={r.status_code} functions={funcs}")
except Exception as e:
    check("POST /compiler/analyze-structure", False, str(e))

try:
    r = post("/compiler/generate-ir", {"code": "x=1", "language": "python"})
    body = r.json() if r.ok else {}
    ir = body.get("ir") or body.get("data", {}).get("ir")
    check("POST /compiler/generate-ir",
          r.status_code == 200 and ir is not None,
          f"status={r.status_code} ir_present={ir is not None}")
except Exception as e:
    check("POST /compiler/generate-ir", False, str(e))

try:
    r = post("/compiler/generate-assembly",
             {"code": "x=1", "language": "python"})
    body = r.json() if r.ok else {}
    asm = body.get("assembly") or body.get("data", {}).get("assembly")
    check("POST /compiler/generate-assembly",
          r.status_code == 200 and asm is not None,
          f"status={r.status_code} asm_present={asm is not None}")
except Exception as e:
    check("POST /compiler/generate-assembly", False, str(e))

# =========================================================================
# 2. LANGUAGE_PACK_REGISTRY
# =========================================================================
print("\n=== 2. LANGUAGE_PACK_REGISTRY /api/language-packs/* ===")

try:
    r = get("/language-packs")
    body = r.json() if r.ok else {}
    total = body.get("total")
    check("GET /language-packs", r.status_code == 200 and total == 40,
          f"status={r.status_code} total={total}")
except Exception as e:
    check("GET /language-packs", False, str(e))

try:
    r = get("/language-packs/systems")
    body = r.json() if r.ok else {}
    packs = body.get("packs") or []
    cnt = body.get("count", 0)
    check("GET /language-packs/systems",
          r.status_code == 200 and len(packs) > 0 and cnt > 0,
          f"status={r.status_code} packs={len(packs)} count={cnt}")
except Exception as e:
    check("GET /language-packs/systems", False, str(e))

try:
    r = get("/language-packs/functional")
    body = r.json() if r.ok else {}
    packs = body.get("packs") or []
    check("GET /language-packs/functional",
          r.status_code == 200 and len(packs) > 0,
          f"status={r.status_code} packs={len(packs)}")
except Exception as e:
    check("GET /language-packs/functional", False, str(e))

# =========================================================================
# 3. ALGORITHM_REGISTRY
# =========================================================================
print("\n=== 3. ALGORITHM_REGISTRY /api/algorithms/* ===")

try:
    r = get("/algorithms")
    body = r.json() if r.ok else {}
    cats = body.get("categories") or []
    check("GET /algorithms",
          r.status_code == 200 and len(cats) == 23,
          f"status={r.status_code} categories={len(cats)}")
except Exception as e:
    check("GET /algorithms", False, str(e))

try:
    r = get("/algorithms/parsing")
    body = r.json() if r.ok else {}
    algs = body.get("algorithms") or []
    check("GET /algorithms/parsing",
          r.status_code == 200 and len(algs) > 0,
          f"status={r.status_code} algorithms={len(algs)}")
except Exception as e:
    check("GET /algorithms/parsing", False, str(e))

# =========================================================================
# 4. EXPANSION_PACKS (with cross-module ALGORITHM_REGISTRY dep)
# =========================================================================
print("\n=== 4. EXPANSION_PACKS /api/expansions/* ===")

first_pack_id = None
try:
    r = get("/expansions")
    body = r.json() if r.ok else {}
    total = body.get("total")
    packs = body.get("packs") or body.get("expansions") or []
    if packs and isinstance(packs, list):
        first_pack_id = packs[0].get("id") or packs[0].get("pack_id")
    check("GET /expansions", r.status_code == 200 and total == 10,
          f"status={r.status_code} total={total} first_id={first_pack_id}")
except Exception as e:
    check("GET /expansions", False, str(e))

# Try GET on a single pack
try:
    sample_id = first_pack_id or "algorithms_pack"
    r = get(f"/expansions/{sample_id}")
    check(f"GET /expansions/{sample_id}", r.status_code == 200,
          f"status={r.status_code}")
except Exception as e:
    check("GET /expansions/<id>", False, str(e))

# POST install
try:
    sample_id = first_pack_id or "algorithms_pack"
    r = post(f"/expansions/{sample_id}/install", {})
    body = r.json() if r.ok else {}
    succ = body.get("success")
    check(f"POST /expansions/{sample_id}/install",
          r.status_code == 200 and succ is True,
          f"status={r.status_code} success={succ}")
except Exception as e:
    check("POST /expansions/<id>/install", False, str(e))

# =========================================================================
# 5. BACK-COMPAT SHIMS: /api/v9/info uses all 4 imports simultaneously
# =========================================================================
print("\n=== 5. Back-compat shims: /api/v9/info ===")

try:
    r = get("/v9/info")
    body = r.json() if r.ok else {}
    version = body.get("version")
    features = body.get("features") or []
    providers = body.get("llm_providers") or []
    lp = body.get("language_packs")
    algos = body.get("algorithms")
    eps = body.get("expansion_packs")
    ok = (r.status_code == 200 and version == "9.0.0"
          and len(features) > 0 and len(providers) > 0
          and lp == 40 and algos == 23 and eps == 10)
    check("GET /v9/info",
          ok,
          f"v={version} feat={len(features)} prov={len(providers)} lp={lp} algos={algos} eps={eps}")
except Exception as e:
    check("GET /v9/info", False, str(e))

try:
    r = get("/galaxy-studio/agent-db-manifest")
    check("GET /galaxy-studio/agent-db-manifest", r.status_code == 200,
          f"status={r.status_code}")
except Exception as e:
    check("GET /galaxy-studio/agent-db-manifest", False, str(e))

# =========================================================================
# 6. REGRESSION SUITE
# =========================================================================
print("\n=== 6. Regression suite ===")

try:
    r = get("/health")
    check("GET /health", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    check("GET /health", False, str(e))

try:
    r = get("/health/registry")
    body = r.json() if r.ok else {}
    ok_cnt = body.get("ok")
    skip = body.get("skipped")
    check("GET /health/registry",
          r.status_code == 200 and skip == 0,
          f"status={r.status_code} ok={ok_cnt} skipped={skip}")
except Exception as e:
    check("GET /health/registry", False, str(e))

try:
    r = get("/health/overview")
    body = r.json() if r.ok else {}
    ag = body.get("all_green")
    check("GET /health/overview",
          r.status_code == 200 and ag is True,
          f"status={r.status_code} all_green={ag}")
except Exception as e:
    check("GET /health/overview", False, str(e))

try:
    r = get("/health/redundancies")
    body = r.json() if r.ok else {}
    total = body.get("total")
    check("GET /health/redundancies",
          r.status_code == 200 and total == 42,
          f"status={r.status_code} total={total}")
except Exception as e:
    check("GET /health/redundancies", False, str(e))

# Galaxy Studio sub-routers
gs_endpoints = [
    "/galaxy-studio/eas/whoami",
    "/galaxy-studio/code-library/stats",
    "/galaxy-studio/watchdog/health",
    "/galaxy-studio/vault",
    "/galaxy-studio/flair/stats",
    "/galaxy-studio/ml-config/schema",
    "/galaxy-studio/mega-dbs/list",
    "/galaxy-studio/workers",
    "/galaxy-studio/admin-status",
    "/galaxy-studio/agent-db-manifest",
    "/galaxy-studio/domains",
]
for ep in gs_endpoints:
    try:
        r = get(ep)
        check(f"GET {ep}", r.status_code == 200,
              f"status={r.status_code}")
    except Exception as e:
        check(f"GET {ep}", False, str(e))

# intelligence_collab
for ep in ["/starlog/history", "/learning/predictions", "/collaboration/sessions"]:
    try:
        r = get(ep)
        check(f"GET {ep}", r.status_code == 200,
              f"status={r.status_code}")
    except Exception as e:
        check(f"GET {ep}", False, str(e))

try:
    r = get("/world-engine/genres")
    body = r.json() if r.ok else {}
    cnt = body.get("count", 0) or len(body.get("genres") or [])
    check("GET /world-engine/genres",
          r.status_code == 200 and cnt >= 5,
          f"status={r.status_code} count={cnt}")
except Exception as e:
    check("GET /world-engine/genres", False, str(e))

try:
    r = post("/benchmark/simulate", {})
    check("POST /benchmark/simulate",
          r.status_code in (200, 201),
          f"status={r.status_code}")
except Exception as e:
    check("POST /benchmark/simulate", False, str(e))

try:
    r = post("/verify/formal", {})
    check("POST /verify/formal",
          r.status_code in (200, 201),
          f"status={r.status_code}")
except Exception as e:
    check("POST /verify/formal", False, str(e))

try:
    r = post("/healing/organize", {"files": ["a.py", "b.js"]})
    check("POST /healing/organize",
          r.status_code == 200,
          f"status={r.status_code} body={r.text[:120]}")
except Exception as e:
    check("POST /healing/organize", False, str(e))

try:
    r = post("/healing/diagnose", {})
    check("POST /healing/diagnose",
          r.status_code in (200, 201),
          f"status={r.status_code}")
except Exception as e:
    check("POST /healing/diagnose", False, str(e))

try:
    r = get("/ai/hub/providers")
    body = r.json() if r.ok else {}
    provs = body.get("providers") or body.get("data") or []
    check("GET /ai/hub/providers",
          r.status_code == 200 and len(provs) >= 4,
          f"status={r.status_code} providers={len(provs)}")
except Exception as e:
    check("GET /ai/hub/providers", False, str(e))

try:
    r = post("/import/file",
             {"content": "x=1", "language": "python",
              "filename": "test.py"})
    check("POST /import/file",
          r.status_code in (200, 201),
          f"status={r.status_code}")
except Exception as e:
    check("POST /import/file", False, str(e))

try:
    r = post("/export/file",
             {"content": "x=1", "language": "python",
              "filename": "test.py"})
    check("POST /export/file",
          r.status_code in (200, 201),
          f"status={r.status_code}")
except Exception as e:
    check("POST /export/file", False, str(e))

try:
    r = get("/export/formats")
    check("GET /export/formats", r.status_code == 200,
          f"status={r.status_code}")
except Exception as e:
    check("GET /export/formats", False, str(e))

# =========================================================================
# Summary
# =========================================================================
print("\n" + "=" * 70)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"RESULT: {passed}/{total} passed")

failures = [(n, d) for n, ok, d in results if not ok]
if failures:
    print("\nFAILURES:")
    for n, d in failures:
        print(f"  ❌ {n}\n     {d}")

sys.exit(0 if passed == total else 1)
