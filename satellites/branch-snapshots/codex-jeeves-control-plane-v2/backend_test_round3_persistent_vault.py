"""
ROUND 3 — Persistent Vault & Recovery endpoints verification.

Validates the persistent-disk-vault architectural fix:
A) PERSISTENCE — build files land on /app/backend/data/builds_vault/{bid}
B) SURVIVE BACKEND RESTART — files endpoint still returns total_files > 0
C) NEW ENDPOINTS — /my-builds + /cleanup-old-builds (dry_run)
D) /expand on nonexistent build → 404
E) Regression sweep on round-1/2 surface
"""
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import requests

BASE_URL = "https://gemini-game-craft.preview.emergentagent.com/api"
TIMEOUT = 60
VAULT_DISK = Path("/app/backend/data/builds_vault")
GALAXY_VAULT_DISK = Path("/app/backend/data/galaxy_vault")

results: List[Dict[str, Any]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    icon = "✅" if ok else "❌"
    print(f"{icon} {name}: {detail}")
    results.append({"name": name, "ok": ok, "detail": detail})


def get(path: str, **kw) -> requests.Response:
    return requests.get(f"{BASE_URL}{path}", timeout=TIMEOUT, **kw)


def post(path: str, **kw) -> requests.Response:
    return requests.post(f"{BASE_URL}{path}", timeout=TIMEOUT, **kw)


def main() -> int:
    # ────────── SECTION E (regression: pre-flight sanity) ──────────
    try:
        r = get("/health")
        record("E1) GET /api/health", r.status_code == 200 and r.json().get("status") == "healthy", f"{r.status_code}")
    except Exception as e:
        record("E1) GET /api/health", False, f"EXC {e}")

    try:
        r = get("/galaxy-studio/manifest")
        j = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and j.get("total_phases") == 100 and j.get("total_genres") == 69
        record("E2) GET /galaxy-studio/manifest", ok, f"phases={j.get('total_phases')} genres={j.get('total_genres')}")
    except Exception as e:
        record("E2) GET /galaxy-studio/manifest", False, f"EXC {e}")

    try:
        r = get("/galaxy-studio/genres")
        j = r.json() if r.status_code == 200 else {}
        n = len(j.get("genres", []))
        record("E3) GET /galaxy-studio/genres", r.status_code == 200 and n >= 69, f"genres={n}")
    except Exception as e:
        record("E3) GET /galaxy-studio/genres", False, f"EXC {e}")

    try:
        r = get("/galaxy-studio/eas/whoami")
        j = r.json() if r.status_code == 200 else {}
        record("E4) GET /galaxy-studio/eas/whoami", r.status_code == 200 and j.get("status") == "authenticated", f"{j.get('status')}")
    except Exception as e:
        record("E4) GET /galaxy-studio/eas/whoami", False, f"EXC {e}")

    # ────────── SECTION A — PERSISTENCE ──────────
    build_id = None
    try:
        r = post("/galaxy-studio/create", json={
            "title": "Round3PersistTest",
            "genre": "rpg",
            "complexity": "advanced",
        })
        if r.status_code != 200:
            record("A1) POST /galaxy-studio/create", False, f"HTTP {r.status_code}: {r.text[:200]}")
        else:
            build_id = r.json().get("build_id")
            record("A1) POST /galaxy-studio/create", bool(build_id), f"build_id={build_id}")
    except Exception as e:
        record("A1) POST /galaxy-studio/create", False, f"EXC {e}")

    if not build_id:
        print("Cannot continue without build_id")
        return 1

    try:
        r = post("/galaxy-studio/start-build", json={"build_id": build_id, "build_duration_minutes": 1})
        ok = r.status_code == 200
        record("A2) POST /galaxy-studio/start-build (1 min)", ok, f"HTTP {r.status_code}: status={r.json().get('status') if ok else r.text[:200]}")
    except Exception as e:
        record("A2) POST /galaxy-studio/start-build", False, f"EXC {e}")

    # Poll status until completed (cap at 4 minutes)
    final_status = None
    file_count = 0
    deadline = time.time() + 240
    while time.time() < deadline:
        try:
            r = get(f"/galaxy-studio/status/{build_id}")
            if r.status_code == 200:
                j = r.json()
                final_status = j.get("status")
                file_count = j.get("file_count", 0)
                if final_status == "completed":
                    break
            time.sleep(8)
        except Exception:
            time.sleep(5)
    record("A3) Build reaches completed status", final_status == "completed", f"status={final_status} file_count={file_count}")

    # Verify on-disk vault directory + manifest + shards
    bdir = VAULT_DISK / build_id
    manifest = bdir / "manifest.json"
    shards = sorted(bdir.glob("shard_*.jsonl.zst")) if bdir.exists() else []
    record("A4) Vault dir exists on persistent disk",
           bdir.is_dir(),
           f"path={bdir} exists={bdir.exists()}")
    record("A5) manifest.json present",
           manifest.is_file(),
           f"manifest_size={manifest.stat().st_size if manifest.exists() else 0}")
    record("A6) >=20 shard files on disk", len(shards) >= 20, f"shard_count={len(shards)}")

    # /files endpoint
    try:
        r = get(f"/galaxy-studio/files/{build_id}")
        j = r.json() if r.status_code == 200 else {}
        tf = j.get("total_files", 0)
        src = j.get("source", "")
        record("A7) GET /galaxy-studio/files/{bid}",
               r.status_code == 200 and tf > 0,
               f"HTTP {r.status_code} total_files={tf} source={src}")
    except Exception as e:
        record("A7) GET /galaxy-studio/files/{bid}", False, f"EXC {e}")

    # /vault/zip
    vault_id = None
    download_url = None
    try:
        r = post(f"/galaxy-studio/vault/zip/{build_id}")
        if r.status_code == 200:
            j = r.json()
            vault_id = j.get("vault_id")
            download_url = j.get("download_url")
            record("A8) POST /galaxy-studio/vault/zip/{bid}",
                   bool(vault_id) and bool(download_url),
                   f"vault_id={vault_id} size_bytes={j.get('size_bytes')} files={j.get('file_count')}")
        else:
            record("A8) POST /galaxy-studio/vault/zip/{bid}", False, f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        record("A8) POST /galaxy-studio/vault/zip/{bid}", False, f"EXC {e}")

    # /vault/download
    if vault_id:
        try:
            r = requests.get(f"{BASE_URL}/galaxy-studio/vault/download/{vault_id}", timeout=120, stream=True)
            content_type = r.headers.get("content-type", "")
            chunks = []
            for c in r.iter_content(chunk_size=65536):
                if c:
                    chunks.append(c)
            payload = b"".join(chunks)
            try:
                zf = zipfile.ZipFile(io.BytesIO(payload))
                zip_entries = len(zf.namelist())
                zf.close()
                zip_ok = True
            except Exception as _ze:
                zip_entries = 0
                zip_ok = False
            record("A9) GET /vault/download/{vid}",
                   r.status_code == 200 and zip_ok and zip_entries > 0,
                   f"HTTP {r.status_code} bytes={len(payload)} ct={content_type} zip_entries={zip_entries}")
        except Exception as e:
            record("A9) GET /vault/download/{vid}", False, f"EXC {e}")

    # ────────── SECTION B — SURVIVE BACKEND RESTART ──────────
    print("\n[B] Restarting backend (sudo supervisorctl restart backend) ...")
    try:
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=False, capture_output=True, text=True)
    except Exception as e:
        print(f"  supervisor restart issued exception: {e}")
    # Wait for backend to come back online
    print("[B] Waiting up to 30s for backend to recover ...")
    online = False
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = get("/health")
            if r.status_code == 200 and r.json().get("status") == "healthy":
                online = True
                break
        except Exception:
            pass
        time.sleep(2)
    record("B1) Backend online after restart", online, f"online={online}")

    # /files still returns >0 — the gold standard
    try:
        r = get(f"/galaxy-studio/files/{build_id}")
        j = r.json() if r.status_code == 200 else {}
        tf = j.get("total_files", 0)
        src = j.get("source", "")
        record("B2) GET /files/{bid} AFTER RESTART (gold standard)",
               r.status_code == 200 and tf > 0,
               f"HTTP {r.status_code} total_files={tf} source={src}")
    except Exception as e:
        record("B2) GET /files/{bid} AFTER RESTART", False, f"EXC {e}")

    # /my-builds shows it with vault_present=true
    try:
        r = get("/galaxy-studio/my-builds", params={"limit": 100})
        j = r.json() if r.status_code == 200 else {}
        builds = j.get("builds", [])
        our_entry = next((b for b in builds if b.get("build_id") == build_id), None)
        record("B3) GET /my-builds finds our build",
               our_entry is not None,
               f"found={our_entry is not None} count={len(builds)}")
        if our_entry is not None:
            record("B4) Our build has vault_present=True",
                   our_entry.get("vault_present") is True,
                   f"vault_present={our_entry.get('vault_present')} status={our_entry.get('status')} fc={our_entry.get('file_count')}")
    except Exception as e:
        record("B3) GET /my-builds", False, f"EXC {e}")

    # ────────── SECTION C — NEW ENDPOINTS ──────────
    try:
        r = get("/galaxy-studio/my-builds")
        j = r.json() if r.status_code == 200 else {}
        builds = j.get("builds", [])
        if builds:
            shape_ok = all(
                isinstance(b.get("build_id"), str)
                and "title" in b
                and "status" in b
                and "file_count" in b
                and "vault_present" in b
                for b in builds[:5]
            )
        else:
            shape_ok = False
        record("C1) GET /my-builds shape", r.status_code == 200 and shape_ok and len(builds) > 0,
               f"count={len(builds)} shape_ok={shape_ok}")
    except Exception as e:
        record("C1) GET /my-builds shape", False, f"EXC {e}")

    try:
        r = get("/galaxy-studio/my-builds", params={"status": "completed"})
        j = r.json() if r.status_code == 200 else {}
        builds = j.get("builds", [])
        all_completed = all(b.get("status") == "completed" for b in builds) if builds else False
        record("C2) GET /my-builds?status=completed", r.status_code == 200 and all_completed,
               f"count={len(builds)} all_completed={all_completed}")
    except Exception as e:
        record("C2) GET /my-builds?status=completed", False, f"EXC {e}")

    try:
        r = post("/galaxy-studio/cleanup-old-builds", params={"keep_last": 5, "dry_run": "true"})
        j = r.json() if r.status_code == 200 else {}
        # Verify dry_run did NOT actually delete: vault dir for our build should still exist
        still_present = (VAULT_DISK / build_id).exists()
        record("C3) POST /cleanup-old-builds?keep_last=5&dry_run=true",
               r.status_code == 200 and j.get("dry_run") is True and "kept" in j and "deleted" in j and still_present,
               f"HTTP {r.status_code} dry_run={j.get('dry_run')} kept={j.get('kept_count')} deleted_count={j.get('deleted_count')} freed_mb={j.get('freed_mb')} our_build_still_on_disk={still_present}")
    except Exception as e:
        record("C3) POST /cleanup-old-builds dry_run", False, f"EXC {e}")

    # ────────── SECTION D — /expand 404 ──────────
    try:
        r = post("/galaxy-studio/expand", json={"build_id": "nonexistent-build-id-xxx", "expansion_type": "content"})
        record("D1) POST /expand nonexistent → 404", r.status_code == 404, f"HTTP {r.status_code} body={r.text[:140]}")
    except Exception as e:
        record("D1) POST /expand nonexistent → 404", False, f"EXC {e}")

    # ────────── SECTION E (regression: continued) ──────────
    try:
        r = get("/galaxy-studio/vault")
        j = r.json() if r.status_code == 200 else {}
        record("E5) GET /galaxy-studio/vault",
               r.status_code == 200 and "zips" in j and "apks" in j,
               f"zips={len(j.get('zips', []))} apks={len(j.get('apks', []))}")
    except Exception as e:
        record("E5) GET /galaxy-studio/vault", False, f"EXC {e}")

    # /file/{bid}/{path}
    try:
        r = get(f"/galaxy-studio/files/{build_id}")
        j = r.json() if r.status_code == 200 else {}
        files = j.get("files", [])
        if files:
            sample_path = files[0].get("path")
            r2 = get(f"/galaxy-studio/file/{build_id}/{sample_path}")
            j2 = r2.json() if r2.status_code == 200 else {}
            record("E6) GET /file/{bid}/{path}",
                   r2.status_code == 200 and "content" in j2,
                   f"HTTP {r2.status_code} sample={sample_path} content_len={len(j2.get('content', ''))}")
        else:
            record("E6) GET /file/{bid}/{path}", False, "no files to sample")
    except Exception as e:
        record("E6) GET /file/{bid}/{path}", False, f"EXC {e}")

    # ────────── SUMMARY ──────────
    print("\n" + "=" * 80)
    passed = sum(1 for r in results if r["ok"])
    failed = sum(1 for r in results if not r["ok"])
    print(f"TOTAL: {len(results)}  PASS: {passed}  FAIL: {failed}")
    print("=" * 80)
    for r in results:
        if not r["ok"]:
            print(f"  ❌ {r['name']}: {r['detail']}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
