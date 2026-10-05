"""
Backend test: Galaxy Studio Narrative Vault + Era-by-Age integration.
Tests against public EXPO_PUBLIC_BACKEND_URL.
"""
import os
import json
import time
import requests
from pathlib import Path

# Load backend URL
env_path = Path("/app/frontend/.env")
BACKEND_URL = None
for line in env_path.read_text().splitlines():
    if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
        BACKEND_URL = line.split("=", 1)[1].strip()
        break
if not BACKEND_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL not found in /app/frontend/.env")

BASE = BACKEND_URL.rstrip("/") + "/api/galaxy-studio"
print(f"[INFO] Testing Galaxy Studio at: {BASE}\n")

REQUIRED_VISION_FILES = [
    "docs/NARRATIVE_VAULT_BIBLE.md",
    "docs/SPECIALIZED_TOPIC_DIGEST.md",
    "docs/NARRATIVE_DIFFERENTIATION_MANDATE.md",
    "docs/swarm_narrative_feed.json",
]

results = {"passed": [], "failed": []}
builds_created = {}  # {label: build_id}


def _record(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name} :: {detail}")
    (results["passed"] if ok else results["failed"]).append({"name": name, "detail": detail})


def create_build(title, genre, age_era_year=None, complexity=3, age_target="T"):
    payload = {"title": title, "genre": genre, "complexity": complexity, "age_target": age_target}
    if age_era_year is not None:
        payload["age_era_year"] = age_era_year
    r = requests.post(f"{BASE}/create", json=payload, timeout=60)
    return r


def advance(build_id):
    r = requests.post(f"{BASE}/advance", json={"build_id": build_id}, timeout=180)
    return r


def get_files(build_id):
    r = requests.get(f"{BASE}/files/{build_id}", timeout=60)
    return r


def get_file(build_id, path):
    r = requests.get(f"{BASE}/file/{build_id}/{path}", timeout=60)
    return r


# ─── Test 1: Payload + 200, NarrativeTest1 year=1997 ───
print("=" * 70)
print("TEST 1: POST /create with NarrativeTest1 age_era_year=1997")
print("=" * 70)
r = create_build("NarrativeTest1", "rpg", age_era_year=1997)
if r.status_code == 200:
    data = r.json()
    bid = data.get("build_id")
    if bid:
        builds_created["1997"] = bid
        _record("T1 /create 1997 → 200 with build_id", True, f"build_id={bid[:16]}")
    else:
        _record("T1 /create 1997", False, f"no build_id in {data}")
else:
    _record("T1 /create 1997 200", False, f"HTTP {r.status_code}: {r.text[:300]}")

# ─── Test 2: Year variations ───
print("\n" + "=" * 70)
print("TEST 2: Year variations 1985, 2015, 2025, 2030")
print("=" * 70)
for yr in [1985, 2015, 2025, 2030]:
    r = create_build(f"NarrativeYear{yr}", "rpg", age_era_year=yr)
    if r.status_code == 200 and r.json().get("build_id"):
        bid = r.json()["build_id"]
        builds_created[str(yr)] = bid
        _record(f"T2 /create year={yr} → 200", True, f"build_id={bid[:16]}")
    else:
        _record(f"T2 /create year={yr}", False, f"HTTP {r.status_code}: {r.text[:200]}")

# ─── Test 3: Clamping — 1970, 2099, no year ───
print("\n" + "=" * 70)
print("TEST 3: Clamping edge cases (1970, 2099, none)")
print("=" * 70)
# 1970 (below min)
r = create_build("NarrativeClampLow", "rpg", age_era_year=1970)
if r.status_code == 200 and r.json().get("build_id"):
    _record("T3 /create year=1970 (below clamp)", True, f"build_id={r.json()['build_id'][:16]}")
else:
    _record("T3 /create year=1970", False, f"HTTP {r.status_code}: {r.text[:200]}")

# 2099 (above max)
r = create_build("NarrativeClampHigh", "rpg", age_era_year=2099)
if r.status_code == 200 and r.json().get("build_id"):
    _record("T3 /create year=2099 (above clamp)", True, f"build_id={r.json()['build_id'][:16]}")
else:
    _record("T3 /create year=2099", False, f"HTTP {r.status_code}: {r.text[:200]}")

# No year (backward compat)
r = create_build("NarrativeNoYear", "rpg", age_era_year=None)
if r.status_code == 200 and r.json().get("build_id"):
    _record("T3 /create year=None (backward compat)", True, f"build_id={r.json()['build_id'][:16]}")
else:
    _record("T3 /create year=None", False, f"HTTP {r.status_code}: {r.text[:200]}")

# ─── Test 4: /advance once for 1997 & 2025 builds, verify vision files generated ───
print("\n" + "=" * 70)
print("TEST 4: /advance once (batch 1) → verify vision files for 1997 & 2025 builds")
print("=" * 70)

advance_targets = {k: builds_created.get(k) for k in ("1997", "2025") if builds_created.get(k)}

file_sizes_per_build = {}

for label, bid in advance_targets.items():
    print(f"\n-- Advancing build {label} ({bid[:16]}) --")
    r = advance(bid)
    if r.status_code != 200:
        _record(f"T4 /advance {label}", False, f"HTTP {r.status_code}: {r.text[:300]}")
        continue
    adv_data = r.json()
    _record(f"T4 /advance {label} → 200", True,
            f"current_phase={adv_data.get('current_phase')}, file_count={adv_data.get('file_count')}")

    # small wait in case files are async-attached (they are synchronous in _phase_vision)
    time.sleep(1)

    r = get_files(bid)
    if r.status_code != 200:
        _record(f"T4 /files {label}", False, f"HTTP {r.status_code}: {r.text[:300]}")
        continue
    files_data = r.json()
    paths = {f["path"]: f["size"] for f in files_data.get("files", [])}
    file_sizes_per_build[label] = {p: paths.get(p, 0) for p in REQUIRED_VISION_FILES}

    for required in REQUIRED_VISION_FILES:
        if required in paths and paths[required] > 0:
            _record(f"T4 {label}: {required} exists size>{paths[required]}B", True, "")
        else:
            _record(f"T4 {label}: {required}", False,
                    f"missing or empty (size={paths.get(required, 'N/A')})")

# ─── Test 5: Year-1997 content check ───
print("\n" + "=" * 70)
print("TEST 5: 1997 NARRATIVE_VAULT_BIBLE.md content check")
print("=" * 70)

if builds_created.get("1997"):
    bid = builds_created["1997"]
    r = get_file(bid, "docs/NARRATIVE_VAULT_BIBLE.md")
    if r.status_code == 200:
        content = r.json().get("content", "")
        print(f"   Bible size: {len(content)} bytes, {content.count(chr(10))+1} lines")
        snippet_lines = [ln for ln in content.split("\n") if "Era anchor" in ln or "Flavor tags" in ln or "Era-by-Age" in ln]
        print("   Snippet:\n     " + "\n     ".join(snippet_lines[:5]))

        has_1997 = "1997" in content
        canonical_anchors = ["Final Fantasy VII", "CD-ROM", "cinematic RPGs"]
        has_anchor = any(a in content for a in canonical_anchors)
        flavor_tags = ["floppy-disk", "dial-up", "early-3D-low-poly"]
        has_flavor = any(f in content for f in flavor_tags)

        _record("T5 1997 bible contains '1997'", has_1997, "" if has_1997 else "missing")
        _record("T5 1997 bible has ≥1 anchor (FFVII/CD-ROM/cinematic RPGs)", has_anchor,
                f"found: {[a for a in canonical_anchors if a in content]}")
        _record("T5 1997 bible has ≥1 flavor tag (floppy-disk/dial-up/early-3D)", has_flavor,
                f"found: {[f for f in flavor_tags if f in content]}")
    else:
        _record("T5 1997 GET bible", False, f"HTTP {r.status_code}: {r.text[:200]}")
else:
    _record("T5 1997 build", False, "no 1997 build_id available")

# ─── Test 6: Year-2025 content check ───
print("\n" + "=" * 70)
print("TEST 6: 2025 NARRATIVE_VAULT_BIBLE.md content check")
print("=" * 70)

if builds_created.get("2025"):
    bid = builds_created["2025"]
    r = get_file(bid, "docs/NARRATIVE_VAULT_BIBLE.md")
    if r.status_code == 200:
        content = r.json().get("content", "")
        print(f"   Bible size: {len(content)} bytes, {content.count(chr(10))+1} lines")
        snippet_lines = [ln for ln in content.split("\n") if "Era anchor" in ln or "Flavor tags" in ln or "Era-by-Age" in ln]
        print("   Snippet:\n     " + "\n     ".join(snippet_lines[:5]))

        has_2025 = "2025" in content
        anchors_2020s = ["Generative companion AI", "cross-play", "live-service fatigue", "haptic", "ray-tracing"]
        has_anchor = any(a in content for a in anchors_2020s)

        _record("T6 2025 bible contains '2025'", has_2025, "" if has_2025 else "missing")
        _record("T6 2025 bible has ≥1 2020s anchor", has_anchor,
                f"found: {[a for a in anchors_2020s if a in content]}")
    else:
        _record("T6 2025 GET bible", False, f"HTTP {r.status_code}: {r.text[:200]}")
else:
    _record("T6 2025 build", False, "no 2025 build_id available")

# ─── Test 7: swarm_narrative_feed.json schema ───
print("\n" + "=" * 70)
print("TEST 7: swarm_narrative_feed.json schema")
print("=" * 70)

if builds_created.get("1997"):
    bid = builds_created["1997"]
    r = get_file(bid, "docs/swarm_narrative_feed.json")
    if r.status_code == 200:
        raw = r.json().get("content", "")
        try:
            feed = json.loads(raw)
        except Exception as e:
            feed = None
            _record("T7 feed JSON parse", False, f"parse error: {e}; snippet: {raw[:200]}")
        if feed is not None:
            required_keys = {
                "build_id": str,
                "title": str,
                "genre_bucket": str,
                "age_era_year": (int, type(None)),
                "era_anchor": (str, type(None)),
                "era_flavor": list,
                "canonical_refs": list,
                "quest_menu": list,
                "arc_menu": list,
                "technique_menu": list,
                "specialized_picks": dict,
                "mandate": str,
            }
            missing = [k for k in required_keys if k not in feed]
            if missing:
                _record("T7 feed keys complete", False, f"missing: {missing}")
            else:
                _record("T7 feed keys complete", True, f"all {len(required_keys)} keys present")
                # Type validation
                bad_types = []
                for k, expected in required_keys.items():
                    if not isinstance(feed[k], expected):
                        bad_types.append(f"{k}: {type(feed[k]).__name__}")
                if bad_types:
                    _record("T7 feed type correctness", False, f"bad types: {bad_types}")
                else:
                    _record("T7 feed type correctness", True, "all types correct")

                # Content sanity
                print(f"   feed.age_era_year = {feed.get('age_era_year')}")
                print(f"   feed.era_anchor   = {feed.get('era_anchor')}")
                print(f"   feed.era_flavor   = {feed.get('era_flavor')}")
                print(f"   feed.canonical_refs[0:2] = {feed.get('canonical_refs', [])[:2]}")
    else:
        _record("T7 feed GET", False, f"HTTP {r.status_code}: {r.text[:200]}")
else:
    _record("T7 feed build", False, "no 1997 build_id available")

# ─── Test 8: Regression: watchdog/health + status ───
print("\n" + "=" * 70)
print("TEST 8: Regression — /watchdog/health and /status")
print("=" * 70)

r = requests.get(f"{BASE}/watchdog/health", timeout=30)
if r.status_code == 200:
    wd = r.json()
    ok_flag = wd.get("ok", False)
    _record("T8 /watchdog/health 200 ok=true", ok_flag, f"ok={ok_flag}, keys={list(wd.keys())[:8]}")
else:
    _record("T8 /watchdog/health 200", False, f"HTTP {r.status_code}: {r.text[:200]}")

# Status for the 1997 build (or any created)
test_bid = builds_created.get("1997") or next(iter(builds_created.values()), None)
if test_bid:
    r = requests.get(f"{BASE}/status/{test_bid}", timeout=30)
    if r.status_code == 200:
        st = r.json()
        _record("T8 /status/{build_id} 200", True,
                f"status={st.get('status')}, phase={st.get('current_phase')}, files={st.get('file_count')}")
    else:
        _record("T8 /status/{build_id} 200", False, f"HTTP {r.status_code}: {r.text[:200]}")
else:
    _record("T8 /status", False, "no build_id available")

# ─── Summary ───
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Total PASS: {len(results['passed'])}")
print(f"Total FAIL: {len(results['failed'])}")
print(f"\nBuilds created: {len(builds_created)} → {[(k, v[:12]) for k, v in builds_created.items()]}")

if file_sizes_per_build:
    print("\nNarrative-vault doc sizes per build:")
    for lbl, sz in file_sizes_per_build.items():
        print(f"  Build {lbl}:")
        for p, s in sz.items():
            print(f"    {p}: {s} bytes")

if results["failed"]:
    print("\nFAILED cases:")
    for f in results["failed"]:
        print(f"  - {f['name']}: {f['detail']}")

print("\nDone.")
