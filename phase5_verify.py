"""Phase 5 verification - uncapping test (no auth)."""
import os
import json
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com")
API = f"{BASE}/api/galaxy-studio/swarm"

print(f"Using BASE={BASE}\n")

results = []

def record(name, passed, detail=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append((name, passed, detail))
    print(f"{status}: {name} — {detail}")

# ── 1) Legion simulate (defaults) ─────────────────────────────────────
print("=" * 70)
print("1) POST /discourse/legion/simulate (defaults — no seat_limit/max_full_swarm_voices)")
print("=" * 70)
body = {
    "build_id": "phase5_totality_001",
    "phase": "pTot",
    "game_ctx": {"genre": "rpg", "engine": "unreal"},
}
try:
    r = requests.post(f"{API}/discourse/legion/simulate", json=body, timeout=180)
    if r.status_code != 200:
        record("1) legion simulate HTTP 200", False, f"status={r.status_code}, body={r.text[:300]}")
    else:
        data = r.json()
        layers = data.get("layers", {})
        full_swarm = layers.get("full_swarm", {})
        legion_layer = layers.get("legion", {})
        teams = layers.get("teams", [])
        transcript = data.get("transcript", [])

        fs_voices = full_swarm.get("voices_sampled")
        record("1.a full_swarm.voices_sampled == 482", fs_voices == 482,
               f"got {fs_voices}")

        legion_seats = legion_layer.get("seats")
        record("1.b legion.seats >= 200", isinstance(legion_seats, int) and legion_seats >= 200,
               f"got {legion_seats}")

        teams_sum = sum((t.get("seats") or 0) for t in teams)
        record("1.c sum(teams[*].seats) >= 200", teams_sum >= 200,
               f"got {teams_sum} across {len(teams)} teams")

        tlen = len(transcript)
        record("1.d transcript length >= 900", tlen >= 900, f"got {tlen}")

        unique_codes = {entry.get("speaker_code") for entry in transcript if entry.get("speaker_code")}
        record("1.e unique speaker_code count == 482", len(unique_codes) == 482,
               f"got {len(unique_codes)}")

        whisper_count = data.get("whisper_count")
        record("1.f whisper_count >= 300",
               isinstance(whisper_count, int) and whisper_count >= 300,
               f"got {whisper_count}")

        ledger_written = data.get("ledger_entries_written")
        record("1.g ledger_entries_written >= 900",
               isinstance(ledger_written, int) and ledger_written >= 900,
               f"got {ledger_written}")

        census_total = full_swarm.get("census", {}).get("total_agents")
        record("1.h full_swarm.census.total_agents == 482", census_total == 482,
               f"got {census_total}")
except Exception as ex:
    record("1) legion simulate exception", False, str(ex))

# ── 2) Census regression ───────────────────────────────────────────────
print("\n" + "=" * 70)
print("2) GET /census")
print("=" * 70)
try:
    r = requests.get(f"{API}/census", timeout=30)
    if r.status_code != 200:
        record("2) census HTTP 200", False, f"status={r.status_code}")
    else:
        d = r.json()
        total_agents = d.get("total_agents")
        record("2.a total_agents >= 480", isinstance(total_agents, int) and total_agents >= 480,
               f"got {total_agents}")
        st = d.get("swarm_teams") or {}
        record("2.b swarm_teams has 20 keys", len(st) == 20, f"got {len(st)}")
        sl = d.get("swarm_legions") or {}
        record("2.c swarm_legions has 5 keys", len(sl) == 5, f"got {len(sl)}")
except Exception as ex:
    record("2) census exception", False, str(ex))

# ── 3) Teams regression ────────────────────────────────────────────────
print("\n" + "=" * 70)
print("3) GET /teams")
print("=" * 70)
try:
    r = requests.get(f"{API}/teams", timeout=30)
    if r.status_code != 200:
        record("3) teams HTTP 200", False, f"status={r.status_code}")
    else:
        d = r.json()
        tt = d.get("total_teams")
        record("3) total_teams == 20", tt == 20, f"got {tt}")
except Exception as ex:
    record("3) teams exception", False, str(ex))

# ── 4) Legions regression ──────────────────────────────────────────────
print("\n" + "=" * 70)
print("4) GET /legions")
print("=" * 70)
try:
    r = requests.get(f"{API}/legions", timeout=30)
    if r.status_code != 200:
        record("4) legions HTTP 200", False, f"status={r.status_code}")
    else:
        d = r.json()
        tl = d.get("total_legions")
        record("4) total_legions == 5", tl == 5, f"got {tl}")
except Exception as ex:
    record("4) legions exception", False, str(ex))

# ── 5) Platoons run regression ─────────────────────────────────────────
print("\n" + "=" * 70)
print("5) POST /platoons/run")
print("=" * 70)
body = {
    "build_id": "phase5_plat_001",
    "phase_id": "p_render",
    "game_ctx": {"genre": "rpg"},
}
try:
    r = requests.post(f"{API}/platoons/run", json=body, timeout=60)
    if r.status_code != 200:
        record("5) platoons/run HTTP 200", False, f"status={r.status_code}, body={r.text[:300]}")
    else:
        d = r.json()
        members = d.get("members") or []
        transcript = d.get("transcript") or []
        record("5.a platoon members == 5", len(members) == 5, f"got {len(members)}")
        record("5.b platoon transcript == 10 lines", len(transcript) == 10, f"got {len(transcript)}")
except Exception as ex:
    record("5) platoons/run exception", False, str(ex))

# ── 6) Overview regression ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("6) GET /overview")
print("=" * 70)
try:
    r = requests.get(f"{API}/overview", timeout=30)
    record("6) overview HTTP 200", r.status_code == 200, f"status={r.status_code}")
except Exception as ex:
    record("6) overview exception", False, str(ex))

# ── Summary ────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
passed = sum(1 for _, p, _ in results if p)
total = len(results)
print(f"Passed: {passed}/{total}")
for name, ok, detail in results:
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name} — {detail}")
