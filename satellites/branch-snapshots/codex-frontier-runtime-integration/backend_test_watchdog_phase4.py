"""
Phase-4 Galaxy Studio watchdog cluster extraction — final regression suite.

Verifies:
  1) New sub-router endpoints respond on UNCHANGED public paths.
  2) SSOT preserved between parent module and sub-router (_builds shared).
  3) No regression on Phase-2 (EAS) + Phase-3 (code-library) sub-routers.
  4) Health stack invariants.
  5) Boot log + routes_registry counts unchanged.
  6) test_routes_registry.py pytest still passes (113 tests).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import requests

# ── Resolve base URL exactly as spec ───────────────────────────────────
def _resolve_base() -> str:
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
                _, _, v = line.partition("=")
                return v.strip().strip('"').rstrip("/") + "/api"
    return "http://localhost:8001/api"


BASE = _resolve_base()
print(f"\n[BASE] {BASE}\n")
SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    icon = PASS if ok else FAIL
    print(f"{icon} {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok, detail))


def get(path: str, **kw):
    return SESSION.get(BASE + path, timeout=kw.pop("timeout", 30), **kw)


def post(path: str, **kw):
    return SESSION.post(BASE + path, timeout=kw.pop("timeout", 30), **kw)


# ═════════════════════════════════════════════════════════════════════
# Section 1 — New watchdog sub-router endpoints (public path invariance)
# ═════════════════════════════════════════════════════════════════════
print("─── Section 1 — Watchdog sub-router on UNCHANGED public paths ───")

# 1A. watchdog/health
r = get("/galaxy-studio/watchdog/health")
ok = r.status_code == 200
detail = f"HTTP {r.status_code}"
body = {}
if ok:
    try:
        body = r.json()
        has_active = "active_runners" in body and isinstance(body["active_runners"], list)
        has_imb = "in_memory_builds" in body and isinstance(body["in_memory_builds"], int)
        ok = has_active and has_imb
        detail = (f"keys=active_runners({type(body.get('active_runners')).__name__})"
                  f", in_memory_builds={body.get('in_memory_builds')}")
    except Exception as e:
        ok = False
        detail = f"json parse fail: {e}"
record("GET /galaxy-studio/watchdog/health → 200 + required keys", ok, detail)
INITIAL_BUILDS = body.get("in_memory_builds", 0) if isinstance(body, dict) else 0

# 1B. diagnose nonexistent
r = get("/galaxy-studio/diagnose/nonexistent-test-id-zzz999")
ok = r.status_code == 200
detail = f"HTTP {r.status_code}"
if ok:
    try:
        body = r.json()
        expected = {
            "ok": False, "reason": "not_found",
            "in_memory": False, "in_mongo": False, "active_runner": False,
        }
        ok = all(body.get(k) == v for k, v in expected.items())
        detail = f"body={ {k: body.get(k) for k in expected} }"
    except Exception as e:
        ok = False
        detail = f"json: {e}"
record("GET /galaxy-studio/diagnose/<nonexistent> → 200 ok=false not_found", ok, detail)

# 1C. resurrect nonexistent → 404
r = post("/galaxy-studio/resurrect/nonexistent-test-id-zzz999")
ok = r.status_code == 404
record("POST /galaxy-studio/resurrect/<nonexistent> → 404", ok, f"HTTP {r.status_code}")

# 1D. force-advance nonexistent → 404
r = post("/galaxy-studio/force-advance/nonexistent-test-id-zzz999")
ok = r.status_code == 404
record("POST /galaxy-studio/force-advance/<nonexistent> → 404", ok, f"HTTP {r.status_code}")

# ═════════════════════════════════════════════════════════════════════
# Section 2 — SSOT preserved (start a build, diagnose, watchdog count++)
# ═════════════════════════════════════════════════════════════════════
print("\n─── Section 2 — SSOT (parent _builds shared with sub-router) ───")

# Try multiple known build-start endpoints (galaxy_studio uses /create)
build_id = None
create_payload = {"title": "WatchdogPhase4Test", "genre": "rpg", "art_style": "pixel"}
r = post("/galaxy-studio/create", json=create_payload)
if r.status_code == 200:
    try:
        body = r.json()
        build_id = body.get("build_id") or body.get("id")
    except Exception:
        pass

if not build_id:
    # Try start-build per the review request hint
    r = post("/galaxy-studio/start-build", json=create_payload)
    if r.status_code == 200:
        try:
            body = r.json()
            build_id = body.get("build_id") or body.get("id")
        except Exception:
            pass

if not build_id:
    record("POST /galaxy-studio/create → build_id", False, f"could not create build; last HTTP {r.status_code}")
else:
    record("POST /galaxy-studio/create → build_id", True, f"build_id={build_id[:16]}")

    # Give the runner a moment to register itself
    time.sleep(1.5)

    # 2A. diagnose returns in_memory=true
    r = get(f"/galaxy-studio/diagnose/{build_id}")
    ok = r.status_code == 200
    detail = f"HTTP {r.status_code}"
    if ok:
        try:
            body = r.json()
            ok = body.get("ok") is True and body.get("in_memory") is True
            detail = (f"ok={body.get('ok')}, in_memory={body.get('in_memory')}, "
                      f"active_runner={body.get('active_runner')}")
        except Exception as e:
            ok = False
            detail = f"json: {e}"
    record("GET /galaxy-studio/diagnose/<live-build> → in_memory=true", ok, detail)

    # 2B. watchdog/health in_memory_builds should be > initial
    r = get("/galaxy-studio/watchdog/health")
    ok = r.status_code == 200
    detail = f"HTTP {r.status_code}"
    if ok:
        try:
            body = r.json()
            new_count = body.get("in_memory_builds", 0)
            # SSOT: must have grown (or equal if other tests left builds behind)
            ok = new_count > INITIAL_BUILDS
            detail = f"initial={INITIAL_BUILDS} → new={new_count}"
        except Exception as e:
            ok = False
            detail = f"json: {e}"
    record("GET /galaxy-studio/watchdog/health — in_memory_builds increased", ok, detail)

# ═════════════════════════════════════════════════════════════════════
# Section 3 — No regression on Phase-2 + Phase-3 sub-routers
# ═════════════════════════════════════════════════════════════════════
print("\n─── Section 3 — Phase-2 (EAS) + Phase-3 (code-library) regression ───")

r = get("/galaxy-studio/eas/whoami")
record("GET /galaxy-studio/eas/whoami → 200", r.status_code == 200, f"HTTP {r.status_code}")

r = get("/galaxy-studio/code-library/stats")
ok = r.status_code == 200
detail = f"HTTP {r.status_code}"
if ok:
    try:
        b = r.json()
        detail = f"total_snippets={b.get('total_snippets')}, collection={b.get('collection')}"
    except Exception:
        pass
record("GET /galaxy-studio/code-library/stats → 200", ok, detail)

r = post("/galaxy-studio/code-library/search", json={"limit": 2})
ok = r.status_code == 200
detail = f"HTTP {r.status_code}"
if ok:
    try:
        b = r.json()
        ok = isinstance(b.get("snippets"), list)
        detail = f"returned={b.get('returned')}, snippets list ok={ok}"
    except Exception as e:
        ok = False
        detail = f"json: {e}"
record("POST /galaxy-studio/code-library/search {limit:2} → 200 + array", ok, detail)

# ═════════════════════════════════════════════════════════════════════
# Section 4 — Health stack unchanged
# ═════════════════════════════════════════════════════════════════════
print("\n─── Section 4 — Health stack invariants ───")

r = get("/health/overview")
ok = r.status_code == 200
detail = f"HTTP {r.status_code}"
if ok:
    try:
        b = r.json()
        ok = bool(b.get("all_green"))
        detail = f"all_green={b.get('all_green')}, elapsed_ms={b.get('elapsed_ms')}"
    except Exception as e:
        ok = False
        detail = f"json: {e}"
record("GET /health/overview → all_green=true", ok, detail)

r = get("/health/redundancies")
ok = r.status_code == 200
detail = f"HTTP {r.status_code}"
if ok:
    try:
        b = r.json()
        ok = b.get("total") == 42
        detail = f"total={b.get('total')}"
    except Exception as e:
        ok = False
        detail = f"json: {e}"
record("GET /health/redundancies → total=42", ok, detail)

r = get("/health/registry")
ok = r.status_code == 200
detail = f"HTTP {r.status_code}"
if ok:
    try:
        b = r.json()
        ok = b.get("ok") == 111 and b.get("skipped") == 0
        detail = f"ok={b.get('ok')}, skipped={b.get('skipped')}"
    except Exception as e:
        ok = False
        detail = f"json: {e}"
record("GET /health/registry → ok=111 skipped=0", ok, detail)

r = get("/world-engine/genres")
ok = r.status_code == 200
detail = f"HTTP {r.status_code}"
if ok:
    try:
        b = r.json()
        ok = b.get("count") == 5
        detail = f"count={b.get('count')}"
    except Exception as e:
        ok = False
        detail = f"json: {e}"
record("GET /world-engine/genres → count=5", ok, detail)

# ═════════════════════════════════════════════════════════════════════
# Section 5 — No new tracebacks + boot log shape
# ═════════════════════════════════════════════════════════════════════
print("\n─── Section 5 — Backend logs (boot lines + no new tracebacks) ───")

err_log = Path("/var/log/supervisor/backend.err.log")
boot_30 = False
boot_81 = False
last_started_idx = -1
lines = []
if err_log.exists():
    try:
        lines = err_log.read_text(errors="replace").splitlines()
    except Exception:
        lines = []

    # Find the LAST "Started server process" marker, then scan for the two
    # registry lines after it.
    for i, ln in enumerate(lines):
        if "Started server process" in ln:
            last_started_idx = i

    # Scan a window around boot (registry lines are printed BEFORE
    # "Started server process" actually — let's just look at the latest 200
    # lines preceding the marker as well as 30 after).
    if last_started_idx > 0:
        window = lines[max(0, last_started_idx - 300):last_started_idx + 50]
    else:
        window = lines[-500:]
    for ln in window:
        if "[BOOT] routes_registry: registered=30 skipped=0" in ln:
            boot_30 = True
        if "[BOOT] routes_registry: registered=81 skipped=0" in ln:
            boot_81 = True

record("Boot log: registered=30 skipped=0", boot_30, "present" if boot_30 else "missing")
record("Boot log: registered=81 skipped=0", boot_81, "present" if boot_81 else "missing")

# Check for NEW tracebacks after the latest "Started server process".
new_traceback = False
new_tb_excerpt = ""
if last_started_idx >= 0:
    tail = lines[last_started_idx:]
    for j, ln in enumerate(tail):
        if "Traceback (most recent call last)" in ln:
            # Skip pre-existing/unrelated. We only flag if it looks fresh.
            new_traceback = True
            new_tb_excerpt = "\n".join(tail[j:j + 6])
            break
record("No new Traceback after latest Started-server marker",
       not new_traceback,
       "" if not new_traceback else "found traceback:\n" + new_tb_excerpt[:500])

# Check for NEW SKIP lines (we tolerate pre-existing watchdog SKIPS only if
# they existed prior to the latest restart). New lines after last restart
# matching subrouter-import-SKIPPED is what we flag.
new_skip = False
new_skip_excerpt = ""
if last_started_idx >= 0:
    tail = lines[last_started_idx:]
    for ln in tail:
        if "subrouter import SKIPPED" in ln or "watchdog subrouter import SKIPPED" in ln:
            new_skip = True
            new_skip_excerpt = ln
            break
record("No new sub-router SKIP lines after restart", not new_skip,
       "" if not new_skip else new_skip_excerpt[:300])

# ═════════════════════════════════════════════════════════════════════
# Section 6 — pytest /app/backend/tests/test_routes_registry.py
# ═════════════════════════════════════════════════════════════════════
print("\n─── Section 6 — Smoke test: pytest test_routes_registry.py ───")

try:
    proc = subprocess.run(
        ["python", "-m", "pytest", "/app/backend/tests/test_routes_registry.py", "-q",
         "--no-header", "--tb=line"],
        cwd="/app/backend",
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    # Look for "113 passed"
    passed_113 = "113 passed" in out
    detail = ""
    if passed_113:
        # Extract the summary line
        for ln in reversed(out.splitlines()):
            if "passed" in ln and "=" in ln:
                detail = ln.strip()
                break
    else:
        # Capture summary
        tail_lines = out.strip().splitlines()[-5:]
        detail = " | ".join(tail_lines)
    record("pytest test_routes_registry.py → 113 passed", passed_113, detail[:300])
except Exception as e:
    record("pytest test_routes_registry.py → 113 passed", False, f"exec error: {e}")

# ═════════════════════════════════════════════════════════════════════
# Summary
# ═════════════════════════════════════════════════════════════════════
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
print(f"\n{'═' * 70}\nSUMMARY: {passed}/{total} checks passed\n{'═' * 70}\n")

print("FAILURES:" if passed < total else "All checks passed ✓")
for name, ok, detail in results:
    if not ok:
        print(f"  {FAIL} {name}\n       {detail}")

if passed < total:
    import sys
    sys.exit(1)
