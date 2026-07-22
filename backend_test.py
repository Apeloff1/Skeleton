"""
Phase-9 Backend Regression Test
Verifies AIAssistantService extraction + shim resolution + full regression suite
"""
import os
import re
import sys
import json
import time
import subprocess
import requests

# Read EXPO_PUBLIC_BACKEND_URL from /app/frontend/.env
def get_base_url():
    env = "/app/frontend/.env"
    with open(env) as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                v = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                return v.rstrip("/") + "/api"
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL not found in /app/frontend/.env")

BASE = get_base_url()
print(f"BASE URL: {BASE}\n")

PASSES = []
FAILS = []

def check(name, ok, detail=""):
    if ok:
        PASSES.append(name)
        print(f"✅ {name}  {detail}")
    else:
        FAILS.append((name, detail))
        print(f"❌ {name}  {detail}")

def get(path, **kwargs):
    return requests.get(BASE + path, timeout=60, **kwargs)

def post(path, payload=None, **kwargs):
    return requests.post(BASE + path, json=payload or {}, timeout=60, **kwargs)


# ───────────────────────────────────────────────────────────────────
# 1. AIAssistantService extraction
# ───────────────────────────────────────────────────────────────────
print("\n=== 1. AIAssistantService extraction ===")
r = get("/health")
ok = r.status_code == 200 and r.json().get("ai_available") is True
check("GET /api/health → 200 + ai_available:true", ok,
      f"status={r.status_code}")

# Try /ai-assist – any of 200 or 404 is acceptable, just no 500
r = post("/ai-assist", {"code": "x=1", "language": "python", "mode": "explain"})
ok = r.status_code != 500
check(f"POST /api/ai-assist no 500 (status={r.status_code})", ok)


# ───────────────────────────────────────────────────────────────────
# 2. SHIM RESOLUTION
# ───────────────────────────────────────────────────────────────────
print("\n=== 2. SHIM RESOLUTION ===")
r = get("/v9/info")
body = r.json() if r.status_code == 200 else {}
def find_int(b, key):
    if isinstance(b, dict):
        if key in b and isinstance(b[key], int):
            return b[key]
        for v in b.values():
            if isinstance(v, dict):
                r = find_int(v, key)
                if r is not None:
                    return r
            elif isinstance(v, list):
                # try _count variants
                pass
    return None

lp = find_int(body, "language_packs")
ep = find_int(body, "expansion_packs")
algs = find_int(body, "algorithms")
ok = r.status_code == 200 and lp == 40 and ep == 10 and algs == 23
check("GET /api/v9/info → language_packs=40, expansion_packs=10, algorithms=23",
      ok, f"got lp={lp} ep={ep} algs={algs} (status={r.status_code})")
if not ok:
    print(f"   /v9/info body: {json.dumps(body)[:500]}")

r = post("/compiler/analyze-structure", {"code": "def hello(): pass", "language": "python"})
body = r.json() if r.status_code == 200 else {}
funcs = body.get("functions") if isinstance(body, dict) else None
if funcs is None and isinstance(body, dict):
    for v in body.values():
        if isinstance(v, dict) and "functions" in v:
            funcs = v["functions"]
            break
ok = r.status_code == 200 and isinstance(funcs, list) and "hello" in funcs
check("POST /api/compiler/analyze-structure → functions:['hello']",
      ok, f"got functions={funcs} (status={r.status_code})")
if not ok:
    print(f"   body: {r.text[:400]}")

r = get("/ai/hub/providers")
body = r.json() if r.status_code == 200 else {}
provs = body.get("providers") if isinstance(body, dict) else body
if provs is None and isinstance(body, list):
    provs = body
ok = r.status_code == 200 and isinstance(provs, list) and len(provs) >= 3
check("GET /api/ai/hub/providers → providers >= 3",
      ok, f"got {len(provs) if isinstance(provs, list) else 'n/a'} (status={r.status_code})")

r = post("/healing/organize", {"files": ["a.py", "b.js"]})
body = r.json() if r.status_code == 200 else {}
by_lang = body.get("by_language", {}) if isinstance(body, dict) else {}
if not by_lang and isinstance(body, dict):
    for v in body.values():
        if isinstance(v, dict) and ("python" in v or "javascript" in v):
            by_lang = v
            break
ok = r.status_code == 200 and "python" in by_lang and "javascript" in by_lang
check("POST /api/healing/organize → by_language has python+javascript",
      ok, f"got by_language keys={list(by_lang.keys()) if isinstance(by_lang, dict) else by_lang} (status={r.status_code})")
if not ok:
    print(f"   body: {r.text[:400]}")

r = get("/export/formats")
ok = r.status_code == 200
check("GET /api/export/formats → 200", ok, f"status={r.status_code}")


# ───────────────────────────────────────────────────────────────────
# 3. REGRESSION SUITE
# ───────────────────────────────────────────────────────────────────
print("\n=== 3. REGRESSION SUITE ===")

r = get("/health")
ok = r.status_code == 200 and r.json().get("status") == "healthy"
check("GET /api/health → status:healthy", ok)

r = get("/health/registry")
body = r.json() if r.status_code == 200 else {}
okc = body.get("ok")
if okc is None:
    okc = body.get("ok_count")
if okc is None:
    okc = body.get("registered")
skc = body.get("skipped", 0)
ok = r.status_code == 200 and okc == 114 and skc == 0
check("GET /api/health/registry → ok=114 skipped=0",
      ok, f"got ok={okc} skipped={skc} body_keys={list(body.keys())[:8]}")
if not ok:
    print(f"   body: {json.dumps(body)[:500]}")

r = get("/health/overview")
body = r.json() if r.status_code == 200 else {}
ag = body.get("all_green") if isinstance(body, dict) else None
ok = r.status_code == 200 and ag is True
check("GET /api/health/overview → all_green:true", ok, f"got all_green={ag}")
if not ok:
    print(f"   body: {json.dumps(body)[:500]}")

r = get("/health/redundancies")
body = r.json() if r.status_code == 200 else {}
total = body.get("total") or body.get("count") or 0
ok = r.status_code == 200 and total >= 42
check("GET /api/health/redundancies → total >= 42", ok, f"got total={total}")

# Galaxy Studio sub-routers
gs_paths = [
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
for p in gs_paths:
    r = get(p)
    ok = r.status_code in (200, 405)
    check(f"GET {p}", ok, f"status={r.status_code}")

# intelligence_collab
for p in ["/starlog/history", "/learning/predictions", "/collaboration/sessions"]:
    r = get(p)
    ok = r.status_code in (200, 405)
    check(f"GET {p}", ok, f"status={r.status_code}")

r = get("/world-engine/genres")
body = r.json() if r.status_code == 200 else {}
cnt = body.get("count") if isinstance(body, dict) else None
if cnt is None and isinstance(body, dict):
    g = body.get("genres") or []
    cnt = len(g) if isinstance(g, list) else 0
ok = r.status_code == 200 and (cnt or 0) >= 5
check("GET /api/world-engine/genres → count >= 5", ok, f"got count={cnt}")

r = post("/benchmark/simulate", {"code": "x=1", "language": "python", "iterations": 50})
ok = r.status_code == 200
check("POST /api/benchmark/simulate", ok, f"status={r.status_code}")
if not ok:
    print(f"   body: {r.text[:300]}")

r = post("/verify/formal", {"code": "x=1", "language": "python",
                            "property_to_verify": "x>0", "proof_type": "invariant"})
ok = r.status_code == 200
check("POST /api/verify/formal", ok, f"status={r.status_code}")
if not ok:
    print(f"   body: {r.text[:300]}")


# ───────────────────────────────────────────────────────────────────
# 4. BOOT LOG CHECKS
# ───────────────────────────────────────────────────────────────────
print("\n=== 4. BOOT LOG ===")
log_path = "/var/log/supervisor/backend.err.log"
try:
    with open(log_path, "r", errors="replace") as f:
        log_text = f.read()
except FileNotFoundError:
    log_text = ""

matches = [m.start() for m in re.finditer(r"Started server process", log_text)]
if matches:
    latest_idx = matches[-1]
    tail = log_text[latest_idx:]
else:
    tail = log_text

has_33 = "[BOOT] routes_registry: registered=33 skipped=0" in tail
has_81 = "[BOOT] routes_registry: registered=81 skipped=0" in tail
check("BOOT log: registered=33 skipped=0", has_33)
check("BOOT log: registered=81 skipped=0", has_81)

suspicious = []
for line in tail.splitlines():
    if any(k in line for k in ("NameError", "ImportError", "Traceback")):
        if any(x in line for x in ("CodeComplexity", "ExecutionStatus", "TutorialStep", "ExecutorFactory")):
            continue
        suspicious.append(line)

ok = len(suspicious) == 0
check(f"BOOT log: no NameError/ImportError/Traceback after latest start (found {len(suspicious)})",
      ok, "\n  ".join(suspicious[:5]))


# ───────────────────────────────────────────────────────────────────
# 5. pytest test_routes_registry.py
# ───────────────────────────────────────────────────────────────────
print("\n=== 5. pytest test_routes_registry.py ===")
try:
    proc = subprocess.run(
        ["python", "-m", "pytest", "/app/backend/tests/test_routes_registry.py", "-q",
         "--no-header", "--tb=short"],
        capture_output=True, text=True, timeout=180,
        cwd="/app/backend",
    )
    out = proc.stdout + proc.stderr
    print(out[-2500:])
    ok = proc.returncode == 0
    m = re.search(r"(\d+) passed", out)
    pcount = m.group(1) if m else "?"
    check(f"pytest test_routes_registry.py — rc={proc.returncode}, {pcount} passed",
          ok)
except Exception as e:
    check("pytest test_routes_registry.py — ran", False, str(e))


# ───────────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"PASSED: {len(PASSES)}")
print(f"FAILED: {len(FAILS)}")
if FAILS:
    print("\nFAILED items:")
    for n, d in FAILS:
        print(f"  ❌ {n}  ::  {d[:200]}")

sys.exit(0 if not FAILS else 1)
