"""
Backend tests for the P3 Feature Flags MEGA UPGRADE batch.

Covers:
  a-h) Regression checks
  1-10) New upgrade checks (ETag/304, bulk, audit, impressions, metrics, rate-limit, admin token, version)
"""
from __future__ import annotations

import os
import sys
import time
import json
from pathlib import Path
from typing import Any

import requests


# ── Resolve base URL (prefer EXPO_PUBLIC_BACKEND_URL from frontend/.env) ─────
def _resolve_base_url() -> str:
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
                _, _, v = line.partition("=")
                v = v.strip().strip('"').strip("'")
                if v:
                    return v.rstrip("/") + "/api"
    return "http://localhost:8001/api"


BASE_URL = _resolve_base_url()
print(f"[ff-mega-test] Using BASE_URL={BASE_URL}")


# ── Tracking ─────────────────────────────────────────────────────────────────
results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond, detail))
    icon = "✅" if cond else "❌"
    print(f"{icon} {name} — {detail}")


# ── Regression checks (a–h) ──────────────────────────────────────────────────
def test_regression() -> None:
    # a) GET list
    r = requests.get(f"{BASE_URL}/feature-flags", timeout=15)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    flags = body.get("flags", []) if isinstance(body, dict) else []
    check("a) GET /feature-flags → 200 with >=8 default flags",
          r.status_code == 200 and isinstance(flags, list) and len(flags) >= 8,
          f"status={r.status_code}, flags={len(flags)}")

    # b) GET ?user_id=alice → every flag has resolved boolean
    r = requests.get(f"{BASE_URL}/feature-flags", params={"user_id": "alice"}, timeout=15)
    body = r.json()
    fl = body.get("flags", [])
    all_bool = all(isinstance(f.get("resolved"), bool) for f in fl)
    check("b) GET ?user_id=alice → resolved booleans",
          r.status_code == 200 and all_bool and len(fl) >= 8,
          f"status={r.status_code}, all_resolved_bool={all_bool}")

    # c) GET /{name}
    r = requests.get(f"{BASE_URL}/feature-flags/hub.network_banner", timeout=15)
    body = r.json()
    check("c) GET /{name} (hub.network_banner) → 200",
          r.status_code == 200 and body.get("ok") is True and isinstance(body.get("flag"), dict),
          f"status={r.status_code}")

    # d) GET unknown → 404
    r = requests.get(f"{BASE_URL}/feature-flags/__does_not_exist_qa__", timeout=15)
    check("d) GET /__does_not_exist__ → 404", r.status_code == 404, f"status={r.status_code}")

    # e) POST upsert
    r = requests.post(f"{BASE_URL}/feature-flags/qa.regression",
                      json={"enabled": True, "rollout": 33, "description": "qa"},
                      timeout=15)
    body = r.json() if r.ok else {}
    flag = body.get("flag", {}) if isinstance(body, dict) else {}
    check("e) POST /{name} upsert → 200 with values",
          r.status_code == 200 and flag.get("enabled") is True
          and flag.get("rollout") == 33 and flag.get("description") == "qa",
          f"status={r.status_code}, flag={json.dumps(flag, default=str)[:120]}")

    # f) DELETE
    r = requests.delete(f"{BASE_URL}/feature-flags/qa.regression", timeout=15)
    body = r.json() if r.ok else {}
    check("f) DELETE /{name} → 200 ok:true",
          r.status_code == 200 and body.get("ok") is True,
          f"status={r.status_code}")

    # g) /health → exposes total/enabled/version
    r = requests.get(f"{BASE_URL}/feature-flags/health", timeout=15)
    body = r.json()
    has_total = "total_flags" in body
    has_enabled = "enabled_flags" in body
    has_version = "version" in body or "cache_ttl_s" in body  # version optional in health
    check("g) GET /health → total_flags + enabled_flags exposed",
          r.status_code == 200 and has_total and has_enabled,
          f"keys={list(body.keys())[:8]}")

    # h) Stable bucketing — rollout=10 flag for same user_id
    target = "experimental.live_collab_v2"  # rollout=10 from defaults
    seq: list[bool] = []
    for _ in range(5):
        r = requests.get(f"{BASE_URL}/feature-flags",
                         params={"user_id": "alice"}, timeout=15)
        f = next((f for f in r.json().get("flags", []) if f.get("name") == target), None)
        if f is not None:
            seq.append(bool(f.get("resolved")))
    stable = len(set(seq)) == 1 and len(seq) == 5
    check("h) Stable bucketing alice × rollout=10 across 5 calls",
          stable, f"sequence={seq}")


# ── New upgrade checks (1–10) ────────────────────────────────────────────────
def test_upgrades() -> None:
    # 1) GET includes `version` integer
    r = requests.get(f"{BASE_URL}/feature-flags", timeout=15)
    body = r.json()
    v1 = body.get("version")
    check("1) GET response includes integer `version`",
          isinstance(v1, int), f"version={v1!r}")

    # 2) Response headers include ETag, Cache-Control, Server-Timing
    etag = r.headers.get("ETag") or r.headers.get("etag")
    cc = r.headers.get("Cache-Control") or r.headers.get("cache-control")
    st = r.headers.get("Server-Timing") or r.headers.get("server-timing")
    check("2) Headers ETag + Cache-Control + Server-Timing present",
          bool(etag) and bool(cc) and bool(st)
          and "ff-v" in (etag or "")
          and "ff_list" in (st or ""),
          f"etag={etag!r}, cc={cc!r}, st={st!r}")

    # 3) Re-GET with If-None-Match → 304
    if etag:
        r2 = requests.get(f"{BASE_URL}/feature-flags",
                          headers={"If-None-Match": etag}, timeout=15)
        check("3) If-None-Match → 304 (no body)",
              r2.status_code == 304 and (not r2.content or r2.content == b""),
              f"status={r2.status_code}, content_len={len(r2.content)}")
    else:
        check("3) If-None-Match → 304", False, "no ETag from initial GET")

    # 4) /bulk upsert route — must not be shadowed by /{name}
    r = requests.post(
        f"{BASE_URL}/feature-flags/bulk",
        json={"flags": [
            {"name": "qa.bulkA", "enabled": True, "rollout": 25},
            {"name": "qa.bulkB", "enabled": False},
        ]},
        timeout=15,
    )
    body = r.json() if r.ok else {}
    check("4) POST /bulk → ok:true, applied:2 (not shadowed by /{name})",
          r.status_code == 200 and body.get("ok") is True and body.get("applied") == 2,
          f"status={r.status_code}, body={body}")

    # Verify bulk upsert actually persisted
    rA = requests.get(f"{BASE_URL}/feature-flags/qa.bulkA", timeout=10)
    rB = requests.get(f"{BASE_URL}/feature-flags/qa.bulkB", timeout=10)
    persisted = (rA.status_code == 200 and rA.json().get("flag", {}).get("rollout") == 25
                 and rB.status_code == 200 and rB.json().get("flag", {}).get("enabled") is False)
    check("4b) /bulk results persisted (qa.bulkA & qa.bulkB readable)",
          persisted, f"A={rA.status_code} B={rB.status_code}")

    # 5) Audit log — POST a flag then check audit?name=
    audit_name = "qa.audit_target"
    requests.post(f"{BASE_URL}/feature-flags/{audit_name}",
                  json={"enabled": True, "rollout": 77, "description": "audit"},
                  timeout=15)
    # small wait so audit row commits
    time.sleep(0.5)
    ra = requests.get(f"{BASE_URL}/feature-flags/audit",
                     params={"name": audit_name, "limit": 20}, timeout=15)
    abody = ra.json() if ra.ok else {}
    rows = abody.get("rows", []) if isinstance(abody, dict) else []
    upsert_row = next((r for r in rows
                       if r.get("action") == "upsert" and r.get("name") == audit_name), None)
    diff_non_empty = bool(upsert_row and upsert_row.get("diff"))
    check("5a) GET /audit?name=… returns matching upsert row with non-empty diff",
          ra.status_code == 200 and abody.get("ok") is True
          and upsert_row is not None and diff_non_empty,
          f"status={ra.status_code}, rows={len(rows)}, has_upsert={upsert_row is not None}, diff={bool(upsert_row and upsert_row.get('diff'))}")

    # /audit (unfiltered) — top-level shape
    ra2 = requests.get(f"{BASE_URL}/feature-flags/audit", params={"limit": 20}, timeout=15)
    ab2 = ra2.json() if ra2.ok else {}
    check("5b) GET /audit?limit=20 → {ok, stats, rows[]}",
          ra2.status_code == 200 and ab2.get("ok") is True
          and isinstance(ab2.get("stats"), dict) and isinstance(ab2.get("rows"), list),
          f"keys={list(ab2.keys()) if isinstance(ab2, dict) else 'n/a'}")

    # Clean audit_name
    requests.delete(f"{BASE_URL}/feature-flags/{audit_name}", timeout=10)

    # 6) Impressions
    r = requests.post(f"{BASE_URL}/feature-flags/impressions",
                     json={"rows": [
                         {"name": "hub.network_banner", "value": True, "count": 3},
                         {"name": "experimental.live_collab_v2", "value": False, "count": 1},
                     ]}, timeout=15)
    body = r.json() if r.ok else {}
    check("6) POST /impressions → ok:true, accepted:2",
          r.status_code == 200 and body.get("ok") is True and body.get("accepted") == 2,
          f"status={r.status_code}, body={body}")

    # 7) Metrics
    r = requests.get(f"{BASE_URL}/feature-flags/metrics", timeout=15)
    body = r.json() if r.ok else {}
    prom_lines = body.get("prom_lines", []) if isinstance(body, dict) else []
    help_count = sum(1 for ln in prom_lines if isinstance(ln, str) and ln.startswith("# HELP"))
    type_count = sum(1 for ln in prom_lines if isinstance(ln, str) and ln.startswith("# TYPE"))
    flusher_ok = body.get("flusher_alive") is True
    check("7) GET /metrics → ok, flusher_alive=true, prom HELP+TYPE present",
          r.status_code == 200 and body.get("ok") is True and flusher_ok
          and help_count >= 1 and type_count >= 1,
          f"flusher_alive={body.get('flusher_alive')}, help={help_count}, type={type_count}, prom_lines={len(prom_lines)}")

    # 8) Rate-limit — 12 rapid POSTs, expect >=1 HTTP 429
    statuses: list[int] = []
    rl_names: list[str] = []
    for i in range(12):
        nm = f"test.rl_{i}_{int(time.time()*1000)%100000}"
        rl_names.append(nm)
        rr = requests.post(f"{BASE_URL}/feature-flags/{nm}",
                           json={"enabled": True, "rollout": 1}, timeout=10)
        statuses.append(rr.status_code)
    n429 = sum(1 for s in statuses if s == 429)
    check("8) Rate-limit (12 rapid POSTs ⇒ ≥1 HTTP 429)",
          n429 >= 1, f"statuses={statuses}, n429={n429}")
    # Best-effort cleanup of any created RL flags
    for nm in rl_names:
        try:
            requests.delete(f"{BASE_URL}/feature-flags/{nm}", timeout=5)
        except Exception:
            pass

    # 9) Admin token gating — env unset → mutations open (already exercised by 4/5/6/8)
    # We can't toggle the env at runtime here, so confirm dev-open semantics:
    test_open = requests.post(f"{BASE_URL}/feature-flags/qa.admin_open_test",
                              json={"enabled": True, "rollout": 7}, timeout=10)
    check("9) Admin token unset → mutations open (dev mode)",
          test_open.status_code == 200,
          f"status={test_open.status_code}")
    requests.delete(f"{BASE_URL}/feature-flags/qa.admin_open_test", timeout=10)

    # 10) Admin fields surfaced when env unset
    r = requests.get(f"{BASE_URL}/feature-flags", timeout=15)
    flags = r.json().get("flags", [])
    sample = flags[0] if flags else {}
    has_overrides = "overrides" in sample
    has_created = "created_at" in sample
    check("10) GET list exposes admin-only fields when token env unset",
          has_overrides or has_created,
          f"has_overrides={has_overrides}, has_created_at={has_created}, sample_keys={list(sample.keys())[:12]}")

    # Cleanup bulk-test flags
    for nm in ("qa.bulkA", "qa.bulkB"):
        try:
            requests.delete(f"{BASE_URL}/feature-flags/{nm}", timeout=5)
        except Exception:
            pass


# ── Runner ───────────────────────────────────────────────────────────────────
def main() -> int:
    print("\n=== Regression checks (a–h) ===")
    test_regression()
    print("\n=== New upgrade checks (1–10) ===")
    test_upgrades()

    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, det in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {det if not ok else ''}")
    print(f"\nTotal: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
