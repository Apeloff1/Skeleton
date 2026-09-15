#!/usr/bin/env python3
"""
Full backend bug sweep — every router group named in the review request.
Runs requests concurrently where safe; only ONE Galaxy Studio build kickoff.
"""
import os, time, json, uuid
import concurrent.futures as cf
from typing import Optional

import requests

BASE = "https://gemini-game-craft.preview.emergentagent.com/api"
SESSION = requests.Session()
SESSION.headers.update({"X-Request-Id": f"sweep-{uuid.uuid4().hex[:8]}"})

RESULTS = []  # list of dicts: {group, num, endpoint, method, status, ms, ok, notes}


def call(method: str, path: str, num: int, group: str, *, json_body=None, timeout=30, expect=200, notes_extra: str = "") -> dict:
    url = f"{BASE}{path}"
    t0 = time.time()
    body_text = ""
    status = -1
    ok = False
    notes = notes_extra
    headers = {}
    try:
        r = SESSION.request(method, url, json=json_body, timeout=timeout)
        status = r.status_code
        headers = dict(r.headers)
        body_text = r.text
        ok = (status == expect) if isinstance(expect, int) else (status in expect)
    except Exception as e:
        notes = f"EXCEPTION: {e!r}"
    ms = int((time.time() - t0) * 1000)
    entry = {
        "group": group, "num": num, "endpoint": path, "method": method,
        "status": status, "ms": ms, "ok": ok,
        "body_head": "\n".join(body_text.splitlines()[:5])[:600] if not ok else "",
        "headers": headers,
        "notes": notes,
        "body_text": body_text if not ok else body_text[:2000],
    }
    RESULTS.append(entry)
    return entry


def gather_parallel(jobs):
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda j: call(**j), jobs))


# ---- A. CORE ---------------------------------------------------------------
print("== Group A: CORE ==")
A_jobs = [
    {"method": "GET", "path": "/health", "num": 1, "group": "A"},
    {"method": "GET", "path": "/_telemetry", "num": 2, "group": "A"},
    {"method": "GET", "path": "/languages", "num": 3, "group": "A"},
    {"method": "GET", "path": "/ai/modes", "num": 4, "group": "A"},
    {"method": "GET", "path": "/class-progress/achievements/all", "num": 5, "group": "A"},
    {"method": "GET", "path": "/jeeves-languages/overview", "num": 6, "group": "A"},
]
gather_parallel(A_jobs)

# ---- B. CURRICULUM ---------------------------------------------------------
print("== Group B: CURRICULUM ==")
B_jobs = [
    {"method": "GET", "path": "/curriculum/classes", "num": 7, "group": "B"},
    {"method": "GET", "path": "/curriculum/classes/cs100", "num": 8, "group": "B"},
    {"method": "GET", "path": "/curriculum/classes/cs100/week/1", "num": 9, "group": "B"},
    {"method": "GET", "path": "/curriculum/classes/cs100/week/15", "num": 10, "group": "B"},
    {"method": "GET", "path": "/curriculum/classes/cs100/week/1/quiz", "num": 11, "group": "B"},
    {"method": "GET", "path": "/curriculum/classes/cs100/week/99", "num": 12, "group": "B", "expect": 404},
    {"method": "GET", "path": "/curriculum/classes/does_not_exist", "num": 13, "group": "B", "expect": 404},
]
gather_parallel(B_jobs)

# ---- C. ACADEMY / READING --------------------------------------------------
print("== Group C: ACADEMY / READING ==")
C_jobs = [
    {"method": "GET", "path": "/academy/reading-library?page=1&limit=20", "num": 14, "group": "C"},
    {"method": "GET", "path": "/academy/bibles?page=1&limit=20", "num": 15, "group": "C"},
    {"method": "GET", "path": "/academy/tracks?page=1&limit=20", "num": 16, "group": "C"},
    {"method": "GET", "path": "/academy/search?q=python", "num": 17, "group": "C"},
]
gather_parallel(C_jobs)

# pick a book from #14 and verify single-book endpoint
book_id = None
for e in RESULTS:
    if e["num"] == 14 and e["ok"]:
        try:
            data = json.loads(e["body_text"])
            books = data.get("books") or data.get("items") or data.get("data") or []
            if isinstance(books, list) and books:
                first = books[0]
                book_id = first.get("book_id") or first.get("id") or first.get("_id")
        except Exception as ex:
            print("book-id parse failed:", ex)
if book_id:
    call("GET", f"/academy/reading-library/{book_id}", 18, "C", notes_extra=f"book_id={book_id}")
else:
    RESULTS.append({"group": "C", "num": 18, "endpoint": "/academy/reading-library/<no_id>", "method": "GET",
                    "status": -1, "ms": 0, "ok": False, "body_head": "could not extract book_id from #14", "notes": "skipped"})

# ---- D. GALAXY STUDIO ------------------------------------------------------
print("== Group D: GALAXY STUDIO ==")
D_read_jobs = [
    {"method": "GET", "path": "/galaxy-studio/manifest", "num": 19, "group": "D"},
    {"method": "GET", "path": "/galaxy-studio/genres", "num": 20, "group": "D"},
    {"method": "GET", "path": "/galaxy-studio/db-status", "num": 21, "group": "D"},
    {"method": "GET", "path": "/galaxy-studio/watchdog/health", "num": 22, "group": "D"},
    {"method": "GET", "path": "/galaxy-studio/flair/stats", "num": 23, "group": "D"},
]
gather_parallel(D_read_jobs)

# 24 — ONE controlled build kickoff
create_payload = {"title": "Sweep", "genre": "rpg", "complexity": "intermediate", "target_files": 48000}
create_entry = call("POST", "/galaxy-studio/create", 24, "D", json_body=create_payload, timeout=30, notes_extra=f"payload={create_payload}")
bid = None
try:
    data = json.loads(create_entry["body_text"])
    bid = data.get("build_id") or data.get("id") or (data.get("build") or {}).get("build_id")
except Exception as ex:
    print("create parse failed:", ex)
print("  -> build_id:", bid)

# 25 — status with alias check
if bid:
    s_entry = call("GET", f"/galaxy-studio/status/{bid}", 25, "D")
    try:
        s_body = json.loads(s_entry["body_text"])
        required_aliases = ["progress_percent", "phase_label", "phase", "target_files", "eta_seconds", "errors"]
        missing = [k for k in required_aliases if k not in s_body]
        s_entry["notes"] = f"missing_aliases={missing}; target_files={s_body.get('target_files')}; progress={s_body.get('progress_percent')}; phase_label={s_body.get('phase_label')!r}"
        if missing:
            s_entry["ok"] = False
            s_entry["body_head"] = f"missing aliases: {missing}"
        # floor check
        tf = s_body.get("target_files")
        if tf is not None and tf != 48000:
            s_entry["ok"] = False
            s_entry["body_head"] = f"target_files != 48000, got {tf}"
            s_entry["notes"] += " | FLOOR REGRESSION"
    except Exception as ex:
        print("status parse failed:", ex)

    # 26 — force complete
    call("POST", f"/galaxy-studio/force-complete/{bid}", 26, "D", timeout=60)
    # 27 — files
    call("GET", f"/galaxy-studio/files/{bid}", 27, "D")
    # 28 — vault zip
    call("POST", f"/galaxy-studio/vault/zip/{bid}", 28, "D", timeout=60)
else:
    for n, ep, m in [(25, "/galaxy-studio/status/<no_bid>", "GET"), (26, "/galaxy-studio/force-complete/<no_bid>", "POST"),
                     (27, "/galaxy-studio/files/<no_bid>", "GET"), (28, "/galaxy-studio/vault/zip/<no_bid>", "POST")]:
        RESULTS.append({"group": "D", "num": n, "endpoint": ep, "method": m, "status": -1, "ms": 0, "ok": False, "body_head": "skipped — no build_id from #24", "notes": "skipped"})

# 29 — vault list
call("GET", "/galaxy-studio/vault", 29, "D")
# 30 — clear zombies (cleanup)
call("POST", "/galaxy-studio/clear-zombies", 30, "D")

# ---- E. AI / JEEVES --------------------------------------------------------
print("== Group E: AI / JEEVES ==")
ai_chat_payload = {"message": "hello", "mode": "default", "user_id": "sweep_user"}
quiz_payload = {"topic": "python basics", "num_questions": 1, "difficulty": "easy"}
# Try common AI chat shapes
call("POST", "/ai/chat", 31, "E", json_body=ai_chat_payload, timeout=30, notes_extra=str(ai_chat_payload))
call("POST", "/ai/quiz/generate", 32, "E", json_body=quiz_payload, timeout=45, notes_extra=str(quiz_payload))
call("GET", "/ai/usage", 33, "E")

# ---- F. GAME / EDITOR-ADJACENT --------------------------------------------
print("== Group F: GAME / EDITOR ==")
F_jobs = [
    {"method": "GET", "path": "/game/scenes", "num": 34, "group": "F"},
    {"method": "GET", "path": "/gallery/builds", "num": 35, "group": "F"},
    {"method": "GET", "path": "/scheduler/events", "num": 36, "group": "F"},
]
gather_parallel(F_jobs)

# ---- G. SOTA / request-id sweep -------------------------------------------
print("== Group G: SOTA / request-id ==")
# 37 — verify X-Request-Id echoed
hdr_rid = f"sweep-rid-{uuid.uuid4().hex[:8]}"
r = SESSION.get(f"{BASE}/health", headers={"X-Request-Id": hdr_rid}, timeout=10)
got = r.headers.get("X-Request-Id") or r.headers.get("x-request-id")
ok = got == hdr_rid
RESULTS.append({
    "group": "G", "num": 37, "endpoint": "/health", "method": "GET",
    "status": r.status_code, "ms": int(r.elapsed.total_seconds() * 1000),
    "ok": ok,
    "body_head": "" if ok else f"sent={hdr_rid!r} echoed={got!r}",
    "notes": f"sent={hdr_rid!r} echoed={got!r}",
    "headers": dict(r.headers),
    "body_text": "",
})

# 38 — check telemetry for rid != "-"
tel_entry = call("GET", "/_telemetry", 38, "G")
try:
    tel = json.loads(tel_entry["body_text"])
    # Look for request log entries to verify rid is not all dashes
    recent = tel.get("recent_requests") or tel.get("recent") or tel.get("requests") or []
    if isinstance(recent, list) and recent:
        rids = [str(r.get("rid") or r.get("request_id") or "-") for r in recent if isinstance(r, dict)]
        non_dash = [x for x in rids if x and x != "-"]
        tel_entry["notes"] += f" | recent_log_len={len(rids)} non_dash_rid_count={len(non_dash)}"
        if rids and not non_dash:
            tel_entry["ok"] = False
            tel_entry["body_head"] = "all rids in recent log are '-' — request-id middleware regression"
    else:
        # telemetry may not expose log — just record summary
        keys = list(tel.keys()) if isinstance(tel, dict) else []
        tel_entry["notes"] += f" | telemetry keys: {keys[:12]}"
except Exception as ex:
    tel_entry["notes"] += f" | parse_err={ex!r}"

# ---- PRINT REPORT ----------------------------------------------------------
print("\n\n========= REPORT =========")
groups = {}
for e in sorted(RESULTS, key=lambda x: x["num"]):
    groups.setdefault(e["group"], []).append(e)

for g, items in groups.items():
    print(f"\n--- Group {g} ---")
    print(f"{'#':>3} {'Method':<6} {'Endpoint':<70} {'HTTP':>5} {'ms':>6} {'OK':>4} Notes")
    for e in items:
        notes = e["notes"][:80]
        print(f"{e['num']:>3} {e['method']:<6} {e['endpoint'][:70]:<70} {e['status']:>5} {e['ms']:>6} {('Y' if e['ok'] else 'N'):>4} {notes}")

print("\n========= FAILURES =========")
fails = [e for e in RESULTS if not e["ok"]]
for e in fails:
    print(f"\n#{e['num']} [{e['method']} {e['endpoint']}] HTTP={e['status']} {e['ms']}ms")
    print(f"  body_head: {e['body_head']}")
    print(f"  notes: {e['notes']}")

print(f"\nTotal: {len(RESULTS)}   Pass: {sum(1 for e in RESULTS if e['ok'])}   Fail: {len(fails)}")

# also dump raw json
with open("/tmp/sweep_results.json", "w") as fh:
    # strip headers/body_text from output to keep size small
    cleaned = []
    for e in RESULTS:
        c = dict(e)
        c.pop("headers", None)
        c["body_text"] = c.get("body_text", "")[:600]
        cleaned.append(c)
    json.dump(cleaned, fh, indent=2)
print("\nFull dump: /tmp/sweep_results.json")
