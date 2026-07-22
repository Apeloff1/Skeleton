"""
Backend test script for Telemetry & Security observability endpoints.

Tests:
  - POST /api/telemetry/event
  - POST /api/telemetry/batch
  - POST /api/telemetry/last-crash
  - GET  /api/telemetry/recent (+ filters)
  - GET  /api/telemetry/sessions
  - GET  /api/telemetry/summary
  - GET  /api/security/audit
  - GET  /api/security/audit-summary
  - GET  /api/security/rate-limits
  - GET  /api/security/health
  - GET  /api/binary/inspect/real_runnable_v1 (regression)
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

import requests


def _load_backend_url() -> str:
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL missing from /app/frontend/.env")


BASE = _load_backend_url().rstrip("/")
API = f"{BASE}/api"
TIMEOUT = 30

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ PASS: {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} :: {detail}")
        print(f"  ❌ FAIL: {name} :: {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def post(path: str, payload: dict) -> requests.Response:
    return requests.post(f"{API}{path}", json=payload, timeout=TIMEOUT)


def get(path: str, **params) -> requests.Response:
    return requests.get(f"{API}{path}", params=params, timeout=TIMEOUT)


def main() -> int:
    print(f"BASE URL: {BASE}")
    print(f"API URL:  {API}")

    # ─── INGEST ─────────────────────────────────────────────
    section("1) POST /api/telemetry/event")
    r = post("/telemetry/event", {
        "modal_id": "TestModal",
        "session_id": "sess_a",
        "event": "open",
        "severity": "info",
    })
    check("event status 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        body = r.json()
        check("event returns ok=true", body.get("ok") is True, f"body={body}")

    section("2) POST /api/telemetry/batch (4 events)")
    batch_payload = {
        "events": [
            {"modal_id": "TestModal", "session_id": "sess_a", "event": "open", "severity": "info"},
            {"modal_id": "TestModal", "session_id": "sess_a", "event": "action", "severity": "info", "detail": {"k": "v"}},
            {"modal_id": "TestModal", "session_id": "sess_a", "event": "close", "severity": "info", "duration_ms": 1234},
            {"modal_id": "OtherModal", "session_id": "sess_b", "event": "error", "severity": "error", "detail": "boom"},
        ]
    }
    r = post("/telemetry/batch", batch_payload)
    check("batch status 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        body = r.json()
        check("batch ok=true", body.get("ok") is True, f"body={body}")
        check("batch ingested=4", body.get("ingested") == 4, f"ingested={body.get('ingested')}")

    section("3) POST /api/telemetry/last-crash")
    r = post("/telemetry/last-crash", {
        "source": "ErrorBoundary",
        "component": "SomeScreen",
        "message": "Boom",
        "stack": "at line 42",
        "session_id": "sess_a",
    })
    check("crash status 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        check("crash ok=true", r.json().get("ok") is True, f"body={r.json()}")

    # Give a moment for ring writes to settle
    time.sleep(0.5)

    # ─── READ ───────────────────────────────────────────────
    section("4) GET /api/telemetry/recent?limit=20")
    r = get("/telemetry/recent", limit=20)
    check("recent status 200", r.status_code == 200, f"status={r.status_code}")
    events = []
    if r.status_code == 200:
        body = r.json()
        check("recent has count field", "count" in body)
        check("recent has events list", isinstance(body.get("events"), list))
        events = body.get("events", [])
        # Verify steps 1-3 are present
        has_test_open = any(e.get("modal_id") == "TestModal" and e.get("event") == "open" for e in events)
        has_test_action = any(e.get("modal_id") == "TestModal" and e.get("event") == "action" for e in events)
        has_test_close = any(e.get("modal_id") == "TestModal" and e.get("event") == "close" for e in events)
        has_other_error = any(e.get("modal_id") == "OtherModal" and e.get("event") == "error" for e in events)
        has_crash = any(e.get("event") == "crash" for e in events)
        check("recent contains TestModal open event", has_test_open)
        check("recent contains TestModal action event", has_test_action)
        check("recent contains TestModal close event", has_test_close)
        check("recent contains OtherModal error event", has_other_error)
        check("recent contains crash event from step 3", has_crash)

    section("5) GET /api/telemetry/recent?modal_id=TestModal")
    r = get("/telemetry/recent", modal_id="TestModal", limit=200)
    check("filter modal_id status 200", r.status_code == 200)
    if r.status_code == 200:
        ev = r.json().get("events", [])
        all_test_modal = all(e.get("modal_id") == "TestModal" for e in ev)
        check("filter modal_id returns only TestModal", all_test_modal and len(ev) > 0,
              f"count={len(ev)} sample={ev[:1]}")

    section("6) GET /api/telemetry/recent?severity=error")
    r = get("/telemetry/recent", severity="error", limit=200)
    check("filter severity status 200", r.status_code == 200)
    if r.status_code == 200:
        ev = r.json().get("events", [])
        all_error = all(e.get("severity") == "error" for e in ev)
        check("filter severity returns only error", all_error and len(ev) > 0,
              f"count={len(ev)} sample={ev[:1]}")

    section("7) GET /api/telemetry/sessions?limit=10")
    r = get("/telemetry/sessions", limit=10)
    check("sessions status 200", r.status_code == 200)
    if r.status_code == 200:
        body = r.json()
        check("sessions has count field", "count" in body)
        check("sessions has sessions list", isinstance(body.get("sessions"), list))
        sess = body.get("sessions", [])
        check("sessions list non-empty", len(sess) > 0)
        if sess:
            s = sess[0]
            check("session has events field", "events" in s, f"sess={s}")
            check("session has modal_count field", "modal_count" in s, f"sess={s}")
            check("session has duration_s field", "duration_s" in s, f"sess={s}")
            check("session has errors field", "errors" in s, f"sess={s}")
            # check that sess_a and sess_b exist
            ids = {x.get("session_id") for x in sess}
            check("session list includes sess_a", "sess_a" in ids, f"ids={ids}")
            check("session list includes sess_b", "sess_b" in ids, f"ids={ids}")

    section("8) GET /api/telemetry/summary")
    r = get("/telemetry/summary")
    check("summary status 200", r.status_code == 200)
    if r.status_code == 200:
        body = r.json()
        for field in ("total_events", "errors", "error_rate", "top_modals",
                      "by_event", "by_severity", "ring_capacity", "ring_size_now"):
            check(f"summary has '{field}'", field in body, f"body keys={list(body.keys())}")
        check("summary ring_capacity = 10000", body.get("ring_capacity") == 10000,
              f"ring_capacity={body.get('ring_capacity')}")

    # ─── SECURITY OBSERVABILITY ──────────────────────────────
    section("9) GET /api/security/audit?limit=20")
    r = get("/security/audit", limit=20)
    check("audit status 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        body = r.json()
        check("audit has entries list", isinstance(body.get("entries"), list),
              f"keys={list(body.keys())}")
        check("audit entries non-empty", len(body.get("entries", [])) > 0)

    section("10) GET /api/security/audit-summary")
    r = get("/security/audit-summary")
    check("audit-summary status 200", r.status_code == 200)
    if r.status_code == 200:
        body = r.json()
        for field in ("total_requests", "errors", "error_rate", "avg_ms",
                      "statuses", "top_paths", "slowest"):
            check(f"audit-summary has '{field}'", field in body,
                  f"body keys={list(body.keys())}")

    section("11) GET /api/security/rate-limits")
    r = get("/security/rate-limits")
    check("rate-limits status 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        body = r.json()
        check("rate-limits is dict/list",
              isinstance(body, (dict, list)),
              f"type={type(body).__name__}")

    section("12) GET /api/security/health")
    r = get("/security/health")
    check("health status 200", r.status_code == 200)
    if r.status_code == 200:
        body = r.json()
        for field in ("ok", "error_rate", "audit_summary", "rate_limit",
                      "telemetry_ring_size", "ts"):
            check(f"health has '{field}'", field in body,
                  f"body keys={list(body.keys())}")

    # ─── REGRESSION GUARDRAIL ────────────────────────────────
    section("13) GET /api/binary/inspect/real_runnable_v1 (APK pipeline)")
    r = get("/binary/inspect/real_runnable_v1")
    check("binary inspect status 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        body = r.json()
        check("is_installable=true", body.get("is_installable_apk") is True,
              f"is_installable_apk={body.get('is_installable_apk')}")
        # classes.dex size — exposed under structure.classes_dex_size
        dex_size = None
        struct = body.get("structure") or {}
        for key in ("classes_dex_size", "dex_size", "classes_dex_bytes"):
            if isinstance(struct.get(key), int):
                dex_size = struct[key]
                break
        if dex_size is None:
            for key in ("classes_dex_size", "dex_size", "classes_dex_bytes"):
                if key in body:
                    dex_size = body[key]
                    break
        if dex_size is None:
            classes = body.get("classes") or {}
            if isinstance(classes, dict):
                dex_size = classes.get("dex") or classes.get("classes.dex") or classes.get("size")
        # Also check 'entries' / 'files' arrays for classes.dex
        if dex_size is None:
            entries = body.get("entries") or body.get("files") or []
            for e in entries:
                if isinstance(e, dict) and (
                    e.get("name") == "classes.dex" or e.get("path") == "classes.dex"
                ):
                    dex_size = e.get("size") or e.get("bytes")
                    break
        check("classes.dex >= 10000 bytes",
              isinstance(dex_size, int) and dex_size >= 10000,
              f"dex_size={dex_size} body={json.dumps(body)[:600]}")

    # ─── SUMMARY ─────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed (total {PASS + FAIL})")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print(f"  ❌ {f}")
    print(f"{'=' * 60}\n")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
