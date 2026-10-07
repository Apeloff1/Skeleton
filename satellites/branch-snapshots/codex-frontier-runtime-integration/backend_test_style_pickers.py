"""
Backend test — Galaxy Studio v6 Style Pickers
Tests 10 cases per review request.
"""
import os
import json
import sys
import requests

BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"
API = f"{BACKEND_URL}/api/galaxy-studio"
TIMEOUT = 120

def log(msg):
    print(msg, flush=True)

def post(path, body):
    r = requests.post(f"{API}{path}", json=body, timeout=TIMEOUT)
    return r

def get(path):
    r = requests.get(f"{API}{path}", timeout=TIMEOUT)
    return r

results = {}

# ── CASE 1: Full payload ───────────────────────────────
log("\n=== CASE 1: Full payload /create ===")
full_style = {
    "graphic_style": "cel_shaded",
    "sound_style": "cinematic_fx",
    "music_style": "orchestral_epic",
    "design_style": "minimalist",
    "cinematic_style": "nolan",
    "director_style": "kojima",
    "dimension": "3d_rtx",
    "asset_style": "stylized_handpainted",
    "model_style": "heroic_8head",
}
payload = {
    "title": "StyleTestA",
    "genre": "rpg",
    "age_era_year": 2015,
    "complexity": 3,
    "age_target": "T",
    "style_params": full_style,
}
r = post("/create", payload)
log(f"POST /create status={r.status_code}")
try:
    data = r.json()
    log(f"body keys: {list(data.keys())}")
except Exception:
    log(f"body non-JSON: {r.text[:300]}")
    data = {}
assert r.status_code == 200, f"Case1 FAIL status={r.status_code}"
build_id_A = data.get("build_id")
assert build_id_A, "Case1 FAIL: no build_id"
results["case1"] = ("PASS", f"build_id={build_id_A}")

# ── CASE 2: advance once ──────────────────────────────
log("\n=== CASE 2: POST /advance ===")
r = post("/advance", {"build_id": build_id_A})
log(f"POST /advance status={r.status_code}")
try:
    d = r.json()
    log(f"phase={d.get('phase')}, files_so_far={d.get('files_count', d.get('files'))}, batch={d.get('batch_name')}")
except Exception:
    log(f"body: {r.text[:300]}")
assert r.status_code == 200, f"Case2 FAIL status={r.status_code}"
results["case2"] = ("PASS", "advance ok")

# ── CASE 3: GET STYLE_MANIFEST.md ─────────────────────
log("\n=== CASE 3: GET /file/{id}/docs/STYLE_MANIFEST.md ===")
r = get(f"/file/{build_id_A}/docs/STYLE_MANIFEST.md")
log(f"status={r.status_code}")
if r.status_code != 200:
    log(f"body: {r.text[:400]}")
    results["case3"] = ("FAIL", f"status={r.status_code}")
else:
    data = r.json()
    content = data.get("content", "")
    size = data.get("size", len(content))
    expected_headers = ["Graphic Style", "Sound Style", "Music Style", "Design Style",
                        "Cinematic Style", "Director Style", "Dimension", "Asset Style", "Model Style"]
    expected_values = ["cel_shaded", "cinematic_fx", "orchestral_epic", "minimalist",
                       "nolan", "kojima", "3d_rtx", "stylized_handpainted", "heroic_8head"]
    missing_h = [h for h in expected_headers if h not in content]
    missing_v = [v for v in expected_values if v not in content]
    log(f"file size: {size} bytes, lines: {data.get('lines')}")
    if missing_h or missing_v:
        log(f"MISSING headers: {missing_h}")
        log(f"MISSING values: {missing_v}")
        log(f"content preview:\n{content[:800]}")
        results["case3"] = ("FAIL", f"missing_headers={missing_h}, missing_values={missing_v}")
    else:
        results["case3"] = ("PASS", f"all 9 headers + 9 values present, size={size}B")

# ── CASE 4: GET swarm_narrative_feed.json ─────────────
log("\n=== CASE 4: GET /file/{id}/docs/swarm_narrative_feed.json ===")
r = get(f"/file/{build_id_A}/docs/swarm_narrative_feed.json")
log(f"status={r.status_code}")
if r.status_code != 200:
    log(f"body: {r.text[:400]}")
    results["case4"] = ("FAIL", f"status={r.status_code}")
else:
    data = r.json()
    content = data.get("content", "")
    try:
        feed = json.loads(content)
        sp = feed.get("style_params")
        log(f"style_params type: {type(sp).__name__}")
        log(f"style_params keys: {list(sp.keys()) if isinstance(sp, dict) else 'N/A'}")
        if not isinstance(sp, dict):
            results["case4"] = ("FAIL", "style_params not a dict")
        else:
            mismatches = []
            for k, v in full_style.items():
                if sp.get(k) != v:
                    mismatches.append(f"{k}={sp.get(k)}≠{v}")
            if mismatches:
                results["case4"] = ("FAIL", f"mismatches: {mismatches}")
            else:
                results["case4"] = ("PASS", "all 9 keys + values match verbatim")
    except Exception as e:
        results["case4"] = ("FAIL", f"JSON parse error: {e}")

# ── CASE 5: Partial style_params ──────────────────────
log("\n=== CASE 5: Partial style_params ===")
partial = {"graphic_style": "pixel_16bit", "dimension": "2_5d"}
r = post("/create", {
    "title": "StyleTestB",
    "genre": "rpg",
    "age_era_year": 2015,
    "complexity": 3,
    "age_target": "T",
    "style_params": partial,
})
log(f"POST /create partial status={r.status_code}")
assert r.status_code == 200, f"Case5a FAIL status={r.status_code}"
data = r.json()
build_id_B = data.get("build_id")
r = post("/advance", {"build_id": build_id_B})
log(f"POST /advance partial status={r.status_code}")
assert r.status_code == 200, f"Case5b FAIL advance status={r.status_code}"
r = get(f"/file/{build_id_B}/docs/STYLE_MANIFEST.md")
log(f"GET STYLE_MANIFEST.md status={r.status_code}")
if r.status_code != 200:
    log(f"body: {r.text[:400]}")
    results["case5"] = ("FAIL", f"manifest status={r.status_code}")
else:
    content = r.json().get("content", "")
    has_pixel = "pixel_16bit" in content
    has_25d = "2_5d" in content
    dash_count = content.count("`—`")
    log(f"pixel_16bit present: {has_pixel}, 2_5d present: {has_25d}, dash placeholders: {dash_count}")
    log(f"size: {len(content)}B")
    # Expected: 2 values present, 7 missing → 7 `—` placeholders
    if has_pixel and has_25d and dash_count >= 7:
        results["case5"] = ("PASS", f"partial rendered: pixel_16bit + 2_5d + {dash_count} `—` placeholders")
    else:
        log(f"content preview:\n{content[:1000]}")
        results["case5"] = ("FAIL", f"pixel={has_pixel} 2_5d={has_25d} dashes={dash_count}")

# ── CASE 6: No style_params (regression) ──────────────
log("\n=== CASE 6: No style_params ===")
r = post("/create", {
    "title": "StyleTestC",
    "genre": "rpg",
    "age_era_year": 2015,
    "complexity": 3,
    "age_target": "T",
})
log(f"status={r.status_code}")
if r.status_code != 200:
    log(f"body: {r.text[:400]}")
    results["case6"] = ("FAIL", f"status={r.status_code}")
else:
    results["case6"] = ("PASS", f"build_id={r.json().get('build_id')}")

# ── CASE 7: Oversize string sanitization ──────────────
log("\n=== CASE 7: Oversize string sanitization ===")
oversize_val = "A" + ("x" * 200)
r = post("/create", {
    "title": "StyleTestD",
    "genre": "rpg",
    "age_era_year": 2015,
    "complexity": 3,
    "age_target": "T",
    "style_params": {"graphic_style": oversize_val},
})
log(f"status={r.status_code}")
if r.status_code == 200:
    build_id_D = r.json().get("build_id")
    results["case7"] = ("PASS", f"no 500, build_id={build_id_D}")
else:
    log(f"body: {r.text[:400]}")
    results["case7"] = ("FAIL", f"status={r.status_code}")

# ── CASE 8: Non-str sanitization ──────────────────────
log("\n=== CASE 8: Non-str value sanitization ===")
r = post("/create", {
    "title": "StyleTestE",
    "genre": "rpg",
    "age_era_year": 2015,
    "complexity": 3,
    "age_target": "T",
    "style_params": {"dimension": 42, "graphic_style": True},
})
log(f"status={r.status_code}")
if r.status_code == 200:
    results["case8"] = ("PASS", f"no 500, build_id={r.json().get('build_id')}")
else:
    log(f"body: {r.text[:400]}")
    results["case8"] = ("FAIL", f"status={r.status_code}")

# ── CASE 9: Phase 9 regression (1997 anchor) ──────────
log("\n=== CASE 9: 1997 anchor regression ===")
r = post("/create", {
    "title": "StyleTestF",
    "genre": "rpg",
    "age_era_year": 1997,
    "complexity": 3,
    "age_target": "T",
})
log(f"POST /create 1997 status={r.status_code}")
assert r.status_code == 200, f"Case9a FAIL status={r.status_code}"
build_id_F = r.json().get("build_id")
r = post("/advance", {"build_id": build_id_F})
log(f"POST /advance 1997 status={r.status_code}")
assert r.status_code == 200, f"Case9b FAIL status={r.status_code}"
r = get(f"/file/{build_id_F}/docs/NARRATIVE_VAULT_BIBLE.md")
log(f"GET bible status={r.status_code}")
if r.status_code != 200:
    log(f"body: {r.text[:400]}")
    results["case9"] = ("FAIL", f"bible status={r.status_code}")
else:
    content = r.json().get("content", "")
    has_1997 = "1997" in content
    log(f"1997 anchor present: {has_1997}, bible size={len(content)}B")
    if has_1997:
        results["case9"] = ("PASS", "1997 anchor present in bible")
    else:
        results["case9"] = ("FAIL", "1997 not in bible")

# ── CASE 10: Watchdog health ──────────────────────────
log("\n=== CASE 10: GET /watchdog/health ===")
r = get("/watchdog/health")
log(f"status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    ok = d.get("ok")
    log(f"ok={ok}")
    if ok is True:
        results["case10"] = ("PASS", "ok:true")
    else:
        results["case10"] = ("FAIL", f"ok={ok}")
else:
    results["case10"] = ("FAIL", f"status={r.status_code}")

# ── SUMMARY ──
log("\n" + "=" * 60)
log("SUMMARY")
log("=" * 60)
passed = 0
failed = 0
for k in sorted(results.keys(), key=lambda x: int(x[4:])):
    status, note = results[k]
    mark = "✅" if status == "PASS" else "❌"
    log(f"{mark} {k}: {status} — {note}")
    if status == "PASS":
        passed += 1
    else:
        failed += 1
log(f"\nTotal: {passed}/{passed+failed} passed")
sys.exit(0 if failed == 0 else 1)
