"""
backend_test_apk_s20_v2.py — Regression on S20-hardened APK pipeline (round 2).

Per review request (changes since 36/36 baseline):
  - Theme: Theme.DeviceDefault.Light.NoActionBar (OEM-universal)
  - Package naming: underscores removed (real_runnable_v1 → realrunnablev1)
  - javac --release 8 (was 11)
  - Uncaught exception handler at process start
  - super.onCreate try/catch retry with null state
  - On-screen full stack-trace renderer in fallback view
  - <uses-feature webview required=false/>
  - largeHeap=true, installLocation=auto, launchMode=singleTask

8 regression tests:
  1. GET    /api/binary/inspect/real_runnable_v1
       • is_installable_apk: true
       • classes_dex_size >= 7000 bytes
       • 6 diagnostic bullets all start with "✓"
       • has_main_activity, has_launcher_intent, manifest_is_binary_xml, has_resources_arsc
  2. GET    /api/binary/download/real_runnable_v1/apk
       • HTTP 200, Content-Type application/vnd.android.package-archive
       • PK magic header, body >= 14000 bytes
  3. POST   /api/binary/rebuild/real_runnable_v1
       • rebuilt: true, fresh apk is_installable: true
  4. POST   /api/binary/rebuild/regression_<ts>
       • Synthesized stub still produces installable APK
       • Then DELETE
  5. GET    /api/binary/list
       • real_runnable_v1 with is_likely_runnable: true
  6. POST   /api/tools/invoke {tool:package_build, build_id:demo_apk_real}
       • ok=true, both artifacts, apk is_real_apk=true, is_installable=true
  7. GET    /api/binary/toolchain — have_full_toolchain: true
  8. POST   /api/tools/invoke {tool:web_search, ...}
       • ok=true, results non-empty
"""
import os, sys, time, json, requests

BASE = os.environ.get("BACKEND_BASE_URL",
                     "https://gemini-game-craft.preview.emergentagent.com")
API = BASE.rstrip("/") + "/api"

PASS, FAIL = [], []

def ok(name, cond, detail=""):
    if cond:
        print(f"✅ {name}")
        PASS.append(name)
    else:
        print(f"❌ {name} — {detail}")
        FAIL.append((name, detail))

def section(s):
    print(f"\n{'='*76}\n{s}\n{'='*76}")


# ─────────────────────────────────────────────────────────────────
section("1. GET /api/binary/inspect/real_runnable_v1")
r = requests.get(f"{API}/binary/inspect/real_runnable_v1", timeout=30)
print(f"  HTTP {r.status_code}")
ok("1. HTTP 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    data = r.json()
    s = data.get("structure", {})
    sig = data.get("signature", {})
    diag = (data.get("diagnostic") or data.get("diagnostics")
            or data.get("diagnostic_bullets") or [])
    if not diag:
        for k in ("checks", "bullets", "messages"):
            if k in data and isinstance(data[k], list):
                diag = data[k]
                break
    print(f"  is_installable_apk: {data.get('is_installable_apk')}")
    print(f"  size_bytes: {s.get('size_bytes')}")
    print(f"  classes_dex_size: {s.get('classes_dex_size')}")
    print(f"  has_main_activity: {s.get('has_main_activity')}")
    print(f"  has_launcher_intent: {s.get('has_launcher_intent')}")
    print(f"  manifest_is_binary_xml: {s.get('manifest_is_binary_xml')}")
    print(f"  has_resources_arsc: {s.get('has_resources_arsc')}")
    print(f"  signature.verifies: {sig.get('verifies')}")
    print(f"  diagnostics({len(diag)}): {diag[:6]}")

    ok("1a. is_installable_apk=true",
       data.get("is_installable_apk") is True,
       f"got {data.get('is_installable_apk')}")
    ok("1b. classes_dex_size >= 7000",
       s.get("classes_dex_size", 0) >= 7000,
       f"got {s.get('classes_dex_size')}")
    ok("1c. has_main_activity=true",
       s.get("has_main_activity") is True,
       f"got {s.get('has_main_activity')}")
    ok("1d. has_launcher_intent=true",
       s.get("has_launcher_intent") is True,
       f"got {s.get('has_launcher_intent')}")
    ok("1e. manifest_is_binary_xml=true",
       s.get("manifest_is_binary_xml") is True,
       f"got {s.get('manifest_is_binary_xml')}")
    ok("1f. has_resources_arsc=true",
       s.get("has_resources_arsc") is True,
       f"got {s.get('has_resources_arsc')}")
    # All 6 diagnostic bullets start with ✓
    if diag:
        bullets_ok = [str(b).lstrip().startswith("✓") for b in diag]
        ok("1g. 6+ diagnostic bullets all start with ✓",
           len(diag) >= 6 and all(bullets_ok),
           f"got {len(diag)} bullets, ✓-starts={bullets_ok}")
    else:
        ok("1g. 6 diagnostic bullets present", False,
           "no diagnostics field found; tried keys: diagnostics,diagnostic_bullets,checks,bullets,messages")


# ─────────────────────────────────────────────────────────────────
section("2. GET /api/binary/download/real_runnable_v1/apk")
r = requests.get(f"{API}/binary/download/real_runnable_v1/apk",
                 timeout=60, stream=True)
print(f"  HTTP {r.status_code}")
ok("2a. HTTP 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    ctype = r.headers.get("Content-Type", "")
    print(f"  Content-Type: {ctype}")
    ok("2b. Content-Type application/vnd.android.package-archive",
       "application/vnd.android.package-archive" in ctype,
       f"got {ctype}")
    body = r.content
    print(f"  body size: {len(body)}")
    print(f"  first 4 bytes (hex): {body[:4].hex()}")
    ok("2c. PK magic header (50 4B 03 04)",
       body[:4] == b"\x50\x4B\x03\x04",
       f"got {body[:4].hex()}")
    ok("2d. body >= 14000 bytes",
       len(body) >= 14000,
       f"got {len(body)}")


# ─────────────────────────────────────────────────────────────────
section("3. POST /api/binary/rebuild/real_runnable_v1")
r = requests.post(f"{API}/binary/rebuild/real_runnable_v1", timeout=300)
print(f"  HTTP {r.status_code}")
ok("3a. HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
if r.status_code == 200:
    data = r.json()
    print(f"  rebuilt: {data.get('rebuilt')}, source: {data.get('source')}")
    ok("3b. rebuilt=true", data.get("rebuilt") is True,
       f"got {data.get('rebuilt')}")
    # Fresh inspect
    ri = requests.get(f"{API}/binary/inspect/real_runnable_v1", timeout=30)
    if ri.status_code == 200:
        di = ri.json()
        print(f"  post-rebuild is_installable: {di.get('is_installable_apk')}")
        print(f"  post-rebuild classes_dex_size: {di.get('structure',{}).get('classes_dex_size')}")
        ok("3c. post-rebuild is_installable_apk=true",
           di.get("is_installable_apk") is True,
           f"got {di.get('is_installable_apk')}")
        ok("3d. post-rebuild classes_dex_size >= 7000",
           di.get("structure",{}).get("classes_dex_size", 0) >= 7000,
           f"got {di.get('structure',{}).get('classes_dex_size')}")


# ─────────────────────────────────────────────────────────────────
ts_build = f"regression_{int(time.time())}"
section(f"4. POST /api/binary/rebuild/{ts_build} (synth stub) + DELETE")
r = requests.post(f"{API}/binary/rebuild/{ts_build}", timeout=300)
print(f"  HTTP {r.status_code}")
ok("4a. rebuild HTTP 200", r.status_code == 200,
   f"got {r.status_code}: {r.text[:200]}")
if r.status_code == 200:
    data = r.json()
    print(f"  rebuilt: {data.get('rebuilt')}, source: {data.get('source')}")
    ok("4b. rebuilt=true", data.get("rebuilt") is True,
       f"got {data.get('rebuilt')}")
    ri = requests.get(f"{API}/binary/inspect/{ts_build}", timeout=30)
    print(f"  inspect HTTP {ri.status_code}")
    if ri.status_code == 200:
        di = ri.json()
        print(f"  is_installable_apk: {di.get('is_installable_apk')}")
        ok("4c. is_installable_apk=true",
           di.get("is_installable_apk") is True,
           f"got {di.get('is_installable_apk')}")
    # DELETE
    dr = requests.delete(f"{API}/binary/artifact/{ts_build}", timeout=30)
    print(f"  DELETE HTTP {dr.status_code}: {dr.text[:200]}")
    ok("4d. DELETE HTTP 200", dr.status_code == 200,
       f"got {dr.status_code}")
    if dr.status_code == 200:
        deleted = dr.json().get("deleted", [])
        ok("4e. deleted list non-empty",
           isinstance(deleted, list) and len(deleted) > 0,
           f"got {deleted}")


# ─────────────────────────────────────────────────────────────────
section("5. GET /api/binary/list")
r = requests.get(f"{API}/binary/list", timeout=30)
print(f"  HTTP {r.status_code}")
ok("5a. HTTP 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    data = r.json()
    apks = data.get("apks", [])
    by_id = {a.get("build_id"): a for a in apks}
    print(f"  count: {data.get('count')}; build_ids: {list(by_id.keys())}")
    rr = by_id.get("real_runnable_v1")
    ok("5b. real_runnable_v1 present", rr is not None, "missing")
    if rr:
        ok("5c. real_runnable_v1.is_likely_runnable=true",
           rr.get("is_likely_runnable") is True,
           f"got {rr.get('is_likely_runnable')}")
        print(f"  real_runnable_v1: size={rr.get('size_bytes')}, dex={rr.get('classes_dex_size')}, runnable={rr.get('is_likely_runnable')}")


# ─────────────────────────────────────────────────────────────────
section("6. POST /api/tools/invoke package_build demo_apk_real")
payload = {"tool": "package_build",
           "params": {"build_id": "demo_apk_real", "kinds": ["zip", "apk"]}}
r = requests.post(f"{API}/tools/invoke", json=payload, timeout=300)
print(f"  HTTP {r.status_code}")
ok("6a. HTTP 200", r.status_code == 200,
   f"got {r.status_code}: {r.text[:200]}")
if r.status_code == 200:
    data = r.json()
    print(f"  ok: {data.get('ok')}")
    ok("6b. ok=true", data.get("ok") is True, f"got ok={data.get('ok')}")
    result = data.get("result") or {}
    artifacts = result.get("artifacts") or data.get("artifacts") or []
    print(f"  artifacts count: {len(artifacts)}")
    for a in artifacts:
        print(f"    kind={a.get('kind')}, is_real_apk={a.get('is_real_apk')}, "
              f"is_installable={a.get('is_installable')}, size={a.get('size_bytes')}")
    ok("6c. exactly 2 artifacts", len(artifacts) == 2, f"got {len(artifacts)}")
    apk_art = next((a for a in artifacts if a.get("kind") == "apk"), None)
    zip_art = next((a for a in artifacts if a.get("kind") == "zip"), None)
    ok("6d. apk artifact present", apk_art is not None, "missing")
    ok("6e. zip artifact present", zip_art is not None, "missing")
    if apk_art:
        ok("6f. apk is_real_apk=true",
           apk_art.get("is_real_apk") is True,
           f"got {apk_art.get('is_real_apk')}")
        ok("6g. apk is_installable=true",
           apk_art.get("is_installable") is True,
           f"got {apk_art.get('is_installable')}")


# ─────────────────────────────────────────────────────────────────
section("7. GET /api/binary/toolchain")
r = requests.get(f"{API}/binary/toolchain", timeout=30)
print(f"  HTTP {r.status_code}")
ok("7a. HTTP 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  have_full_toolchain: {data.get('have_full_toolchain')}")
    print(f"  build_tools_version: {data.get('build_tools_version')}")
    ok("7b. have_full_toolchain=true",
       data.get("have_full_toolchain") is True,
       f"got {data.get('have_full_toolchain')}")


# ─────────────────────────────────────────────────────────────────
section("8. POST /api/tools/invoke web_search")
payload = {"tool": "web_search",
           "params": {"query": "galaxy s20 android 13 webview", "max_results": 2}}
r = requests.post(f"{API}/tools/invoke", json=payload, timeout=60)
print(f"  HTTP {r.status_code}")
ok("8a. HTTP 200", r.status_code == 200,
   f"got {r.status_code}: {r.text[:300]}")
if r.status_code == 200:
    data = r.json()
    print(f"  ok: {data.get('ok')}")
    ok("8b. ok=true", data.get("ok") is True, f"got ok={data.get('ok')}")
    result = data.get("result") or {}
    results = result.get("results") or data.get("results") or []
    print(f"  results count: {len(results)}")
    if results:
        for r0 in results[:2]:
            print(f"    title={str(r0.get('title',''))[:80]}, url={r0.get('url','')[:80]}")
    ok("8c. results array non-empty",
       isinstance(results, list) and len(results) > 0,
       f"got {len(results) if isinstance(results, list) else results}")


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
