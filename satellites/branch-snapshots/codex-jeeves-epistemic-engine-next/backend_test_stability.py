"""
Backend stability/observability hardening test driver.
Tests 5 endpoints:
  1) GET /api/health/tunnel
  2) GET /api/health/runtime
  3) POST /api/telemetry/trail
  4) GET /api/telemetry/trail
  5) GET /api/health (regression)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests


def _read_env(path: str, key: str) -> str | None:
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return None
    return None


BASE = (_read_env("/app/frontend/.env", "EXPO_PUBLIC_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    results.append((name, ok, info))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name} :: {info}")


def step(label: str) -> None:
    print(f"\n=== {label} ===")


def main() -> int:
    print(f"BASE: {API}")

    # 1) /health/tunnel
    step("1) GET /api/health/tunnel")
    try:
        r = requests.get(f"{API}/health/tunnel", timeout=15)
        check("1.http_200", r.status_code == 200, f"status={r.status_code}")
        j = r.json()
        check("1.ok_present", "ok" in j, f"ok={j.get('ok')}")
        check("1.status_value", j.get("status") in ("ok", "degraded", "down"), f"status={j.get('status')}")
        check("1.gap_number", isinstance(j.get("gap_since_last_request_s"), (int, float)),
              f"gap={j.get('gap_since_last_request_s')}")
        check("1.degraded_after_s_15", j.get("degraded_after_s") == 15 or j.get("degraded_after_s") == 15.0,
              f"deg_after_s={j.get('degraded_after_s')}")
        check("1.down_after_s_60", j.get("down_after_s") == 60 or j.get("down_after_s") == 60.0,
              f"down_after_s={j.get('down_after_s')}")
        check("1.flap_count_number", isinstance(j.get("flap_count_total"), (int, float)),
              f"flap={j.get('flap_count_total')}")
        check("1.uptime_s_nonneg", isinstance(j.get("uptime_s"), (int, float)) and j["uptime_s"] >= 0,
              f"uptime_s={j.get('uptime_s')}")
        check("1.tick_interval_s_5", j.get("tick_interval_s") == 5 or j.get("tick_interval_s") == 5.0,
              f"tick={j.get('tick_interval_s')}")
        check("1.history_size_number", isinstance(j.get("history_size"), (int, float)),
              f"history_size={j.get('history_size')}")
        check("1.recent_is_array", isinstance(j.get("recent"), list),
              f"recent_len={len(j.get('recent') or [])}")
    except Exception as e:
        check("1.exception", False, f"{type(e).__name__}: {e}")

    # 2) /health/runtime
    step("2) GET /api/health/runtime")
    try:
        r = requests.get(f"{API}/health/runtime", timeout=15)
        check("2.http_200", r.status_code == 200, f"status={r.status_code}")
        j = r.json()
        check("2.ok_true", j.get("ok") is True, f"ok={j.get('ok')}")
        check("2.ts_present", "ts" in j, f"ts={j.get('ts')}")
        check("2.uptime_s_present", "uptime_s" in j, f"uptime_s={j.get('uptime_s')}")
        check("2.pid_int_gt0", isinstance(j.get("pid"), int) and j["pid"] > 0, f"pid={j.get('pid')}")
        check("2.python_str", isinstance(j.get("python"), str), f"python={j.get('python')}")
        mem = j.get("memory") or {}
        check("2.memory.rss_kb_gt0", isinstance(mem.get("rss_kb"), (int, float)) and mem["rss_kb"] > 0,
              f"rss_kb={mem.get('rss_kb')}")
        check("2.open_fds_number", isinstance(j.get("open_fds"), (int, float)), f"open_fds={j.get('open_fds')}")
        gc = j.get("gc") or {}
        check("2.gc.counts_present", "counts" in gc, f"counts={gc.get('counts')}")
        check("2.gc.collections_present", "collections" in gc, f"collections={gc.get('collections')}")
        aio = j.get("asyncio") or {}
        check("2.asyncio.total_tasks", "total_tasks" in aio, f"total={aio.get('total_tasks')}")
        check("2.asyncio.pending_tasks", "pending_tasks" in aio, f"pending={aio.get('pending_tasks')}")
        mongo = j.get("mongo") or {}
        check("2.mongo.ok_true", mongo.get("ok") is True, f"mongo={mongo}")
        check("2.mongo.rtt_ms_lt_500",
              isinstance(mongo.get("rtt_ms"), (int, float)) and mongo["rtt_ms"] < 500,
              f"rtt_ms={mongo.get('rtt_ms')}")
        check("2.tunnel_present", isinstance(j.get("tunnel"), dict),
              f"tunnel_keys={list((j.get('tunnel') or {}).keys())[:5]}")
        ff = j.get("feature_flags") or {}
        check("2.feature_flags.ok_true", ff.get("ok") is True, f"ff_ok={ff.get('ok')}")
        check("2.feature_flags.total_flags_ge_8",
              isinstance(ff.get("total_flags"), (int, float)) and ff["total_flags"] >= 8,
              f"total_flags={ff.get('total_flags')}")
    except Exception as e:
        check("2.exception", False, f"{type(e).__name__}: {e}")

    # 3) POST /telemetry/trail
    step("3) POST /api/telemetry/trail")
    payload = {
        "rid": "qa-trail-1",
        "user_agent": "qa",
        "crumbs": [
            {"ts": 1, "category": "boot", "message": "hello"},
            {"ts": 2, "category": "nav", "message": "open hub", "level": "info", "data": {"foo": "bar"}},
        ],
    }
    try:
        r = requests.post(f"{API}/telemetry/trail", json=payload, timeout=15)
        check("3.http_200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
        j = r.json()
        check("3.ok_true", j.get("ok") is True, f"ok={j.get('ok')}")
        check("3.buffered_ge_1",
              isinstance(j.get("buffered"), (int, float)) and j["buffered"] >= 1,
              f"buffered={j.get('buffered')}")
    except Exception as e:
        check("3.exception", False, f"{type(e).__name__}: {e}")

    # 4) GET /telemetry/trail?limit=5
    step("4) GET /api/telemetry/trail?limit=5")
    try:
        r = requests.get(f"{API}/telemetry/trail", params={"limit": 5}, timeout=15)
        check("4.http_200", r.status_code == 200, f"status={r.status_code}")
        j = r.json()
        check("4.ok_true", j.get("ok") is True, f"ok={j.get('ok')}")
        check("4.count_ge_1", isinstance(j.get("count"), (int, float)) and j["count"] >= 1,
              f"count={j.get('count')}")
        trails = j.get("trails") or []
        check("4.trails_is_list", isinstance(trails, list), f"len={len(trails)}")
        if trails:
            most_recent = trails[-1]
            check("4.most_recent_rid_qa_trail_1", most_recent.get("rid") == "qa-trail-1",
                  f"rid={most_recent.get('rid')}")
        else:
            check("4.most_recent_rid_qa_trail_1", False, "no trails returned")
    except Exception as e:
        check("4.exception", False, f"{type(e).__name__}: {e}")

    # 5) Sanity: GET /api/health
    step("5) GET /api/health (regression)")
    try:
        r = requests.get(f"{API}/health", timeout=15)
        check("5.http_200", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        check("5.exception", False, f"{type(e).__name__}: {e}")

    # Summary
    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"{passed}/{total} checks passed")
    failed = [(n, info) for n, ok, info in results if not ok]
    for n, info in failed:
        print(f"  FAIL {n} :: {info}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
