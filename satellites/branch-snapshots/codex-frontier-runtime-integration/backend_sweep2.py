#!/usr/bin/env python3
"""Follow-up corrections sweep:
   - Group B: use real class id ds_complete (not cs100)
   - Group C: pick a book and verify single-book endpoint
   - Group D: use a fresh build_id, complete the build, files, vault zip
   - Group G: check rid in telemetry log after a flurry of rid-bearing requests
"""
import json, time, uuid, sys
import requests

BASE = "https://gemini-game-craft.preview.emergentagent.com/api"
S = requests.Session()

RESULTS = []
def call(method, path, num, group, json_body=None, timeout=30, expect=200, notes=""):
    t0 = time.time()
    try:
        r = S.request(method, f"{BASE}{path}", json=json_body, timeout=timeout, headers={"X-Request-Id": f"sweepX-{uuid.uuid4().hex[:8]}"})
        status = r.status_code
        body_text = r.text
        body_json = None
        try:
            body_json = r.json()
        except Exception:
            pass
    except Exception as e:
        status = -1; body_text = repr(e); body_json = None
    ms = int((time.time()-t0)*1000)
    ok = (status == expect) if isinstance(expect, int) else (status in expect)
    head = "\n".join(body_text.splitlines()[:5])[:600]
    RESULTS.append({"group":group,"num":num,"endpoint":path,"method":method,"status":status,"ms":ms,"ok":ok,"head":head,"notes":notes})
    print(f"{num:>3} {method:<5} {path:<70} {status:>5} {ms:>6}ms {'Y' if ok else 'N'}  {notes}")
    return body_json, body_text, status

# ---- B (corrected) ----
print("\n== Group B (corrected — class=ds_complete) ==")
call("GET", "/curriculum/classes/ds_complete", 8.1, "B")
call("GET", "/curriculum/classes/ds_complete/week/1", 9.1, "B")
call("GET", "/curriculum/classes/ds_complete/week/15", 10.1, "B")
call("GET", "/curriculum/classes/ds_complete/week/1/quiz", 11.1, "B")
call("GET", "/curriculum/classes/ds_complete/week/99", 12.1, "B", expect=404)

# ---- C (single book) ----
print("\n== Group C — pick a book ==")
lib, _, _ = call("GET", "/academy/reading-library?page=1&limit=20", 14.1, "C")
book_id = None
if isinstance(lib, dict):
    books = lib.get("books") or lib.get("items") or lib.get("data") or []
    if isinstance(books, list) and books:
        first = books[0]
        book_id = first.get("book_id") or first.get("id") or first.get("_id")
        print(f"   picked book_id={book_id}; keys={list(first.keys())[:10]}")
if book_id:
    call("GET", f"/academy/reading-library/{book_id}", 18, "C", notes=f"book_id={book_id}")

# ---- D — fresh build ----
print("\n== Group D — fresh build cycle ==")
created, _, _ = call("POST", "/galaxy-studio/create", 24.1, "D",
                     json_body={"title":"Sweep","genre":"rpg","complexity":"intermediate","target_files":48000})
bid = (created or {}).get("build_id")
print(f"   build_id = {bid}")
if bid:
    status_body, _, _ = call("GET", f"/galaxy-studio/status/{bid}", 25, "D")
    if isinstance(status_body, dict):
        required = ["progress_percent","phase_label","phase","target_files","eta_seconds","errors"]
        missing = [k for k in required if k not in status_body]
        print(f"   aliases: missing={missing}")
        print(f"   target_files={status_body.get('target_files')!r}  progress_percent={status_body.get('progress_percent')!r}  phase_label={status_body.get('phase_label')!r}  eta_seconds={status_body.get('eta_seconds')!r}")
        # floor check
        tf = status_body.get("target_files")
        if tf != 48000:
            print(f"   ❌ FLOOR REGRESSION: target_files={tf} != 48000")
        else:
            print(f"   ✅ target_files=48000 (floor holds)")
        if missing:
            # patch result row
            for r in RESULTS:
                if r["num"] == 25:
                    r["ok"] = False
                    r["notes"] = f"missing aliases: {missing}"
                    break

    call("POST", f"/galaxy-studio/force-complete/{bid}", 26, "D", timeout=60)
    call("GET", f"/galaxy-studio/files/{bid}", 27, "D")
    call("POST", f"/galaxy-studio/vault/zip/{bid}", 28, "D", timeout=60)
    # cleanup
    call("POST", "/galaxy-studio/clear-zombies", 30.1, "D")

# ---- G — rid in telemetry ----
print("\n== Group G — RID in telemetry ==")
# Fire a few rid-bearing requests, then inspect telemetry
for i in range(5):
    rid = f"sweepX-rid-{i}-{uuid.uuid4().hex[:6]}"
    r = S.get(f"{BASE}/health", headers={"X-Request-Id": rid}, timeout=10)
    echo = r.headers.get("X-Request-Id") or r.headers.get("x-request-id")
    print(f"   GET /health sent={rid} echo={echo} match={echo==rid}")

# Check telemetry — may or may not include recent_requests
tel, raw, _ = call("GET", "/_telemetry", 38, "G")
if isinstance(tel, dict):
    print(f"   telemetry keys: {list(tel.keys())[:20]}")
    for k in ("recent_requests","recent","requests","log","tail","last_requests"):
        if k in tel:
            print(f"   {k}: {tel[k][:2] if isinstance(tel[k],list) else tel[k]}")

print("\n--- Summary ---")
fails = [r for r in RESULTS if not r["ok"]]
print(f"  pass={len(RESULTS)-len(fails)} fail={len(fails)} total={len(RESULTS)}")
for f in fails:
    print(f"   #{f['num']} {f['method']} {f['endpoint']} -> {f['status']}  {f['head'][:120]}")
