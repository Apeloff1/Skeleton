"""
backend_test_apk_s20.py — Regression pass on rebuilt APK pipeline (S20 compat).

Per review request:
  1. GET    /api/binary/inspect/real_runnable_v1 — fresh structure assertions
  2. POST   /api/binary/rebuild/real_runnable_v1 — rebuild + re-inspect
  3. GET    /api/binary/list — appearance with is_likely_runnable:true
  4. POST   /api/binary/rebuild/quick_s20_test — synthesized stub path
     DELETE /api/binary/artifact/quick_s20_test
  5. POST   /api/tools/invoke {tool:package_build, build_id:demo_apk_real,
           kinds:[zip,apk]} — direct tool path
  6. GET    /api/binary/toolchain — have_full_toolchain still true
"""
import os, sys, json, requests

BASE = os.environ.get("BACKEND_BASE_URL", "https://gemini-game-craft.preview.emergentagent.com")
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
    print(f"\n{'='*72}\n{s}\n{'='*72}")


def inspect_real_runnable():
    r = requests.get(f"{API}/binary/inspect/real_runnable_v1", timeout=30)
    print(f"  HTTP {r.status_code}")
    ok("inspect HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:300]}")
    if r.status_code != 200:
        return None
    data = r.json()
    s = data.get("structure", {})
    sig = data.get("signature", {})
    print(f"  apk size: {s.get('size_bytes')} bytes")
    print(f"  classes_dex_size: {s.get('classes_dex_size')}")
    print(f"  has_classes_dex: {s.get('has_classes_dex')}")
    print(f"  has_main_activity: {s.get('has_main_activity')}")
    print(f"  has_launcher_intent: {s.get('has_launcher_intent')}")
    print(f"  manifest_is_binary_xml: {s.get('manifest_is_binary_xml')}")
    print(f"  has_resources_arsc: {s.get('has_resources_arsc')}")
    print(f"  signature.verifies: {sig.get('verifies')}")
    print(f"  is_installable_apk: {data.get('is_installable_apk')}")
    return data


# ─────────────────────────────────────────────────────────────────
section("1. GET /api/binary/inspect/real_runnable_v1 — fresh structure")
data1 = inspect_real_runnable()
if data1:
    s = data1.get("structure", {})
    sig = data1.get("signature", {})
    ok("1a. is_installable_apk=true", data1.get("is_installable_apk") is True,
       f"got {data1.get('is_installable_apk')}")
    ok("1b. structure.has_classes_dex=true", s.get("has_classes_dex") is True,
       f"got {s.get('has_classes_dex')}")
    ok("1c. structure.classes_dex_size >= 5000", s.get("classes_dex_size", 0) >= 5000,
       f"got {s.get('classes_dex_size')}")
    ok("1d. structure.has_main_activity=true", s.get("has_main_activity") is True,
       f"got {s.get('has_main_activity')}")
    ok("1e. structure.has_launcher_intent=true", s.get("has_launcher_intent") is True,
       f"got {s.get('has_launcher_intent')}")
    ok("1f. structure.manifest_is_binary_xml=true", s.get("manifest_is_binary_xml") is True,
       f"got {s.get('manifest_is_binary_xml')}")
    ok("1g. structure.has_resources_arsc=true", s.get("has_resources_arsc") is True,
       f"got {s.get('has_resources_arsc')}")
    ok("1h. signature.verifies=true", sig.get("verifies") is True,
       f"got {sig.get('verifies')}")
    size = s.get("size_bytes", 0)
    ok("1i. APK size between 14000 and 25000 bytes (bonus)",
       14000 <= size <= 25000, f"got {size} bytes")


# ─────────────────────────────────────────────────────────────────
section("2. POST /api/binary/rebuild/real_runnable_v1 — rebuild")
try:
    r = requests.post(f"{API}/binary/rebuild/real_runnable_v1", timeout=180)
    print(f"  HTTP {r.status_code}")
    ok("2a. rebuild HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:300]}")
    if r.status_code == 200:
        data = r.json()
        print(f"  rebuilt: {data.get('rebuilt')}, source: {data.get('source')}")
        print(f"  artifacts: {[a.get('kind') for a in data.get('artifacts', [])]}")
        ok("2b. rebuilt=true", data.get("rebuilt") is True, f"got {data.get('rebuilt')}")

        # Re-inspect after rebuild
        print("\n  Post-rebuild inspect:")
        data2 = inspect_real_runnable()
        if data2:
            s2 = data2.get("structure", {})
            sig2 = data2.get("signature", {})
            ok("2c. post-rebuild is_installable_apk=true", data2.get("is_installable_apk") is True,
               f"got {data2.get('is_installable_apk')}")
            ok("2d. post-rebuild classes_dex_size >= 5000", s2.get("classes_dex_size", 0) >= 5000,
               f"got {s2.get('classes_dex_size')}")
            ok("2e. post-rebuild has_main_activity=true", s2.get("has_main_activity") is True,
               f"got {s2.get('has_main_activity')}")
            ok("2f. post-rebuild has_launcher_intent=true", s2.get("has_launcher_intent") is True,
               f"got {s2.get('has_launcher_intent')}")
            ok("2g. post-rebuild manifest_is_binary_xml=true", s2.get("manifest_is_binary_xml") is True,
               f"got {s2.get('manifest_is_binary_xml')}")
            ok("2h. post-rebuild signature.verifies=true", sig2.get("verifies") is True,
               f"got {sig2.get('verifies')}")
            size2 = s2.get("size_bytes", 0)
            ok("2i. post-rebuild APK size 14000-25000 bytes",
               14000 <= size2 <= 25000, f"got {size2} bytes")
except Exception as e:
    FAIL.append(("2. rebuild real_runnable_v1", str(e)))
    print(f"❌ rebuild crashed: {e}")


# ─────────────────────────────────────────────────────────────────
section("3. GET /api/binary/list — appearance with is_likely_runnable")
try:
    r = requests.get(f"{API}/binary/list", timeout=30)
    print(f"  HTTP {r.status_code}")
    ok("3a. list HTTP 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        apks = data.get("apks", [])
        by_id = {a.get("build_id"): a for a in apks}
        print(f"  count: {data.get('count')}; build_ids: {list(by_id.keys())}")
        rr = by_id.get("real_runnable_v1")
        ok("3b. real_runnable_v1 present in list", rr is not None, "missing from list")
        if rr:
            ok("3c. real_runnable_v1.is_likely_runnable=true",
               rr.get("is_likely_runnable") is True, f"got {rr.get('is_likely_runnable')}")
            print(f"  real_runnable_v1 row: size={rr.get('size_bytes')}, "
                  f"dex={rr.get('classes_dex_size')}, runnable={rr.get('is_likely_runnable')}")
except Exception as e:
    FAIL.append(("3. binary/list", str(e)))
    print(f"❌ list crashed: {e}")


# ─────────────────────────────────────────────────────────────────
section("4. POST /api/binary/rebuild/quick_s20_test — synthesized stub")
try:
    r = requests.post(f"{API}/binary/rebuild/quick_s20_test", timeout=180)
    print(f"  HTTP {r.status_code}")
    ok("4a. quick_s20 rebuild HTTP 200", r.status_code == 200,
       f"got {r.status_code}: {r.text[:300]}")
    if r.status_code == 200:
        data = r.json()
        print(f"  rebuilt: {data.get('rebuilt')}, source: {data.get('source')}")
        ok("4b. quick_s20 rebuilt=true", data.get("rebuilt") is True,
           f"got {data.get('rebuilt')}")

        # Inspect the synthesized APK
        ri = requests.get(f"{API}/binary/inspect/quick_s20_test", timeout=30)
        print(f"  inspect HTTP {ri.status_code}")
        if ri.status_code == 200:
            di = ri.json()
            print(f"  is_installable_apk: {di.get('is_installable_apk')}")
            print(f"  classes_dex_size: {di.get('structure',{}).get('classes_dex_size')}")
            ok("4c. quick_s20 is_installable_apk=true",
               di.get("is_installable_apk") is True,
               f"got {di.get('is_installable_apk')}")
        else:
            ok("4c. inspect quick_s20 HTTP 200", False, f"got {ri.status_code}")

    # Cleanup: DELETE
    dr = requests.delete(f"{API}/binary/artifact/quick_s20_test", timeout=30)
    print(f"  DELETE HTTP {dr.status_code}, body: {dr.text[:200]}")
    ok("4d. DELETE quick_s20_test HTTP 200", dr.status_code == 200,
       f"got {dr.status_code}")
    if dr.status_code == 200:
        deleted = dr.json().get("deleted", [])
        ok("4e. delete returned non-empty list", isinstance(deleted, list) and len(deleted) > 0,
           f"got {deleted}")
except Exception as e:
    FAIL.append(("4. quick_s20_test cycle", str(e)))
    print(f"❌ quick_s20 crashed: {e}")


# ─────────────────────────────────────────────────────────────────
section("5. POST /api/tools/invoke package_build demo_apk_real")
try:
    payload = {
        "tool": "package_build",
        "params": {"build_id": "demo_apk_real", "kinds": ["zip", "apk"]},
    }
    r = requests.post(f"{API}/tools/invoke", json=payload, timeout=180)
    print(f"  HTTP {r.status_code}")
    ok("5a. tools/invoke HTTP 200", r.status_code == 200,
       f"got {r.status_code}: {r.text[:300]}")
    if r.status_code == 200:
        data = r.json()
        print(f"  ok: {data.get('ok')}")
        ok("5b. ok=true", data.get("ok") is True, f"got ok={data.get('ok')}")
        result = data.get("result") or {}
        artifacts = result.get("artifacts") or data.get("artifacts") or []
        print(f"  artifacts count: {len(artifacts)}")
        for a in artifacts:
            print(f"    kind={a.get('kind')}, "
                  f"is_real_apk={a.get('is_real_apk')}, "
                  f"is_installable={a.get('is_installable')}, "
                  f"size={a.get('size_bytes')}")
        ok("5c. exactly 2 artifacts", len(artifacts) == 2, f"got {len(artifacts)}")
        apk_art = next((a for a in artifacts if a.get("kind") == "apk"), None)
        ok("5d. apk artifact present", apk_art is not None, "no apk artifact")
        if apk_art:
            ok("5e. apk is_real_apk=true", apk_art.get("is_real_apk") is True,
               f"got {apk_art.get('is_real_apk')}")
            ok("5f. apk is_installable=true", apk_art.get("is_installable") is True,
               f"got {apk_art.get('is_installable')}")
except Exception as e:
    FAIL.append(("5. tools/invoke package_build", str(e)))
    print(f"❌ tools/invoke crashed: {e}")


# ─────────────────────────────────────────────────────────────────
section("6. GET /api/binary/toolchain — regression")
try:
    r = requests.get(f"{API}/binary/toolchain", timeout=30)
    print(f"  HTTP {r.status_code}")
    ok("6a. toolchain HTTP 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  have_full_toolchain: {data.get('have_full_toolchain')}")
        print(f"  build_tools_version: {data.get('build_tools_version')}")
        ok("6b. have_full_toolchain=true", data.get("have_full_toolchain") is True,
           f"got {data.get('have_full_toolchain')}")
except Exception as e:
    FAIL.append(("6. toolchain", str(e)))
    print(f"❌ toolchain crashed: {e}")


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
