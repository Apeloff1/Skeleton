#!/usr/bin/env python3
"""Galaxy Studio P0 Regression Test (2026-05-13)
Verifies the three critical fixes:
  1) BackgroundTasks import added — router now loads (no 404).
  2) vault_entry_id NameError removed from force-complete response.
  3) /files & /vault/zip use list_file_paths/iter_files (not list_files).

Plus regression: /api/health, /api/ai/modes, /api/ai/chat, curriculum.
"""
import os, sys, time, json, zipfile, io
import requests

BASE = "https://gemini-game-craft.preview.emergentagent.com/api"
TIMEOUT = 60

results = []  # (group, name, ok, detail)

def rec(group, name, ok, detail=""):
    icon = "✅" if ok else "❌"
    print(f"  {icon} [{group}] {name}: {detail[:300]}")
    results.append((group, name, ok, detail))

def safe_json(r):
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:500]}

# ════════════════════════════════════════════════════════════════════
# GROUP A — Galaxy Studio router-load fix (smoke endpoints)
# ════════════════════════════════════════════════════════════════════
print("\n=== GROUP A — Router Loaded (smoke) ===")
try:
    r = requests.get(f"{BASE}/galaxy-studio/manifest", timeout=TIMEOUT)
    rec("A", "GET /galaxy-studio/manifest", r.status_code == 200,
        f"status={r.status_code}, total_agents={safe_json(r).get('total', {}).get('agents', '?')}")
except Exception as e:
    rec("A", "GET /galaxy-studio/manifest", False, f"EXCEPTION: {e}")

try:
    r = requests.get(f"{BASE}/galaxy-studio/genres", timeout=TIMEOUT)
    js = safe_json(r)
    genre_count = len(js.get("genres", [])) if isinstance(js, dict) else 0
    rec("A", "GET /galaxy-studio/genres", r.status_code == 200 and genre_count > 0,
        f"status={r.status_code}, genres={genre_count}")
except Exception as e:
    rec("A", "GET /galaxy-studio/genres", False, f"EXCEPTION: {e}")

# ════════════════════════════════════════════════════════════════════
# GROUP B — Build creation + status (P0 path)
# ════════════════════════════════════════════════════════════════════
print("\n=== GROUP B — Create + Start + Status ===")
build_id = None
try:
    r = requests.post(f"{BASE}/galaxy-studio/create",
                      json={"title": "P0SmokeTest", "genre": "rpg"},
                      timeout=TIMEOUT)
    js = safe_json(r)
    build_id = js.get("build_id")
    rec("B", "POST /create minimal {title,genre}", r.status_code == 200 and bool(build_id),
        f"status={r.status_code}, build_id={build_id}, scale_target={js.get('scale', {}).get('target_files')}")
except Exception as e:
    rec("B", "POST /create minimal", False, f"EXCEPTION: {e}")

if build_id:
    try:
        r = requests.post(f"{BASE}/galaxy-studio/start-build",
                          json={"build_id": build_id, "build_duration_minutes": 1},
                          timeout=TIMEOUT)
        js = safe_json(r)
        rec("B", "POST /start-build (1-min)", r.status_code == 200,
            f"status={r.status_code}, bg_status={js.get('bg_status')}, batches={js.get('total_batches')}")
    except Exception as e:
        rec("B", "POST /start-build", False, f"EXCEPTION: {e}")

    # Poll status until completion (max ~90s)
    print("  Polling status...")
    final_status = None
    final_files = 0
    target_files = None
    started_at = time.time()
    last_progress = -1
    while time.time() - started_at < 120:
        try:
            r = requests.get(f"{BASE}/galaxy-studio/status/{build_id}", timeout=TIMEOUT)
            if r.status_code != 200:
                time.sleep(3); continue
            js = safe_json(r)
            final_status = js.get("status") or js.get("_bg_status")
            final_files = js.get("file_count", 0) or js.get("files_generated", 0) or 0
            target_files = js.get("target_files") or js.get("scale_info", {}).get("target_files")
            progress = js.get("progress_percent", 0)
            if progress != last_progress:
                print(f"    t+{int(time.time()-started_at)}s status={final_status} progress={progress}% files={final_files} target={target_files}")
                last_progress = progress
            if final_status == "completed":
                break
        except Exception as e:
            print(f"    poll error: {e}")
        time.sleep(3)

    rec("B", "GET /status/{build_id} → completed",
        final_status == "completed",
        f"final_status={final_status}, file_count={final_files}, target_files={target_files}, elapsed={int(time.time()-started_at)}s")

    rec("B", "file_count > 0 (not silent failure)",
        final_files > 0,
        f"file_count={final_files} (floor target = {target_files})")

# ════════════════════════════════════════════════════════════════════
# GROUP C — force-complete (NameError fix)
# ════════════════════════════════════════════════════════════════════
print("\n=== GROUP C — force-complete (vault_entry_id removed) ===")
if build_id:
    try:
        r = requests.post(f"{BASE}/galaxy-studio/force-complete/{build_id}", timeout=TIMEOUT)
        js = safe_json(r)
        # Must NOT have vault_id key (it was undefined). Must have build_id/status.
        has_vault_id = "vault_id" in js
        has_required = "build_id" in js and "status" in js
        rec("C", "POST /force-complete (no NameError)",
            r.status_code == 200 and has_required and not has_vault_id,
            f"status={r.status_code}, keys={list(js.keys())}, has_vault_id={has_vault_id}")
        # also acceptable: file_count, message
    except Exception as e:
        rec("C", "POST /force-complete", False, f"EXCEPTION: {e}")

# ════════════════════════════════════════════════════════════════════
# GROUP D — /files endpoint (list_file_paths fix)
# ════════════════════════════════════════════════════════════════════
print("\n=== GROUP D — /files (list_file_paths fix) ===")
if build_id:
    try:
        r = requests.get(f"{BASE}/galaxy-studio/files/{build_id}", timeout=TIMEOUT)
        js = safe_json(r)
        total_files = js.get("total_files", 0)
        source = js.get("source", "")
        # Expect 200, no 'list_files not found' silent failure, total_files > 0, source preferably 'vault'
        rec("D", "GET /files/{build_id}",
            r.status_code == 200 and total_files > 0,
            f"status={r.status_code}, total_files={total_files}, source={source}")
    except Exception as e:
        rec("D", "GET /files/{build_id}", False, f"EXCEPTION: {e}")

# ════════════════════════════════════════════════════════════════════
# GROUP E — /vault/zip + download (iter_files fix)
# ════════════════════════════════════════════════════════════════════
print("\n=== GROUP E — /vault/zip + /vault/download ===")
vault_id = None
if build_id:
    try:
        r = requests.post(f"{BASE}/galaxy-studio/vault/zip/{build_id}", timeout=120)
        js = safe_json(r)
        vault_id = js.get("vault_id")
        size_bytes = js.get("size_bytes", 0)
        download_url = js.get("download_url", "")
        rec("E", "POST /vault/zip/{build_id}",
            r.status_code == 200 and bool(vault_id) and size_bytes > 0 and bool(download_url),
            f"status={r.status_code}, vault_id={vault_id}, size_bytes={size_bytes}, file_count={js.get('file_count')}")
    except Exception as e:
        rec("E", "POST /vault/zip", False, f"EXCEPTION: {e}")

if vault_id:
    try:
        r = requests.get(f"{BASE}/galaxy-studio/vault/download/{vault_id}", timeout=120, stream=True)
        ctype = r.headers.get("content-type", "")
        # Validate it's a real ZIP
        data = r.content
        is_zip = False
        zip_n_files = 0
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            is_zip = True
            zip_n_files = len(zf.namelist())
        except Exception:
            pass
        rec("E", "GET /vault/download/{vault_id} (real ZIP)",
            r.status_code == 200 and "zip" in ctype.lower() and is_zip and zip_n_files > 0,
            f"status={r.status_code}, ctype={ctype}, bytes={len(data)}, zip_files={zip_n_files}")
    except Exception as e:
        rec("E", "GET /vault/download", False, f"EXCEPTION: {e}")

# ════════════════════════════════════════════════════════════════════
# GROUP F — /vault listing
# ════════════════════════════════════════════════════════════════════
print("\n=== GROUP F — /vault listing ===")
try:
    r = requests.get(f"{BASE}/galaxy-studio/vault", timeout=TIMEOUT)
    js = safe_json(r)
    total = js.get("total_entries", 0)
    zips = len(js.get("zips", []))
    rec("F", "GET /vault",
        r.status_code == 200 and total > 0 and zips > 0,
        f"status={r.status_code}, total_entries={total}, zips={zips}, apks={len(js.get('apks', []))}")
except Exception as e:
    rec("F", "GET /vault", False, f"EXCEPTION: {e}")

# ════════════════════════════════════════════════════════════════════
# GROUP G — Regression: other backend areas
# ════════════════════════════════════════════════════════════════════
print("\n=== GROUP G — Regression: other backend ===")

try:
    r = requests.get(f"{BASE}/health", timeout=TIMEOUT)
    js = safe_json(r)
    rec("G", "GET /api/health", r.status_code == 200 and js.get("status") == "healthy",
        f"status={r.status_code}, ai_available={js.get('ai_available')}")
except Exception as e:
    rec("G", "GET /api/health", False, f"EXCEPTION: {e}")

try:
    r = requests.get(f"{BASE}/ai/modes", timeout=TIMEOUT)
    js = safe_json(r)
    n_modes = len(js.get("modes", [])) if isinstance(js, dict) else 0
    rec("G", "GET /api/ai/modes", r.status_code == 200 and n_modes > 0,
        f"status={r.status_code}, modes={n_modes}")
except Exception as e:
    rec("G", "GET /api/ai/modes", False, f"EXCEPTION: {e}")

try:
    r = requests.post(f"{BASE}/ai/chat", json={"message": "hi"}, timeout=TIMEOUT)
    js = safe_json(r)
    has_response = bool(js.get("response") or js.get("message") or js.get("reply") or js.get("content"))
    rec("G", "POST /api/ai/chat {message:'hi'}",
        r.status_code == 200 and has_response,
        f"status={r.status_code}, keys={list(js.keys()) if isinstance(js, dict) else 'n/a'}")
except Exception as e:
    rec("G", "POST /api/ai/chat", False, f"EXCEPTION: {e}")

try:
    r = requests.get(f"{BASE}/curriculum/info", timeout=TIMEOUT)
    js = safe_json(r)
    rec("G", "GET /api/curriculum/info", r.status_code == 200 and js.get("total_classes", 0) > 0,
        f"status={r.status_code}, total_classes={js.get('total_classes')}, hours={js.get('total_hours')}")
except Exception as e:
    rec("G", "GET /api/curriculum/info", False, f"EXCEPTION: {e}")

try:
    r = requests.get(f"{BASE}/curriculum/classes/ds_complete/week/1", timeout=TIMEOUT)
    js = safe_json(r)
    has_lab = isinstance(js.get("lab"), dict) and js["lab"].get("title")
    has_gloss = isinstance(js.get("glossary"), list) and len(js["glossary"]) > 0
    rec("G", "GET /api/curriculum/classes/ds_complete/week/1",
        r.status_code == 200 and has_lab and has_gloss,
        f"status={r.status_code}, lab.title={js.get('lab', {}).get('title') if has_lab else None}, glossary_len={len(js.get('glossary', [])) if has_gloss else 0}")
except Exception as e:
    rec("G", "GET /api/curriculum/classes/ds_complete/week/1", False, f"EXCEPTION: {e}")

# ════════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print(f"TOTAL: {sum(1 for _,_,ok,_ in results if ok)}/{len(results)} PASS")
print("=" * 70)
fails = [(g,n,d) for g,n,ok,d in results if not ok]
if fails:
    print("\nFAILED:")
    for g,n,d in fails:
        print(f"  ❌ [{g}] {n}: {d}")
sys.exit(0 if not fails else 1)
