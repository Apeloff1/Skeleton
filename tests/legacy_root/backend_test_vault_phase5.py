"""Phase-5 vault read cluster extraction — regression test."""
import os
import sys
import time
import json
import requests

BASE = "https://gemini-game-craft.preview.emergentagent.com/api"
TIMEOUT = 30

results = []
def log(name, ok, detail=""):
    status = "✅" if ok else "❌"
    results.append((ok, name, detail))
    print(f"{status} {name} :: {detail}")

# 1) Public URL invariance
def section_1():
    print("\n--- Section 1: Public URL invariance ---")
    r = requests.get(f"{BASE}/galaxy-studio/vault", timeout=TIMEOUT)
    ok = r.status_code == 200
    body = r.json() if ok else {}
    has_keys = ok and all(k in body for k in ("total_entries", "zips", "apks"))
    log("GET /vault → 200 with {total_entries, zips, apks}",
        has_keys, f"status={r.status_code}, total_entries={body.get('total_entries')}, zips={len(body.get('zips', []))}, apks={len(body.get('apks', []))}")

    r2 = requests.get(f"{BASE}/galaxy-studio/vault/download/nonexistent-id", timeout=TIMEOUT)
    ok2 = r2.status_code == 404
    detail = ""
    try:
        detail = r2.json().get("detail", "")
    except Exception:
        pass
    log("GET /vault/download/nonexistent-id → 404 detail='Vault entry not found'",
        ok2 and detail == "Vault entry not found", f"status={r2.status_code}, detail={detail!r}")

    # If real entries exist, hit first one
    if body.get("zips"):
        first = body["zips"][0]
        url = first["download_url"]
        # download_url is path-relative; need to strip /api prefix to attach to BASE
        full = url if url.startswith("http") else f"https://gemini-game-craft.preview.emergentagent.com{url}"
        r3 = requests.get(full, timeout=TIMEOUT, stream=True)
        ok3 = r3.status_code in (200, 404)
        log(f"GET first zip's download_url → 200 or 404",
            ok3, f"status={r3.status_code}, vault_id={first['vault_id']}")
        r3.close()
    return body

# 2) SSOT preserved — create build → zip → vault count +1
def section_2(initial_body):
    print("\n--- Section 2: SSOT preserved ---")
    initial_total = initial_body.get("total_entries", 0)
    # Create build
    payload = {"title": "VaultPhase5Test", "genre": "rpg", "art_style": "pixel"}
    r = requests.post(f"{BASE}/galaxy-studio/create", json=payload, timeout=TIMEOUT)
    if r.status_code != 200:
        log("POST /galaxy-studio/create", False, f"status={r.status_code} body={r.text[:200]}")
        return
    build_id = r.json().get("build_id")
    log("POST /galaxy-studio/create", True, f"build_id={build_id}")

    # advance fully through 10 batches (or check current status approach)
    # Use /advance for 10 batches sequentially.
    last_status = None
    for i in range(15):
        ra = requests.post(f"{BASE}/galaxy-studio/advance/{build_id}", timeout=TIMEOUT)
        if ra.status_code != 200:
            log("advance loop", False, f"i={i} status={ra.status_code} body={ra.text[:200]}")
            return
        last_status = ra.json()
        if last_status.get("status") == "completed":
            break
    log("advance to completion", last_status.get("status") == "completed",
        f"status={last_status.get('status')}, current_batch={last_status.get('current_batch')}")
    if last_status.get("status") != "completed":
        return

    # Trigger zip
    rz = requests.post(f"{BASE}/galaxy-studio/vault/zip/{build_id}", timeout=120)
    ok_zip = rz.status_code == 200
    log("POST /vault/zip/{build_id}", ok_zip, f"status={rz.status_code}")
    if not ok_zip:
        print(rz.text[:400])
        return
    zip_body = rz.json()
    new_vault_id = zip_body.get("vault_id")
    log("new vault entry has vault_id", bool(new_vault_id), f"vault_id={new_vault_id}")

    # Recheck list
    r2 = requests.get(f"{BASE}/galaxy-studio/vault", timeout=TIMEOUT)
    new_body = r2.json()
    new_total = new_body.get("total_entries", 0)
    log("total_entries incremented by >=1 (Mongo + cache SSOT)",
        new_total > initial_total, f"before={initial_total}, after={new_total}")
    # Find new entry
    found = next((z for z in new_body.get("zips", []) if z.get("vault_id") == new_vault_id), None)
    log("new vault entry appears in zips list",
        found is not None, f"present={found is not None}")
    if found:
        expected_dl = f"/api/galaxy-studio/vault/download/{new_vault_id}"
        log("download_url points to sub-router path",
            found.get("download_url") == expected_dl,
            f"got={found.get('download_url')}")

# 3) No regression on Phase-2/3/4
def section_3():
    print("\n--- Section 3: No regression on Phase-2/3/4 sub-routers ---")
    checks = [
        ("GET", "/galaxy-studio/eas/whoami", 200),
        ("GET", "/galaxy-studio/code-library/stats", 200),
        ("GET", "/galaxy-studio/watchdog/health", 200),
        ("POST", "/galaxy-studio/resurrect/nonexistent", 404),
    ]
    for method, path, expected in checks:
        if method == "GET":
            r = requests.get(f"{BASE}{path}", timeout=TIMEOUT)
        else:
            r = requests.post(f"{BASE}{path}", timeout=TIMEOUT)
        log(f"{method} {path} → {expected}", r.status_code == expected, f"got={r.status_code}")

# 4) Health stack
def section_4():
    print("\n--- Section 4: Health stack ---")
    r = requests.get(f"{BASE}/health/overview", timeout=TIMEOUT)
    b = r.json() if r.status_code == 200 else {}
    log("/health/overview all_green=true", r.status_code == 200 and b.get("all_green") is True,
        f"status={r.status_code}, all_green={b.get('all_green')}")

    r = requests.get(f"{BASE}/health/redundancies", timeout=TIMEOUT)
    b = r.json() if r.status_code == 200 else {}
    log("/health/redundancies total=42", b.get("total") == 42, f"total={b.get('total')}")

    r = requests.get(f"{BASE}/health/registry", timeout=TIMEOUT)
    b = r.json() if r.status_code == 200 else {}
    log("/health/registry ok=111 skipped=0",
        b.get("ok") == 111 and b.get("skipped") == 0,
        f"ok={b.get('ok')}, skipped={b.get('skipped')}")

    r = requests.get(f"{BASE}/world-engine/genres", timeout=TIMEOUT)
    b = r.json() if r.status_code == 200 else {}
    log("/world-engine/genres count=5", b.get("count") == 5, f"count={b.get('count')}")

# 5) Boot logs
def section_5():
    print("\n--- Section 5: Boot logs ---")
    import subprocess
    out = subprocess.run(["grep", "-E", "registered=(30|81) skipped=0|vault subrouter import SKIPPED", "/var/log/supervisor/backend.err.log"],
                        capture_output=True, text=True)
    lines = out.stdout.strip().split("\n")
    last_lines = lines[-10:] if lines else []
    print("Relevant log lines (last 10):")
    for ln in last_lines:
        print("  ", ln)
    has_30 = any("registered=30 skipped=0" in ln for ln in last_lines)
    has_81 = any("registered=81 skipped=0" in ln for ln in last_lines)
    has_skip = any("vault subrouter import SKIPPED" in ln for ln in last_lines)
    log("Boot logs: registered=30 skipped=0", has_30, "")
    log("Boot logs: registered=81 skipped=0", has_81, "")
    log("Boot logs: NO 'vault subrouter import SKIPPED'", not has_skip, "")

# 6) Smoke test
def section_6():
    print("\n--- Section 6: pytest smoke test ---")
    import subprocess
    out = subprocess.run(
        ["python", "-m", "pytest", "/app/backend/tests/test_routes_registry.py", "-q"],
        capture_output=True, text=True, timeout=120, cwd="/app/backend",
    )
    combined = out.stdout + out.stderr
    print(combined[-1500:])
    passed = "113 passed" in combined
    log("pytest test_routes_registry.py → 113 passed", passed, "")

if __name__ == "__main__":
    body = section_1()
    section_2(body)
    section_3()
    section_4()
    section_5()
    section_6()
    print("\n" + "=" * 60)
    fails = [r for r in results if not r[0]]
    print(f"TOTAL: {len(results)} checks, {len(results) - len(fails)} passed, {len(fails)} failed")
    if fails:
        print("FAILED:")
        for _, n, d in fails:
            print(f"  - {n} :: {d}")
    sys.exit(0 if not fails else 1)
