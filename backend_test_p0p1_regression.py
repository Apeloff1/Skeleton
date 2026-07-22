#!/usr/bin/env python3
"""
Galaxy Studio P0/P1 regression sweep — 2026-05-13.

Verifies the four fixes:
  Fix #1 — Tolerant /create schema (4 variants must return 200)
  Fix #2 — /files/{build_id} falls through to vault after force-complete
  Fix #3 — /vault/zip/{build_id} falls through to vault after force-complete
  Fix #4 — File-count floor (≥ 48,000 default, explicit values preserved)

Plus regression checks for /manifest, /genres, /db-status, /watchdog/health.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import requests

BASE = os.environ.get(
    "BACKEND_BASE_URL",
    "https://gemini-game-craft.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE}/api/galaxy-studio"
TIMEOUT = 60

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    icon = "✅" if ok else "❌"
    print(f"{icon} {name}  {detail}")
    results.append((name, ok, detail))


def cleanup(build_id: str | None) -> None:
    """Force-complete (idempotent) + clear-zombies after each variant."""
    if build_id:
        try:
            requests.post(f"{API}/force-complete/{build_id}", timeout=TIMEOUT)
        except Exception:
            pass
    try:
        requests.post(f"{API}/clear-zombies", timeout=TIMEOUT)
    except Exception:
        pass


def post_create(payload: dict[str, Any], retries: int = 3) -> tuple[int, dict | str]:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.post(f"{API}/create", json=payload, timeout=TIMEOUT)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, r.text
        except Exception as exc:
            last_exc = exc
            time.sleep(2 + attempt * 2)
    return -1, f"timeout after {retries}: {last_exc}"


def get_with_retries(url: str, retries: int = 3) -> tuple[int, Any]:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, r.text
        except Exception as exc:
            last = exc
            time.sleep(2 + attempt * 2)
    return -1, f"err: {last}"


def get_status(build_id: str, retries: int = 3) -> tuple[int, dict | str]:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(f"{API}/status/{build_id}", timeout=TIMEOUT)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, r.text
        except Exception as exc:
            last_exc = exc
            time.sleep(2 + attempt * 2)
    return -1, f"timeout after {retries} attempts: {last_exc}"


# ── REGRESSION CHECKS (run early so we know the surface is alive) ───────────
def regression_checks() -> None:
    print("\n═══ REGRESSION CHECKS ═══")
    for name, url in [
        ("GET /manifest", f"{API}/manifest"),
        ("GET /genres", f"{API}/genres"),
        ("GET /db-status", f"{API}/db-status"),
        ("GET /watchdog/health", f"{API}/watchdog/health"),
    ]:
        try:
            r = requests.get(url, timeout=TIMEOUT)
            ok = r.status_code == 200
            try:
                body = r.json()
                shape = (
                    f"keys={list(body.keys())[:6]}"
                    if isinstance(body, dict)
                    else f"type={type(body).__name__}"
                )
            except Exception:
                shape = f"len={len(r.text)}"
            record(name, ok, f"HTTP {r.status_code}; {shape}")
        except Exception as exc:
            record(name, False, f"ERR {exc}")


# ── FIX #1 — TOLERANT /create SCHEMA ────────────────────────────────────────
VARIANTS = [
    (
        "A",
        {
            "title": "Variant A",
            "genre": "rpg",
            "complexity": "intermediate",
            "extra_params": "",
            "system_arch": "client-server",
            "age_year": 2026,
            "scale": "100,000 files",
            "target_files": 100000,
        },
        100000,
    ),
    (
        "B",
        {
            "title": "Variant B",
            "genre": "rpg",
            "complexity": "godlike",
            "extra_params": {"foo": 5},
            "system_architecture": "canonical",
            "age_era_year": 1995,
            "scale": "500,000 files",
            "target_files": 500000,
        },
        500000,
    ),
    (
        "C",
        {
            "title": "Variant C",
            "genre": "rpg",
            "complexity": 7,
            "scale": "",
            "target_files": 0,
        },
        None,  # floor — should be ≥ 48000
    ),
    (
        "D",
        {
            "title": "Variant D",
            "genre": "action",
            "complexity": "beginner",
            "extra_params": '{"a":1}',
            "scale": "1m",
            "target_files": 1000000,
        },
        1000000,
    ),
]


def run_variants() -> dict[str, str | None]:
    """Returns {variant_letter: build_id_or_None}."""
    print("\n═══ FIX #1 — TOLERANT /create SCHEMA (4 VARIANTS) ═══")
    build_ids: dict[str, str | None] = {}
    for letter, payload, expected_target in VARIANTS:
        # 1) POST /create
        code, body = post_create(payload)
        ok_http = code == 200 and isinstance(body, dict) and bool(body.get("build_id"))
        bid = body.get("build_id") if isinstance(body, dict) else None
        record(
            f"Variant {letter} — POST /create",
            ok_http,
            f"HTTP {code}; build_id={bid}",
        )
        build_ids[letter] = bid

        if not bid:
            continue

        # 2) GET /status — must surface new payload aliases
        time.sleep(0.6)
        scode, sbody = get_status(bid)
        required_aliases = [
            "progress_percent",
            "phase_label",
            "phase",
            "target_files",
            "eta_seconds",
            "errors",
        ]
        if scode == 200 and isinstance(sbody, dict):
            missing = [k for k in required_aliases if k not in sbody]
            ok_aliases = not missing
            tf = sbody.get("target_files", 0)
            record(
                f"Variant {letter} — /status aliases present",
                ok_aliases,
                f"HTTP {scode}; missing={missing}; target_files={tf}",
            )

            # Floor / explicit-value check (Fix #4)
            if expected_target is None:
                ok_floor = isinstance(tf, int) and tf >= 48_000
                record(
                    f"Variant {letter} — target_files ≥ 48,000 floor",
                    ok_floor,
                    f"target_files={tf}",
                )
            else:
                ok_floor = tf == expected_target
                record(
                    f"Variant {letter} — target_files == {expected_target}",
                    ok_floor,
                    f"target_files={tf}",
                )
        else:
            record(
                f"Variant {letter} — /status aliases present",
                False,
                f"HTTP {scode}; body_type={type(sbody).__name__}",
            )

        # Cleanup AFTER variant checks unless this is Variant C (used for fixes 2+3)
        if letter != "C":
            cleanup(bid)

    return build_ids


# ── FIX #2 & #3 — Variant C: force-complete then /files + /vault/zip ────────
def run_post_complete_checks(bid: str) -> None:
    print("\n═══ FIX #2 + #3 — Variant C post-force-complete ═══")
    if not bid:
        record("Variant C present for fix-2/3", False, "no build_id captured")
        return

    # Step 1: brief sleep then force-complete
    time.sleep(1.2)
    try:
        r = requests.post(f"{API}/force-complete/{bid}", timeout=TIMEOUT)
        ok = r.status_code == 200
        try:
            body = r.json()
        except Exception:
            body = {}
        record(
            "POST /force-complete/{C}",
            ok,
            f"HTTP {r.status_code}; status={body.get('status') if isinstance(body, dict) else '-'}; file_count={body.get('file_count') if isinstance(body, dict) else '-'}",
        )
    except Exception as exc:
        record("POST /force-complete/{C}", False, f"ERR {exc}")
        return

    # Step 2: GET /files/{build_id} — must NOT be 400, total_files > 0, has source
    try:
        r = requests.get(f"{API}/files/{bid}", timeout=TIMEOUT)
        ok_http = r.status_code == 200
        body = {}
        try:
            body = r.json()
        except Exception:
            pass
        total = body.get("total_files", -1) if isinstance(body, dict) else -1
        source = body.get("source") if isinstance(body, dict) else None
        files = body.get("files") if isinstance(body, dict) else None
        ok_total = isinstance(total, int) and total > 0
        ok_files = isinstance(files, list)
        ok_source = source in ("memory", "vault", "empty")
        record(
            "GET /files/{C} — HTTP 200",
            ok_http,
            f"HTTP {r.status_code}",
        )
        record(
            "GET /files/{C} — total_files > 0",
            ok_total,
            f"total_files={total}",
        )
        record(
            "GET /files/{C} — files is list",
            ok_files,
            f"len={len(files) if isinstance(files, list) else 'n/a'}",
        )
        record(
            "GET /files/{C} — source field present",
            ok_source,
            f"source={source}",
        )
    except Exception as exc:
        record("GET /files/{C}", False, f"ERR {exc}")

    # Step 3: POST /vault/zip/{build_id} — must NOT be 400, returns vault_id
    try:
        r = requests.post(f"{API}/vault/zip/{bid}", timeout=TIMEOUT)
        ok_http = r.status_code == 200
        body = {}
        try:
            body = r.json()
        except Exception:
            pass
        vault_id = body.get("vault_id") if isinstance(body, dict) else None
        filename = body.get("filename") if isinstance(body, dict) else None
        dl_url = body.get("download_url") if isinstance(body, dict) else None
        record(
            "POST /vault/zip/{C} — HTTP 200",
            ok_http,
            f"HTTP {r.status_code}",
        )
        record(
            "POST /vault/zip/{C} — vault_id present",
            bool(vault_id),
            f"vault_id={vault_id}",
        )
        record(
            "POST /vault/zip/{C} — filename present",
            bool(filename),
            f"filename={filename}",
        )
        record(
            "POST /vault/zip/{C} — download_url present",
            bool(dl_url),
            f"download_url={dl_url}",
        )
    except Exception as exc:
        record("POST /vault/zip/{C}", False, f"ERR {exc}")

    # Cleanup
    cleanup(bid)


# ── MAIN ────────────────────────────────────────────────────────────────────
def main() -> int:
    print(f"BASE = {BASE}")
    print(f"API  = {API}")

    regression_checks()
    build_ids = run_variants()
    run_post_complete_checks(build_ids.get("C") or "")

    # Final clear-zombies pass
    try:
        requests.post(f"{API}/clear-zombies", timeout=TIMEOUT)
    except Exception:
        pass

    # Summary
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed
    print("\n" + "═" * 70)
    print(f"TOTAL: {passed}/{total} PASS — {failed} FAIL")
    print("═" * 70)
    if failed:
        print("\nFAILURES:")
        for name, ok, detail in results:
            if not ok:
                print(f"  ❌ {name}  — {detail}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
