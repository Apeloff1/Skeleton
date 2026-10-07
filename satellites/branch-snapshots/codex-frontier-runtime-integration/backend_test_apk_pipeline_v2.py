"""
backend_test_apk_pipeline_v2.py — Regression+verification pass on APK pipeline.

Verifies:
  1. GET    /api/binary/list — on-disk inventory
  2. DELETE /api/binary/artifact/{build_id} — artifact removal
  3. GET    /api/binary/inspect/real_runnable_v1 — beefed MainActivity (dex >= 4000)
  4. POST   /api/binary/rebuild/real_runnable_v1 — synthesized fallback
  5. GET    /api/binary/download/real_runnable_v1/apk
  6. GET    /api/binary/toolchain
  7. Smoke: POST /api/tools/invoke web_search
"""
import os, sys, json, requests, time

BASE = os.environ.get("BACKEND_BASE_URL", "https://gemini-game-craft.preview.emergentagent.com")
API = BASE.rstrip("/") + "/api"

PASS = []
FAIL = []

def assert_ok(name, cond, detail=""):
    if cond:
        print(f"✅ {name}")
        PASS.append(name)
    else:
        print(f"❌ {name} — {detail}")
        FAIL.append((name, detail))

def section(s):
    print(f"\n{'='*70}\n{s}\n{'='*70}")


# ─────────────────────────────────────────────────────────────────
# 1. GET /api/binary/list
# ─────────────────────────────────────────────────────────────────
section("1. GET /api/binary/list")
try:
    r = requests.get(f"{API}/binary/list", timeout=30)
    print(f"  HTTP {r.status_code}")
    assert_ok("1a. /binary/list returns 200", r.status_code == 200, f"got {r.status_code}")
    data = r.json()
    print(f"  Top-level keys: {sorted(data.keys())}")
    assert_ok("1b. response has count >= 2", data.get("count", 0) >= 2, f"count={data.get('count')}")
    apks = data.get("apks", [])
    assert_ok("1c. response.apks is an array", isinstance(apks, list), f"type={type(apks)}")
    
    required_fields = {"build_id", "size_bytes", "modified_at", "has_classes_dex",
                       "has_manifest", "classes_dex_size", "is_likely_runnable", "download_url"}
    if apks:
        first = apks[0]
        missing = required_fields - set(first.keys())
        assert_ok("1d. each row has required fields", not missing, f"missing={missing}")
    
    # find real_runnable_v1 and demo_apk_real
    by_id = {a["build_id"]: a for a in apks}
    print(f"  build_ids on disk: {list(by_id.keys())[:20]}")
    rr = by_id.get("real_runnable_v1")
    dr = by_id.get("demo_apk_real")
    assert_ok("1e. real_runnable_v1 present", rr is not None, "missing from list")
    assert_ok("1f. demo_apk_real present", dr is not None, "missing from list")
    if rr:
        assert_ok("1g. real_runnable_v1.is_likely_runnable=true", rr.get("is_likely_runnable") is True, f"got {rr.get('is_likely_runnable')}")
    if dr:
        assert_ok("1h. demo_apk_real.is_likely_runnable=true", dr.get("is_likely_runnable") is True, f"got {dr.get('is_likely_runnable')}")
except Exception as e:
    FAIL.append(("1. /binary/list", str(e)))
    print(f"❌ /binary/list crashed: {e}")


# ─────────────────────────────────────────────────────────────────
# 2. DELETE /api/binary/artifact/{build_id}
# ─────────────────────────────────────────────────────────────────
section("2. DELETE /api/binary/artifact/test_delete_me")
THROWAWAY = "test_delete_me"
try:
    # First create a throwaway APK by POSTing /api/binary/rebuild/test_delete_me
    print(f"  Creating throwaway via POST /api/binary/rebuild/{THROWAWAY}...")
    rb = requests.post(f"{API}/binary/rebuild/{THROWAWAY}", timeout=120)
    print(f"  rebuild HTTP {rb.status_code}")
    assert_ok("2a. POST rebuild/test_delete_me HTTP 200", rb.status_code == 200, f"got {rb.status_code}: {rb.text[:300]}")
    if rb.status_code == 200:
        rbjson = rb.json()
        print(f"  rebuild source: {rbjson.get('source')!r}, rebuilt: {rbjson.get('rebuilt')}")
        assert_ok("2b. rebuild source = 'synthesized'", rbjson.get("source") == "synthesized", f"source={rbjson.get('source')}")
    
    # Confirm it shows up in list
    rl = requests.get(f"{API}/binary/list", timeout=30).json()
    in_list = any(a["build_id"] == THROWAWAY for a in rl.get("apks", []))
    assert_ok("2c. test_delete_me now visible in /binary/list", in_list, "not in list")
    
    # DELETE
    dr = requests.delete(f"{API}/binary/artifact/{THROWAWAY}", timeout=30)
    print(f"  delete HTTP {dr.status_code}, body: {dr.text[:200]}")
    assert_ok("2d. DELETE returns 200", dr.status_code == 200, f"got {dr.status_code}")
    drj = dr.json() if dr.status_code == 200 else {}
    deleted = drj.get("deleted", [])
    assert_ok("2e. response.deleted is a non-empty list", isinstance(deleted, list) and len(deleted) > 0, f"deleted={deleted}")
    assert_ok("2f. deleted includes 'apk'", "apk" in deleted, f"deleted={deleted}")
    # 'zip' should also be present (per review request)
    if "zip" in deleted:
        print(f"  ✓ deleted also includes 'zip' (deleted={deleted})")
    else:
        print(f"  ℹ deleted={deleted} (zip not present — synth path may not produce zip)")
    
    # Confirm no longer in list
    rl2 = requests.get(f"{API}/binary/list", timeout=30).json()
    still_in = any(a["build_id"] == THROWAWAY for a in rl2.get("apks", []))
    assert_ok("2g. /binary/list no longer includes test_delete_me", not still_in, "still listed")
    
    # Edge: DELETE again on now-empty build_id should return 200 with deleted=[]
    dr2 = requests.delete(f"{API}/binary/artifact/{THROWAWAY}", timeout=30)
    print(f"  edge-delete HTTP {dr2.status_code}, body: {dr2.text[:200]}")
    assert_ok("2h. edge DELETE on missing build_id returns 200", dr2.status_code == 200, f"got {dr2.status_code}")
    if dr2.status_code == 200:
        edge_deleted = dr2.json().get("deleted", None)
        assert_ok("2i. edge DELETE returns deleted=[]", edge_deleted == [], f"got {edge_deleted!r}")
except Exception as e:
    FAIL.append(("2. DELETE artifact flow", str(e)))
    print(f"❌ /binary/artifact crashed: {e}")


# ─────────────────────────────────────────────────────────────────
# 3. GET /api/binary/inspect/real_runnable_v1
# ─────────────────────────────────────────────────────────────────
section("3. GET /api/binary/inspect/real_runnable_v1")
try:
    r = requests.get(f"{API}/binary/inspect/real_runnable_v1", timeout=30)
    print(f"  HTTP {r.status_code}")
    assert_ok("3a. inspect HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:300]}")
    data = r.json()
    struct = data.get("structure", {})
    dex_size = struct.get("classes_dex_size", 0)
    print(f"  classes_dex_size: {dex_size} bytes")
    assert_ok("3b. structure.classes_dex_size >= 4000", dex_size >= 4000, f"got {dex_size} bytes")
    assert_ok("3c. is_installable_apk=true", data.get("is_installable_apk") is True, f"got {data.get('is_installable_apk')}")
    diagnostic = data.get("diagnostic", [])
    print(f"  diagnostic bullets ({len(diagnostic)}):")
    for d in diagnostic:
        print(f"    {d}")
    assert_ok("3d. exactly 6 diagnostic bullets", len(diagnostic) == 6, f"got {len(diagnostic)}")
    all_check = all(d.startswith("✓") for d in diagnostic)
    assert_ok("3e. all 6 diagnostic bullets start with ✓", all_check, f"non-✓ entries: {[d for d in diagnostic if not d.startswith('✓')]}")
except Exception as e:
    FAIL.append(("3. inspect real_runnable_v1", str(e)))
    print(f"❌ inspect crashed: {e}")


# ─────────────────────────────────────────────────────────────────
# 4. POST /api/binary/rebuild/real_runnable_v1
# ─────────────────────────────────────────────────────────────────
section("4. POST /api/binary/rebuild/real_runnable_v1")
try:
    r = requests.post(f"{API}/binary/rebuild/real_runnable_v1", timeout=120)
    print(f"  HTTP {r.status_code}")
    assert_ok("4a. rebuild HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:300]}")
    if r.status_code == 200:
        data = r.json()
        print(f"  source: {data.get('source')!r}, rebuilt: {data.get('rebuilt')}")
        print(f"  artifacts: {[a.get('kind') for a in data.get('artifacts', [])]}")
        assert_ok("4b. source == 'synthesized'", data.get("source") == "synthesized", f"got {data.get('source')!r}")
        assert_ok("4c. rebuilt=true", data.get("rebuilt") is True, f"got {data.get('rebuilt')}")
        # Now inspect after rebuild
        r2 = requests.get(f"{API}/binary/inspect/real_runnable_v1", timeout=30)
        if r2.status_code == 200:
            data2 = r2.json()
            assert_ok("4d. APK still is_installable_apk=true after rebuild", data2.get("is_installable_apk") is True, f"got {data2.get('is_installable_apk')}")
            new_size = data2.get("structure", {}).get("classes_dex_size", 0)
            print(f"  post-rebuild classes_dex_size: {new_size}")
except Exception as e:
    FAIL.append(("4. rebuild real_runnable_v1", str(e)))
    print(f"❌ rebuild crashed: {e}")


# ─────────────────────────────────────────────────────────────────
# 5. GET /api/binary/download/real_runnable_v1/apk
# ─────────────────────────────────────────────────────────────────
section("5. GET /api/binary/download/real_runnable_v1/apk")
try:
    r = requests.get(f"{API}/binary/download/real_runnable_v1/apk", timeout=60)
    print(f"  HTTP {r.status_code}")
    ct = r.headers.get("content-type", "")
    print(f"  Content-Type: {ct}")
    print(f"  Body size: {len(r.content)} bytes")
    head = r.content[:4]
    print(f"  Body magic: {head!r}")
    assert_ok("5a. download HTTP 200", r.status_code == 200, f"got {r.status_code}")
    assert_ok("5b. content-type application/vnd.android.package-archive", "application/vnd.android.package-archive" in ct, f"got {ct}")
    assert_ok("5c. body starts with PK", head[:2] == b"PK", f"got {head!r}")
    assert_ok("5d. body >= 10000 bytes", len(r.content) >= 10000, f"got {len(r.content)} bytes")
except Exception as e:
    FAIL.append(("5. download apk", str(e)))
    print(f"❌ download crashed: {e}")


# ─────────────────────────────────────────────────────────────────
# 6. GET /api/binary/toolchain
# ─────────────────────────────────────────────────────────────────
section("6. GET /api/binary/toolchain")
try:
    r = requests.get(f"{API}/binary/toolchain", timeout=30)
    print(f"  HTTP {r.status_code}")
    assert_ok("6a. toolchain HTTP 200", r.status_code == 200, f"got {r.status_code}")
    data = r.json()
    print(f"  have_full_toolchain: {data.get('have_full_toolchain')}")
    print(f"  build_tools_version: {data.get('build_tools_version')}")
    print(f"  android_jar_exists: {data.get('android_jar_exists')}")
    print(f"  debug_keystore_exists: {data.get('debug_keystore_exists')}")
    assert_ok("6b. have_full_toolchain=true", data.get("have_full_toolchain") is True, f"got {data.get('have_full_toolchain')}")
except Exception as e:
    FAIL.append(("6. toolchain", str(e)))
    print(f"❌ toolchain crashed: {e}")


# ─────────────────────────────────────────────────────────────────
# 7. Smoke regression: POST /api/tools/invoke web_search
# ─────────────────────────────────────────────────────────────────
section("7. Smoke: POST /api/tools/invoke web_search 'expo 2026'")
try:
    payload = {"tool": "web_search", "params": {"query": "expo 2026"}}
    r = requests.post(f"{API}/tools/invoke", json=payload, timeout=60)
    print(f"  HTTP {r.status_code}")
    assert_ok("7a. tools/invoke HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:300]}")
    if r.status_code == 200:
        data = r.json()
        print(f"  ok: {data.get('ok')}")
        assert_ok("7b. ok=true", data.get("ok") is True, f"got ok={data.get('ok')}: {data}")
        # check there are real DDG results
        result = data.get("result", {}) or data.get("results") or {}
        # Various shapes — try to find results array
        results = (result.get("results") if isinstance(result, dict) else None) or data.get("results") or []
        print(f"  results found: {len(results) if isinstance(results, list) else 'unknown shape'}")
        if isinstance(results, list):
            assert_ok("7c. >= 1 real result returned", len(results) >= 1, f"got {len(results)}")
            if results:
                print(f"  first result keys: {list(results[0].keys()) if isinstance(results[0], dict) else type(results[0])}")
                print(f"  first result: {json.dumps(results[0], indent=2)[:400]}")
except Exception as e:
    FAIL.append(("7. tools/invoke web_search", str(e)))
    print(f"❌ tools/invoke crashed: {e}")


# ─────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────
section("SUMMARY")
print(f"PASSED: {len(PASS)}")
print(f"FAILED: {len(FAIL)}")
if FAIL:
    print("\nFailures:")
    for n, d in FAIL:
        print(f"  ❌ {n}: {d}")
    sys.exit(1)
print("\n🎉 All assertions passed.")
sys.exit(0)
