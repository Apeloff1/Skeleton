"""
APK Inspector backend review test — verifies new endpoints and regression
on tools/invoke pipeline.

Run with:  python /app/backend_test_apk_inspector.py
"""
from __future__ import annotations
import json, sys
import requests

BASE_URL = "https://gemini-game-craft.preview.emergentagent.com"
API = f"{BASE_URL}/api"

results: list[dict] = []

def record(name: str, ok: bool, status, info: str):
    flag = "PASS" if ok else "FAIL"
    print(f"{flag}  [{status}] {name:<55} -> {info}")
    results.append({"name": name, "ok": ok, "status": status, "info": info})


def post(path, body, timeout=30):
    try:
        r = requests.post(f"{API}{path}", json=body, timeout=timeout)
        try: j = r.json()
        except Exception: j = r.text
        return r.status_code, j
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def get(path, timeout=20, stream=False):
    try:
        r = requests.get(f"{API}{path}", timeout=timeout, stream=stream)
        if stream:
            return r.status_code, r, dict(r.headers)
        try: j = r.json()
        except Exception: j = r.text
        return r.status_code, j, dict(r.headers)
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", {}


# ============================================================
# 1. GET /api/binary/toolchain — Toolchain probe
# ============================================================
print("\n=== 1. GET /api/binary/toolchain ===")
st, j, _ = get("/binary/toolchain", timeout=30)
checks = []
if st == 200 and isinstance(j, dict):
    checks = [
        ("have_full_toolchain==True", j.get("have_full_toolchain") is True),
        ("build_tools_version=='34.0.0'", j.get("build_tools_version") == "34.0.0"),
        ("android_jar_exists==True", j.get("android_jar_exists") is True),
        ("debug_keystore_exists==True", j.get("debug_keystore_exists") is True),
        ("javac_available==True", j.get("javac_available") is True),
        ("qemu_path is set", bool(j.get("qemu_path"))),
        ("aapt2.available", j.get("tools", {}).get("aapt2", {}).get("available") is True),
        ("d8.available", j.get("tools", {}).get("d8", {}).get("available") is True),
        ("zipalign.available", j.get("tools", {}).get("zipalign", {}).get("available") is True),
        ("apksigner.available", j.get("tools", {}).get("apksigner", {}).get("available") is True),
    ]
ok = bool(checks) and all(v for _, v in checks)
detail = ", ".join(f"{k}={v}" for k, v in checks) if checks else json.dumps(j)[:300]
record("binary.toolchain", ok, st, detail)


# ============================================================
# 2. GET /api/binary/inspect/real_runnable_v1
# ============================================================
print("\n=== 2. GET /api/binary/inspect/real_runnable_v1 ===")
st, j, _ = get("/binary/inspect/real_runnable_v1", timeout=30)
checks = []
if st == 200 and isinstance(j, dict):
    s = j.get("structure", {}) or {}
    sig = j.get("signature", {}) or {}
    diag = j.get("diagnostic", []) or []
    checks = [
        ("is_installable_apk==True", j.get("is_installable_apk") is True),
        ("has_classes_dex", s.get("has_classes_dex") is True),
        ("has_main_activity", s.get("has_main_activity") is True),
        ("has_launcher_intent", s.get("has_launcher_intent") is True),
        ("manifest_is_binary_xml", s.get("manifest_is_binary_xml") is True),
        ("has_resources_arsc", s.get("has_resources_arsc") is True),
        ("dex_magic=='dex'", s.get("dex_magic") == "dex"),
        ("dex_version=='037'", s.get("dex_version") == "037"),
        ("signature.verifies==True", sig.get("verifies") is True),
        ("diagnostic is list", isinstance(diag, list) and len(diag) > 0),
        ("diagnostic all start with ✓",
            all(isinstance(b, str) and b.startswith("✓") for b in diag)),
    ]
ok = bool(checks) and all(v for _, v in checks)
detail = ", ".join(f"{k}={v}" for k, v in checks) if checks else json.dumps(j)[:400]
record("binary.inspect.real_runnable_v1", ok, st, detail)


# ============================================================
# 3. POST /api/binary/rebuild/real_runnable_v1
# ============================================================
print("\n=== 3. POST /api/binary/rebuild/real_runnable_v1 ===")
st, j = post("/binary/rebuild/real_runnable_v1", {}, timeout=180)
checks = []
arts = []
if st == 200 and isinstance(j, dict):
    arts = j.get("artifacts", []) or []
    apk_art = next((a for a in arts if a.get("kind") == "apk"), None)
    zip_art = next((a for a in arts if a.get("kind") == "zip"), None)
    checks = [
        ("rebuilt==True", j.get("rebuilt") is True),
        ("artifacts has zip", zip_art is not None),
        ("artifacts has apk", apk_art is not None),
        ("artifacts count==2", len(arts) == 2),
        ("apk.is_real_apk==True", apk_art is not None and apk_art.get("is_real_apk") is True),
    ]
ok = bool(checks) and all(v for _, v in checks)
detail = (f"artifacts={len(arts)}, kinds={[a.get('kind') for a in arts]}, "
          f"is_real_apk={[a.get('is_real_apk') for a in arts if a.get('kind')=='apk']}")
record("binary.rebuild.real_runnable_v1", ok, st,
       detail if ok else json.dumps(j)[:400])


# ============================================================
# 4. POST /api/binary/package — demo_apk_real
# ============================================================
print("\n=== 4. POST /api/binary/package (demo_apk_real) ===")
st, j = post("/binary/package",
             {"build_id": "demo_apk_real", "kinds": ["zip", "apk"]},
             timeout=180)
checks = []
arts = []
if st == 200 and isinstance(j, dict):
    arts = j.get("artifacts", []) or []
    apk_art = next((a for a in arts if a.get("kind") == "apk"), None)
    checks = [
        ("HTTP 200", st == 200),
        ("artifacts count==2", len(arts) == 2),
        ("has zip artifact", any(a.get("kind") == "zip" for a in arts)),
        ("has apk artifact", apk_art is not None),
        ("apk.is_real_apk==True", apk_art is not None and apk_art.get("is_real_apk") is True),
    ]
ok = bool(checks) and all(v for _, v in checks)
detail = (f"artifacts={len(arts)}, kinds={[a.get('kind') for a in arts]}, "
          f"is_real_apk={[a.get('is_real_apk') for a in arts if a.get('kind')=='apk']}")
record("binary.package.demo_apk_real", ok, st,
       detail if ok else json.dumps(j)[:400])


# Also confirm missing build_id returns 404
st404, j404 = post("/binary/package",
                    {"build_id": "definitely_does_not_exist_xyz", "kinds": ["zip"]},
                    timeout=30)
ok404 = (st404 == 404)
record("binary.package.missing_build_id_404", ok404, st404,
       f"got_404={ok404}")


# ============================================================
# 5. GET /api/binary/verify/real_runnable_v1
# ============================================================
print("\n=== 5. GET /api/binary/verify/real_runnable_v1 ===")
st, j, _ = get("/binary/verify/real_runnable_v1", timeout=30)
checks = []
if st == 200 and isinstance(j, dict):
    checks = [
        ("verifies==True", j.get("verifies") is True),
        ("exit_code==0", j.get("exit_code") == 0),
        ("available==True", j.get("available") is True),
    ]
ok = bool(checks) and all(v for _, v in checks)
detail = ", ".join(f"{k}={v}" for k, v in checks) if checks else json.dumps(j)[:300]
record("binary.verify.real_runnable_v1", ok, st, detail)


# ============================================================
# 6. GET /api/binary/download/real_runnable_v1/apk
# ============================================================
print("\n=== 6. GET /api/binary/download/real_runnable_v1/apk ===")
st, resp, hdrs = get("/binary/download/real_runnable_v1/apk",
                      timeout=60, stream=True)
ct = (hdrs.get("content-type") or hdrs.get("Content-Type") or "")
size = 0
first_two = b""
if st == 200:
    try:
        body = resp.content
        size = len(body)
        first_two = body[:2]
    except Exception as e:
        size = -1
checks = [
    ("HTTP 200", st == 200),
    ("Content-Type apk", "vnd.android.package-archive" in ct),
    ("magic == PK", first_two == b"PK"),
    ("size >= 5000", size >= 5000),
]
ok = all(v for _, v in checks)
record("binary.download.real_runnable_v1.apk", ok, st,
       f"ct='{ct}', size={size}, magic={first_two!r}")


# ============================================================
# 7. REGRESSION CHECK — re-test 8 tools/invoke calls (smoke)
# ============================================================
print("\n=== 7. REGRESSION: tools/invoke smoke ===")

# a) web_search (DDG)
st, j = post("/tools/invoke",
             {"tool": "web_search",
              "params": {"query": "fastapi 2026 best practices", "max_results": 3}},
             timeout=60)
ok = (st == 200 and isinstance(j, dict) and j.get("ok") is True
      and isinstance(j.get("results"), list) and len(j["results"]) > 0)
record("regression.tools.web_search", ok, st,
       f"results={len(j.get('results', [])) if isinstance(j, dict) else 'N/A'}"
       if ok else json.dumps(j)[:300])

# b) jeeves_consult
st, j = post("/tools/invoke",
             {"tool": "jeeves_consult",
              "params": {"context": "lesson_intro", "topic": "react native"}},
             timeout=30)
catch = j.get("catchphrase", "") if isinstance(j, dict) else ""
ok = (st == 200 and bool(catch))
record("regression.tools.jeeves_consult", ok, st,
       f"catchphrase='{catch[:60]}'" if ok else json.dumps(j)[:300])

# c) package_build  (internally calls binary_builder)
st, j = post("/tools/invoke",
             {"tool": "package_build",
              "params": {"build_id": "demo_apk_real", "kinds": ["zip", "apk"]}},
             timeout=180)
arts = j.get("artifacts", []) if isinstance(j, dict) else []
has_real_apk = any(a.get("kind") == "apk" and a.get("is_real_apk") is True for a in arts)
ok = (st == 200 and isinstance(j, dict) and j.get("ok") is True
      and len(arts) == 2 and has_real_apk)
record("regression.tools.package_build", ok, st,
       f"artifacts={len(arts)}, real_apk={has_real_apk}"
       if ok else json.dumps(j)[:400])

# d) Quick mongo_query smoke (sanity)
st, j = post("/tools/invoke",
             {"tool": "mongo_query",
              "params": {"collection": "jeeves_persona", "filter": {}, "limit": 2}},
             timeout=30)
ok = (st == 200 and isinstance(j, dict) and j.get("ok") is True
      and isinstance(j.get("rows"), list))
record("regression.tools.mongo_query", ok, st,
       f"rows={len(j.get('rows', [])) if isinstance(j, dict) else 'N/A'}"
       if ok else json.dumps(j)[:200])

# e) llm_chat smoke
st, j = post("/tools/invoke",
             {"tool": "llm_chat",
              "params": {"prompt": "say hi in 3 words", "model": "gpt-4o"}},
             timeout=60)
ok = (st == 200 and isinstance(j, dict) and j.get("ok") is True
      and bool(j.get("response")))
record("regression.tools.llm_chat", ok, st,
       f"response='{(j.get('response') or '')[:60]}'" if ok else json.dumps(j)[:200])

# f) run_code smoke
st, j = post("/tools/invoke",
             {"tool": "run_code",
              "params": {"language": "python", "code": "print('hi')"}},
             timeout=30)
ok = (st == 200 and isinstance(j, dict) and j.get("ok") is True
      and "hi" in (j.get("stdout") or ""))
record("regression.tools.run_code", ok, st,
       f"stdout={(j.get('stdout') or '').strip()!r}"
       if ok else json.dumps(j)[:200])

# g) compile_code smoke
st, j = post("/tools/invoke",
             {"tool": "compile_code",
              "params": {"language": "c", "code": "int main(){return 0;}"}},
             timeout=30)
ok = (st == 200 and isinstance(j, dict) and j.get("ok") is True)
record("regression.tools.compile_code", ok, st,
       f"exit_code={j.get('exit_code') if isinstance(j, dict) else 'N/A'}"
       if ok else json.dumps(j)[:200])

# h) vault_query smoke
st, j = post("/tools/invoke",
             {"tool": "vault_query",
              "params": {"topic": "pathfinding", "limit": 3}},
             timeout=30)
ok = (st == 200 and isinstance(j, dict)
      and (j.get("matches") is not None or (j.get("ok") and j.get("rows"))))
record("regression.tools.vault_query", ok, st,
       (f"matches_keys={list(j['matches'].keys())[:3]}" if isinstance(j, dict) and j.get('matches')
        else f"rows={len(j.get('rows', [])) if isinstance(j, dict) else 'N/A'}")
       if ok else json.dumps(j)[:200])


# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 70)
total  = len(results)
passed = sum(1 for r in results if r["ok"])
print(f"SUMMARY: {passed}/{total} passed")
for r in results:
    if not r["ok"]:
        print(f"  FAIL {r['name']:<55} [{r['status']}] {r['info'][:400]}")
print("=" * 70)
sys.exit(0 if passed == total else 1)
