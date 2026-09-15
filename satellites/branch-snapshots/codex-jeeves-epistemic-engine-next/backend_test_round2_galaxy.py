"""
Round 2 Galaxy Studio comprehensive regression test.
Verifies the two latest patches:
A) file_count progression — monotonically increases (never resets to 0) mid-build.
B) regression-clean (BackgroundTasks import, vault_entry_id removal, list_file_paths/iter_files).

Plus full end-to-end build → browse code → vault zip → vault download → APK whoami.
"""
import io
import json
import sys
import time
import zipfile
from typing import Any, Dict, List

import requests

BASE_URL = "https://gemini-game-craft.preview.emergentagent.com/api"
TIMEOUT = 60

results: List[Dict[str, Any]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    icon = "✅" if ok else "❌"
    print(f"{icon} {name}: {detail}")
    results.append({"name": name, "ok": ok, "detail": detail})


def main() -> int:
    # 1) Health
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        ok = r.status_code == 200 and r.json().get("status") == "healthy"
        record("1) GET /api/health", ok, f"status={r.status_code}, payload={r.json() if r.status_code==200 else r.text[:200]}")
    except Exception as e:
        record("1) GET /api/health", False, f"EXCEPTION {e}")

    # 2) Galaxy router loaded
    try:
        r = requests.get(f"{BASE_URL}/galaxy-studio/manifest", timeout=TIMEOUT)
        if r.status_code != 200:
            record("2) GET /galaxy-studio/manifest", False, f"HTTP {r.status_code}: {r.text[:200]}")
        else:
            j = r.json()
            tp = j.get("total_phases", j.get("phases_total"))
            tg = j.get("total_genres", j.get("genres_total"))
            ok = (tp == 100 and tg == 69)
            record("2) GET /galaxy-studio/manifest", ok, f"total_phases={tp}, total_genres={tg}")
    except Exception as e:
        record("2) GET /galaxy-studio/manifest", False, f"EXCEPTION {e}")

    # 3) Build creation + file_count progression
    build_id = None
    try:
        payload = {"title": "FullTest", "genre": "rpg", "complexity": "advanced"}
        r = requests.post(f"{BASE_URL}/galaxy-studio/create", json=payload, timeout=TIMEOUT)
        if r.status_code != 200:
            record("3a) POST /galaxy-studio/create", False, f"HTTP {r.status_code}: {r.text[:400]}")
        else:
            j = r.json()
            build_id = j.get("build_id") or j.get("id") or (j.get("build") or {}).get("build_id")
            record("3a) POST /galaxy-studio/create", bool(build_id), f"build_id={build_id}")
    except Exception as e:
        record("3a) POST /galaxy-studio/create", False, f"EXCEPTION {e}")

    if not build_id:
        print("\nCANNOT CONTINUE — no build_id\n")
        finalize()
        return 1

    # 3b) start-build
    try:
        r = requests.post(
            f"{BASE_URL}/galaxy-studio/start-build",
            json={"build_id": build_id, "build_duration_minutes": 1},
            timeout=TIMEOUT,
        )
        record("3b) POST /galaxy-studio/start-build", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        record("3b) POST /galaxy-studio/start-build", False, f"EXCEPTION {e}")

    # 3c) Poll status every 5s for up to ~120s. Track file_count monotonicity.
    fc_history: List[int] = []
    status_history: List[str] = []
    completed = False
    start = time.time()
    last_status = "unknown"
    while time.time() - start < 150:
        try:
            r = requests.get(f"{BASE_URL}/galaxy-studio/status/{build_id}", timeout=TIMEOUT)
            if r.status_code == 200:
                j = r.json()
                fc = j.get("file_count", 0)
                st = j.get("status", "unknown")
                fc_history.append(fc)
                status_history.append(st)
                last_status = st
                elapsed = int(time.time() - start)
                print(f"  [poll t={elapsed}s] status={st}, file_count={fc}, progress={j.get('progress_percent', 'NA')}%")
                if st in ("completed", "failed", "error"):
                    completed = True
                    break
            else:
                print(f"  [poll] HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"  [poll] EXCEPTION {e}")
        time.sleep(5)

    # Check monotonic progression
    monotonic = True
    drops = []
    for i in range(1, len(fc_history)):
        if fc_history[i] < fc_history[i - 1]:
            monotonic = False
            drops.append(f"poll{i}: {fc_history[i - 1]} → {fc_history[i]}")
    record(
        "3c) file_count progression monotonic (CRITICAL)",
        monotonic and len(fc_history) > 0 and (max(fc_history) if fc_history else 0) > 0,
        f"history={fc_history[:30]}{'...' if len(fc_history)>30 else ''}, drops={drops or 'none'}",
    )
    record(
        "3d) build reached completed status",
        last_status == "completed",
        f"last_status={last_status}, final file_count={fc_history[-1] if fc_history else 'NA'}",
    )

    final_fc = fc_history[-1] if fc_history else 0

    # 4) Browse Code endpoints
    files_listing = None
    first_path = None
    try:
        r = requests.get(f"{BASE_URL}/galaxy-studio/files/{build_id}", timeout=TIMEOUT)
        if r.status_code != 200:
            record("4a) GET /galaxy-studio/files/{build_id}", False, f"HTTP {r.status_code}: {r.text[:300]}")
        else:
            j = r.json()
            files_listing = j
            tf = j.get("total_files", 0)
            files = j.get("files", [])
            src = j.get("source")
            ok = tf > 0 and len(files) > 0 and bool(src)
            record(
                "4a) GET /galaxy-studio/files/{build_id}",
                ok,
                f"total_files={tf}, files_array_len={len(files)}, source={src}",
            )
            if files:
                # Get a path from the first file (try several shapes)
                f0 = files[0]
                first_path = f0.get("path") or f0.get("filename") or (f0 if isinstance(f0, str) else None)
                print(f"  first file path: {first_path}")
    except Exception as e:
        record("4a) GET /galaxy-studio/files/{build_id}", False, f"EXCEPTION {e}")

    if first_path:
        try:
            # The path likely contains slashes — must URL-encode or pass directly
            from urllib.parse import quote
            encoded = quote(first_path, safe="")
            url = f"{BASE_URL}/galaxy-studio/file/{build_id}/{encoded}"
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                # Try without encoding
                url2 = f"{BASE_URL}/galaxy-studio/file/{build_id}/{first_path}"
                r2 = requests.get(url2, timeout=TIMEOUT)
                if r2.status_code == 200:
                    r = r2
            if r.status_code != 200:
                record("4b) GET /galaxy-studio/file/{build_id}/{path}", False, f"HTTP {r.status_code}: {r.text[:300]}")
            else:
                j = r.json()
                content = j.get("content", "")
                lines = j.get("lines", j.get("line_count", 0))
                ok = isinstance(content, str) and len(content) > 0 and lines >= 0
                record(
                    "4b) GET /galaxy-studio/file/{build_id}/{path}",
                    ok,
                    f"content_len={len(content) if isinstance(content,str) else 'NA'}, lines={lines}",
                )
        except Exception as e:
            record("4b) GET /galaxy-studio/file/{build_id}/{path}", False, f"EXCEPTION {e}")
    else:
        record("4b) GET /galaxy-studio/file/{build_id}/{path}", False, "no first_path available")

    # 5) Vault button
    try:
        r = requests.get(f"{BASE_URL}/galaxy-studio/vault", timeout=TIMEOUT)
        if r.status_code != 200:
            record("5a) GET /galaxy-studio/vault", False, f"HTTP {r.status_code}: {r.text[:300]}")
        else:
            j = r.json()
            zips = j.get("zips", [])
            apks = j.get("apks", [])
            ok = isinstance(zips, list) and isinstance(apks, list)
            record("5a) GET /galaxy-studio/vault", ok, f"zips={len(zips)}, apks={len(apks)}")
    except Exception as e:
        record("5a) GET /galaxy-studio/vault", False, f"EXCEPTION {e}")

    vault_id = None
    expected_size = None
    try:
        r = requests.post(f"{BASE_URL}/galaxy-studio/vault/zip/{build_id}", timeout=180)
        if r.status_code != 200:
            record("5b) POST /galaxy-studio/vault/zip/{build_id}", False, f"HTTP {r.status_code}: {r.text[:300]}")
        else:
            j = r.json()
            vault_id = j.get("vault_id") or j.get("id")
            expected_size = j.get("size_bytes") or j.get("size")
            dl = j.get("download_url")
            fc = j.get("file_count")
            ok = bool(vault_id) and bool(expected_size) and bool(dl)
            record(
                "5b) POST /galaxy-studio/vault/zip/{build_id}",
                ok,
                f"vault_id={vault_id}, size_bytes={expected_size}, file_count={fc}, download_url={dl}",
            )
    except Exception as e:
        record("5b) POST /galaxy-studio/vault/zip/{build_id}", False, f"EXCEPTION {e}")

    if vault_id:
        try:
            r = requests.get(
                f"{BASE_URL}/galaxy-studio/vault/download/{vault_id}",
                timeout=180,
                stream=True,
            )
            if r.status_code != 200:
                record("5c) GET /galaxy-studio/vault/download/{vault_id}", False, f"HTTP {r.status_code}: {r.text[:200]}")
            else:
                ctype = r.headers.get("content-type", "")
                buf = io.BytesIO()
                total = 0
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        buf.write(chunk)
                        total += len(chunk)
                # Validate ZIP
                valid = False
                entries = 0
                try:
                    buf.seek(0)
                    with zipfile.ZipFile(buf, "r") as zf:
                        entries = len(zf.namelist())
                        valid = entries > 0
                except Exception as ze:
                    valid = False
                    print(f"  zip validation error: {ze}")
                size_match = (expected_size is None) or (total == expected_size)
                ok = (ctype.startswith("application/zip") or "zip" in ctype) and valid and size_match
                record(
                    "5c) GET /galaxy-studio/vault/download/{vault_id}",
                    ok,
                    f"content-type={ctype}, bytes_downloaded={total}, expected={expected_size}, zip_entries={entries}, size_match={size_match}",
                )
        except Exception as e:
            record("5c) GET /galaxy-studio/vault/download/{vault_id}", False, f"EXCEPTION {e}")

    # 6) APK pipeline readiness — whoami only
    try:
        r = requests.get(f"{BASE_URL}/galaxy-studio/eas/whoami", timeout=TIMEOUT)
        if r.status_code != 200:
            record("6) GET /galaxy-studio/eas/whoami", False, f"HTTP {r.status_code}: {r.text[:300]}")
        else:
            j = r.json()
            st = j.get("status")
            account = j.get("account") or j.get("username") or j.get("user")
            email = j.get("email")
            ok = st == "authenticated" and (account or email)
            record(
                "6) GET /galaxy-studio/eas/whoami",
                ok,
                f"status={st}, account={account}, email={email}",
            )
    except Exception as e:
        record("6) GET /galaxy-studio/eas/whoami", False, f"EXCEPTION {e}")

    # 7) Non-Galaxy regression
    try:
        r = requests.get(f"{BASE_URL}/ai/modes", timeout=TIMEOUT)
        record("7a) GET /api/ai/modes", r.status_code == 200, f"HTTP {r.status_code}, len={len(r.json()) if r.status_code==200 and isinstance(r.json(), list) else 'see body'}")
    except Exception as e:
        record("7a) GET /api/ai/modes", False, f"EXCEPTION {e}")

    try:
        r = requests.post(f"{BASE_URL}/ai/chat", json={"message": "hi"}, timeout=TIMEOUT)
        if r.status_code != 200:
            record("7b) POST /api/ai/chat", False, f"HTTP {r.status_code}: {r.text[:300]}")
        else:
            j = r.json()
            resp = j.get("response") or j.get("message") or ""
            ai_gen = j.get("ai_generated")
            ok = bool(resp) and (ai_gen is True or ai_gen is None)
            record(
                "7b) POST /api/ai/chat",
                ok,
                f"response_len={len(resp) if isinstance(resp,str) else 'NA'}, ai_generated={ai_gen}, model={j.get('model')}",
            )
    except Exception as e:
        record("7b) POST /api/ai/chat", False, f"EXCEPTION {e}")

    try:
        r = requests.get(f"{BASE_URL}/curriculum/info", timeout=TIMEOUT)
        if r.status_code != 200:
            record("7c) GET /api/curriculum/info", False, f"HTTP {r.status_code}")
        else:
            j = r.json()
            tc = j.get("total_classes", j.get("classes"))
            th = j.get("total_hours", j.get("hours"))
            record("7c) GET /api/curriculum/info", True, f"total_classes={tc}, total_hours={th}")
    except Exception as e:
        record("7c) GET /api/curriculum/info", False, f"EXCEPTION {e}")

    return finalize()


def finalize() -> int:
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    p = sum(1 for r in results if r["ok"])
    f = sum(1 for r in results if not r["ok"])
    print(f"PASS: {p}  FAIL: {f}  TOTAL: {len(results)}")
    if f:
        print("\nFAILS:")
        for r in results:
            if not r["ok"]:
                print(f"  ❌ {r['name']}: {r['detail']}")
    return 0 if f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
