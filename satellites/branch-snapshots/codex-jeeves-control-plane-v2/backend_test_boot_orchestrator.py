"""
SOTA Boot Orchestrator backend test driver
Verifies the 10 acceptance criteria from /app/test_result.md
"""
import os
import sys
import json
import time
import requests

# Resolve backend URL
BACKEND_URL = None
env_path = "/app/frontend/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
                BACKEND_URL = line.split("=", 1)[1].strip()
                break
if not BACKEND_URL:
    BACKEND_URL = "http://localhost:8001"

API = BACKEND_URL.rstrip("/") + "/api"
print(f"Using API base: {API}\n")

results = []  # (id, name, passed, note)

def record(idx, name, passed, note=""):
    status = "PASS" if passed else "FAIL"
    results.append((idx, name, passed, note))
    print(f"[{status}] #{idx} {name} — {note}")


# 1) GET /health/boot/score
try:
    r = requests.get(f"{API}/health/boot/score", timeout=15)
    j = r.json()
    counts = j.get("counts") or {}
    required_keys = {"ok", "boot_score", "counts", "critical_ok", "elapsed_s"}
    required_count_keys = {"ok", "failed", "skipped", "pending", "total"}
    boot_score = j.get("boot_score")
    okc = (
        r.status_code == 200
        and required_keys.issubset(j.keys())
        and required_count_keys.issubset(counts.keys())
        and isinstance(boot_score, (int, float))
        and 0 <= boot_score <= 100
        and boot_score > 0
    )
    record(
        1,
        "GET /health/boot/score",
        okc,
        f"status={r.status_code} boot_score={boot_score} counts={counts} critical_ok={j.get('critical_ok')} elapsed_s={j.get('elapsed_s')}",
    )
except Exception as e:
    record(1, "GET /health/boot/score", False, f"exception: {e}")


# 2) GET /health/boot/stages → has 4 expected stages
expected_stages = {"mongo-ping", "mongo-indexes-verify", "feature-flags-ready", "tunnel-watchdog-ready"}
stage_required_keys = {"name", "phase", "critical", "deps", "weight", "status", "attempts", "duration_s", "description"}
all_stages = []
try:
    r = requests.get(f"{API}/health/boot/stages", timeout=15)
    j = r.json()
    all_stages = j.get("stages") or []
    names = {s.get("name") for s in all_stages}
    missing = expected_stages - names
    schema_ok = all(stage_required_keys.issubset(s.keys()) for s in all_stages)
    okc = r.status_code == 200 and not missing and schema_ok and len(all_stages) >= 4
    record(
        2,
        "GET /health/boot/stages",
        okc,
        f"status={r.status_code} count={len(all_stages)} missing={missing} schema_ok={schema_ok}",
    )
except Exception as e:
    record(2, "GET /health/boot/stages", False, f"exception: {e}")


# 3) GET /health/boot/stages?phase_max=0 → subset
try:
    r = requests.get(f"{API}/health/boot/stages", params={"phase_max": 0}, timeout=15)
    j = r.json()
    stages0 = j.get("stages") or []
    all_phase_le_0 = all(s.get("phase", 99) <= 0 for s in stages0)
    is_subset = {s.get("name") for s in stages0}.issubset({s.get("name") for s in all_stages})
    smaller_or_equal = len(stages0) <= len(all_stages)
    okc = r.status_code == 200 and all_phase_le_0 and is_subset and smaller_or_equal and len(stages0) > 0
    record(
        3,
        "GET /health/boot/stages?phase_max=0",
        okc,
        f"status={r.status_code} returned={len(stages0)} names={[s.get('name') for s in stages0]} all_phase_le_0={all_phase_le_0}",
    )
except Exception as e:
    record(3, "GET /health/boot/stages?phase_max=0", False, f"exception: {e}")


# 4) GET /health/boot/timeline?limit=20
try:
    r = requests.get(f"{API}/health/boot/timeline", params={"limit": 20}, timeout=15)
    j = r.json()
    events = j.get("events") or []
    stats = j.get("stats") or {}
    types = {e.get("type") for e in events}
    stats_required = {"total", "capacity", "counts", "boot_at", "uptime_s"}
    okc = (
        r.status_code == 200
        and j.get("ok") is True
        and stats_required.issubset(stats.keys())
        and "stage_started" in types
        and "stage_ok" in types
    )
    record(
        4,
        "GET /health/boot/timeline?limit=20",
        okc,
        f"status={r.status_code} event_count={len(events)} types={types} stats_keys={list(stats.keys())}",
    )
except Exception as e:
    record(4, "GET /health/boot/timeline?limit=20", False, f"exception: {e}")


# 5) GET /health/boot/timeline?after_ts=99999999999
try:
    r = requests.get(f"{API}/health/boot/timeline", params={"after_ts": 99999999999}, timeout=15)
    j = r.json()
    events = j.get("events") or []
    okc = r.status_code == 200 and events == []
    record(
        5,
        "GET /health/boot/timeline?after_ts=<future>",
        okc,
        f"status={r.status_code} event_count={len(events)}",
    )
except Exception as e:
    record(5, "GET /health/boot/timeline?after_ts=<future>", False, f"exception: {e}")


# 6) POST /health/boot/replay/mongo-ping
try:
    r = requests.post(f"{API}/health/boot/replay/mongo-ping", timeout=20)
    j = r.json()
    stage = j.get("stage") or {}
    okc = r.status_code == 200 and j.get("ok") is True and stage.get("status") == "ok"
    record(
        6,
        "POST /health/boot/replay/mongo-ping",
        okc,
        f"status={r.status_code} ok={j.get('ok')} stage.status={stage.get('status')} duration_s={stage.get('duration_s')}",
    )
except Exception as e:
    record(6, "POST /health/boot/replay/mongo-ping", False, f"exception: {e}")


# 7) POST /health/boot/replay/__nonexistent__ → 404
try:
    r = requests.post(f"{API}/health/boot/replay/__nonexistent__", timeout=15)
    okc = r.status_code == 404
    record(
        7,
        "POST /health/boot/replay/__nonexistent__",
        okc,
        f"status={r.status_code}",
    )
except Exception as e:
    record(7, "POST /health/boot/replay/__nonexistent__", False, f"exception: {e}")


# 8) POST /telemetry/boot
payload = {
    "ok": True,
    "boot_score": 92.5,
    "counts": {"ok": 6, "failed": 0, "skipped": 0, "pending": 0, "total": 6},
    "elapsed_ms": 1240,
    "stages": {"backend": {"status": "ok", "durationMs": 420}},
}
try:
    r = requests.post(f"{API}/telemetry/boot", json=payload, timeout=15)
    j = r.json()
    buffered = j.get("buffered", 0)
    okc = r.status_code == 200 and j.get("ok") is True and buffered >= 1
    record(
        8,
        "POST /telemetry/boot",
        okc,
        f"status={r.status_code} ok={j.get('ok')} buffered={buffered}",
    )
except Exception as e:
    record(8, "POST /telemetry/boot", False, f"exception: {e}")


# 9) GET /telemetry/boot?limit=5
try:
    r = requests.get(f"{API}/telemetry/boot", params={"limit": 5}, timeout=15)
    j = r.json()
    reports = j.get("reports") or []
    count = j.get("count", 0)
    avg = j.get("avg_boot_score")
    p95 = j.get("p95_elapsed_ms", "MISSING_KEY")
    # Find most recent report (first in list normally)
    most_recent_score = reports[0].get("boot_score") if reports else None
    okc = (
        r.status_code == 200
        and j.get("ok") is True
        and count >= 1
        and isinstance(avg, (int, float))
        and (p95 is None or isinstance(p95, (int, float)))
        and most_recent_score == 92.5
    )
    record(
        9,
        "GET /telemetry/boot?limit=5",
        okc,
        f"status={r.status_code} count={count} avg={avg} p95={p95} most_recent_score={most_recent_score}",
    )
except Exception as e:
    record(9, "GET /telemetry/boot?limit=5", False, f"exception: {e}")


# 10) Regression GET /api/health/runtime + /api/health/tunnel
try:
    r1 = requests.get(f"{API}/health/runtime", timeout=15)
    r2 = requests.get(f"{API}/health/tunnel", timeout=15)
    okc = r1.status_code == 200 and r2.status_code == 200
    record(
        10,
        "Regression /health/runtime + /health/tunnel",
        okc,
        f"runtime={r1.status_code} tunnel={r2.status_code}",
    )
except Exception as e:
    record(10, "Regression /health/runtime + /health/tunnel", False, f"exception: {e}")


# Summary
print("\n========== SUMMARY ==========")
passed = sum(1 for r in results if r[2])
failed = sum(1 for r in results if not r[2])
print(f"Passed: {passed}/{len(results)} | Failed: {failed}")
for idx, name, ok, note in results:
    print(f"  #{idx} {'OK ' if ok else 'XX '} {name}")

sys.exit(0 if failed == 0 else 1)
