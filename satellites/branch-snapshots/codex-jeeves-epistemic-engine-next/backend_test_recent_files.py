"""
Galaxy Studio /status `recent_files` field test
Covers: create -> status (pre-advance) -> advance -> status (post-advance) -> regression
"""
import json
import sys
import time
import requests

BASE = "http://localhost:8001"
API = f"{BASE}/api"

PASS = 0
FAIL = 0
FAILURES = []


def check(cond: bool, name: str, extra: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} -- {extra}")
        print(f"  [FAIL] {name} -- {extra}")


def step(n, label):
    print(f"\n=== STEP {n}: {label} ===")


# 1
step(1, "POST /galaxy-studio/create RecentFilesTest")
payload = {"title": "RecentFilesTest", "genre": "rpg", "complexity": 3, "age_target": "T"}
r = requests.post(f"{API}/galaxy-studio/create", json=payload, timeout=60)
print(f"  HTTP {r.status_code}")
check(r.status_code == 200, "create returns 200", f"got {r.status_code}: {r.text[:200]}")
data = r.json() if r.status_code == 200 else {}
build_id = data.get("build_id")
print(f"  build_id = {build_id}")
check(bool(build_id), "create returns build_id", str(data)[:200])

if not build_id:
    print("\n!!! Cannot continue without build_id !!!")
    sys.exit(1)

# 2
step(2, "GET /galaxy-studio/status/{build_id} BEFORE any /advance")
r = requests.get(f"{API}/galaxy-studio/status/{build_id}", timeout=30)
print(f"  HTTP {r.status_code}")
check(r.status_code == 200, "pre-advance status returns 200")
pre = r.json() if r.status_code == 200 else {}
check("recent_files" in pre, "pre-advance response includes `recent_files` key")
rf_pre = pre.get("recent_files")
check(isinstance(rf_pre, list), "pre-advance `recent_files` is a list", f"got {type(rf_pre).__name__}")
print(f"  pre-advance recent_files length = {len(rf_pre) if isinstance(rf_pre, list) else 'N/A'} (empty is OK)")

# 3
step(3, "POST /galaxy-studio/advance/{build_id}  (ONE batch = 10 phases)")
r = requests.post(f"{API}/galaxy-studio/advance", json={"build_id": build_id}, timeout=600)
print(f"  HTTP {r.status_code}")
check(r.status_code == 200, "advance returns 200", r.text[:300])
adv = r.json() if r.status_code == 200 else {}
print(f"  advance response keys: {list(adv.keys())[:12]}")
time.sleep(1)

# 4
step(4, "GET /galaxy-studio/status/{build_id} AFTER one advance")
r = requests.get(f"{API}/galaxy-studio/status/{build_id}", timeout=30)
print(f"  HTTP {r.status_code}")
check(r.status_code == 200, "post-advance status returns 200")
post = r.json() if r.status_code == 200 else {}

rf = post.get("recent_files")
check(isinstance(rf, list), "post-advance `recent_files` is a list", f"got {type(rf).__name__}")
if isinstance(rf, list):
    check(len(rf) <= 12, f"recent_files length <= 12 (got {len(rf)})")
    check(len(rf) > 0, f"recent_files length > 0 (got {len(rf)})",
          "Note: vault flushes may empty in-mem files mid-build")

    shape_ok = True
    shape_details = []
    for i, entry in enumerate(rf):
        if not isinstance(entry, dict):
            shape_ok = False
            shape_details.append(f"entry[{i}] is {type(entry).__name__}")
            continue
        keys = set(entry.keys())
        missing = {"path", "size", "ext"} - keys
        if missing:
            shape_ok = False
            shape_details.append(f"entry[{i}] missing {missing}, has {keys}")
            continue
        if not isinstance(entry["path"], str) or not entry["path"]:
            shape_ok = False
            shape_details.append(f"entry[{i}].path invalid: {entry['path']!r}")
        if not isinstance(entry["size"], int) or entry["size"] < 0:
            shape_ok = False
            shape_details.append(f"entry[{i}].size invalid: {entry['size']!r}")
        if not isinstance(entry["ext"], str):
            shape_ok = False
            shape_details.append(f"entry[{i}].ext not a str: {entry['ext']!r}")
    check(shape_ok, "every recent_files entry has {path:str-nonempty, size:int>=0, ext:str}",
          " | ".join(shape_details[:3]))

    print("\n  First 3 recent_files entries:")
    for e in rf[:3]:
        print(f"    {json.dumps(e)}")

# 5
step(5, "Regression: required fields present on /status response")
required = [
    "build_id", "title", "status", "current_phase", "total_phases",
    "current_batch", "total_batches", "batch_name", "file_count",
    "completed_phases", "phase_log", "bg_progress",
]
for f in required:
    check(f in post, f"/status includes `{f}`")

print(f"\n  Sample regression values:")
for f in required:
    val = post.get(f)
    sval = str(val)
    if len(sval) > 80:
        sval = sval[:77] + "..."
    print(f"    {f}: {sval}")

# 6
step(6, "GET /api/health regression")
r = requests.get(f"{API}/health", timeout=15)
check(r.status_code == 200, "/api/health returns 200")
hdata = r.json() if r.status_code == 200 else {}
check(hdata.get("status") == "healthy", "/api/health status == 'healthy'", str(hdata)[:200])

print("\n" + "=" * 60)
print(f"TOTAL: PASS={PASS}  FAIL={FAIL}")
if FAILURES:
    print("\nFAILURES:")
    for f in FAILURES:
        print(f"  - {f}")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
