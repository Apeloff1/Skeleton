"""
Wave 2 backend regression: 6 new matrices + Advanced ML config endpoints.
Per review request, base URL is http://localhost:8001 (append /api/...).
"""
import json
import sys
import requests

BASE = "http://localhost:8001/api"
TIMEOUT = 30

results = []
def log(name, ok, info=""):
    sym = "✅" if ok else "❌"
    print(f"{sym} {name} :: {info}")
    results.append((name, ok, info))

# ──────────────────────────────────────────────────────────────────────────
# Test 1 — POST /api/galaxy-studio/create with all 6 new matrices + agent_matrix
# ──────────────────────────────────────────────────────────────────────────
payload = {
    "title": "Matrix Verify RPG",
    "genre": "rpg",
    "complexity": 8,
    "vector_db_matrix": {
        "pinecone": {"priority": 9, "scale": 8, "consistency": 7, "latency": 8, "cost": 5},
        "weaviate": {"priority": 8},
        "hnsw":     {"priority": 9},
    },
    "plagiarism_matrix": {
        "moss":     {"sensitivity": 9, "specificity": 8, "recall": 8, "audit_trail": 9, "autofix": 6},
        "codeBERT": {"sensitivity": 8},
    },
    "rdbms_matrix": {
        "postgres": {"priority": 10, "scale": 9, "consistency": 10, "latency": 8, "cost": 4},
        "sharding": {"priority": 7},
    },
    "styles_matrix": {
        "graphic_style":   {"depth": 8, "fidelity": 9},
        "cinematic_style": {"depth": 9},
    },
    "mutation_matrix": {
        "world_drift":   {"rate": 6, "magnitude": 5},
        "boss_mutation": {"rate": 7},
    },
    "unique_flair_matrix": {
        "signature_move": {"rarity": 8, "showmanship": 9},
        "secret_room":    {"rarity": 9},
    },
    "agent_matrix": {
        "loss_ce":              {"weight": 8, "temperature": 6, "samples": 8, "context_depth": 7, "self_consistency": 5},
        "loss_label_smooth":    {"weight": 4},
        "loss_focal":           {"weight": 6},
        "pref_dpo":             {"weight": 7},
        "pref_kto":             {"weight": 5},
        "lora_r":               {"weight": 6},
        "qlora_4bit":           {"weight": 8},
        "icl_logprobs":         {"weight": 9, "samples": 16, "context_depth": 8},
        "icl_self_consistency": {"samples": 12},
        "icl_mcts":             {"context_depth": 6},
    },
}

build_id = None
try:
    r = requests.post(f"{BASE}/galaxy-studio/create", json=payload, timeout=TIMEOUT)
    if r.status_code == 200:
        data = r.json()
        build_id = data.get("build_id")
        log("T1 POST /galaxy-studio/create with 6 matrices+agent_matrix", bool(build_id),
            f"status=200 build_id={build_id}")
    else:
        log("T1 POST /galaxy-studio/create with 6 matrices+agent_matrix", False,
            f"status={r.status_code} body={r.text[:300]}")
except Exception as e:
    log("T1 POST /galaxy-studio/create with 6 matrices+agent_matrix", False, f"exception: {e}")

# ──────────────────────────────────────────────────────────────────────────
# Test 2 — GET /api/galaxy-studio/build/{build_id}/ml-config
# ──────────────────────────────────────────────────────────────────────────
if build_id:
    try:
        r = requests.get(f"{BASE}/galaxy-studio/build/{build_id}/ml-config", timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            ml = d.get("ml_config", {}) or {}
            ce = d.get("cross_entropy_dials", {}) or {}
            ft = d.get("fine_tuning_dials", {}) or {}
            icl = d.get("in_context_dials", {}) or {}
            mdc = d.get("matrix_dial_count", 0)
            mks = d.get("matrix_keys", []) or []

            expected_ml = {
                "ce_loss_weight": 8,
                "ce_temperature": 0.6,
                "label_smoothing": 0.04,
                "focal_gamma": 1.5,
                "preference_finetune": ["DPO", "KTO"],
                "lora_r": 32,
                "qlora_4bit": True,
                "icl_logprobs_depth": 8,
                "icl_samples": 16,
                "self_consistency_k": 12,
                "mcts_depth": 6,
            }
            failures = []
            for k, v in expected_ml.items():
                if ml.get(k) != v:
                    failures.append(f"{k}: expected {v!r} got {ml.get(k)!r}")
            log("T2.ml_config values match expected derived values",
                len(failures) == 0,
                ("OK" if not failures else "; ".join(failures))[:400])

            log("T2.cross_entropy_dials contains loss_ce, loss_label_smooth, loss_focal",
                all(k in ce for k in ("loss_ce", "loss_label_smooth", "loss_focal")),
                f"keys={list(ce.keys())}")
            log("T2.fine_tuning_dials contains pref_dpo, pref_kto, lora_r, qlora_4bit",
                all(k in ft for k in ("pref_dpo", "pref_kto", "lora_r", "qlora_4bit")),
                f"keys={list(ft.keys())}")
            log("T2.in_context_dials contains icl_logprobs, icl_self_consistency, icl_mcts",
                all(k in icl for k in ("icl_logprobs", "icl_self_consistency", "icl_mcts")),
                f"keys={list(icl.keys())}")
            log("T2.matrix_dial_count >= 20",
                isinstance(mdc, (int, float)) and mdc >= 20,
                f"matrix_dial_count={mdc}")
            required_mks = {"agent_matrix", "vector_db_matrix", "plagiarism_matrix",
                            "rdbms_matrix", "styles_matrix", "mutation_matrix", "unique_flair_matrix"}
            missing = required_mks - set(mks)
            log("T2.matrix_keys includes agent_matrix + 6 new matrices",
                not missing,
                f"matrix_keys={mks} missing={list(missing)}")
        else:
            log("T2 GET /build/{id}/ml-config", False, f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        log("T2 GET /build/{id}/ml-config", False, f"exception: {e}")
else:
    log("T2 GET ml-config", False, "skipped — no build_id")

# ──────────────────────────────────────────────────────────────────────────
# Test 3 — POST /api/galaxy-studio/build/{build_id}/ml-config (runtime patch)
# ──────────────────────────────────────────────────────────────────────────
if build_id:
    patch = {"ce_loss_weight": 10, "label_smoothing": 0.1, "loss_type": "focal", "BAD_KEY": 999}
    try:
        r = requests.post(f"{BASE}/galaxy-studio/build/{build_id}/ml-config", json=patch, timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            upd = d.get("updated", {}) or {}
            ml  = d.get("ml_config", {}) or {}
            expected_updated = {"ce_loss_weight": 10, "label_smoothing": 0.1, "loss_type": "focal"}
            bad_dropped = "BAD_KEY" not in upd
            updated_match = upd == expected_updated
            log("T3.updated dict exactly == {ce_loss_weight, label_smoothing, loss_type} (BAD_KEY dropped)",
                updated_match and bad_dropped,
                f"updated={upd}")
            # Verify ml_config merged: should still contain prior derived ce_temperature=0.6 + patched values
            log("T3.ml_config retains derived ce_temperature after patch",
                ml.get("ce_temperature") == 0.6,
                f"ce_temperature={ml.get('ce_temperature')}")
            log("T3.ml_config reflects patched ce_loss_weight=10",
                ml.get("ce_loss_weight") == 10,
                f"ce_loss_weight={ml.get('ce_loss_weight')}")
            log("T3.ml_config reflects patched label_smoothing=0.1",
                ml.get("label_smoothing") == 0.1,
                f"label_smoothing={ml.get('label_smoothing')}")
            log("T3.ml_config reflects patched loss_type='focal'",
                ml.get("loss_type") == "focal",
                f"loss_type={ml.get('loss_type')}")
        else:
            log("T3 POST /build/{id}/ml-config patch", False,
                f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        log("T3 POST /build/{id}/ml-config patch", False, f"exception: {e}")
else:
    log("T3 POST ml-config patch", False, "skipped — no build_id")

# ──────────────────────────────────────────────────────────────────────────
# Test 4 — Phase 4 endpoints still healthy
# ──────────────────────────────────────────────────────────────────────────
try:
    r = requests.get(f"{BASE}/health", timeout=TIMEOUT)
    ok = r.status_code == 200 and r.json().get("status") == "healthy"
    log("T4.1 /api/health == healthy", ok, f"status={r.status_code}")
except Exception as e:
    log("T4.1 /api/health", False, f"exception: {e}")

try:
    r = requests.get(f"{BASE}/knowledge/agent-context",
                     params={"topic": "stylometric", "language": "Python"},
                     timeout=TIMEOUT)
    if r.status_code == 200:
        d = r.json()
        required = {"code_similarity", "asset_theft", "ast_detection", "stylometric",
                    "legal_precedents", "academic", "agnostic_content", "training_recipes",
                    "logic_clones", "linting"}
        missing = required - set(d.keys())
        log("T4.2 /knowledge/agent-context has 10 phase4 keys", not missing,
            f"missing={list(missing)}" if missing else "all present")
    else:
        log("T4.2 /knowledge/agent-context", False, f"status={r.status_code}")
except Exception as e:
    log("T4.2 /knowledge/agent-context", False, f"exception: {e}")

try:
    r = requests.get(f"{BASE}/knowledge/scrapers", timeout=TIMEOUT)
    if r.status_code == 200:
        d = r.json()
        total = d.get("total")
        log("T4.3 /knowledge/scrapers total==12", total == 12, f"total={total}")
    else:
        log("T4.3 /knowledge/scrapers", False, f"status={r.status_code}")
except Exception as e:
    log("T4.3 /knowledge/scrapers", False, f"exception: {e}")

try:
    r = requests.get(f"{BASE}/knowledge/training/recipes", params={"kind": "in-context"}, timeout=TIMEOUT)
    if r.status_code == 200:
        total = r.json().get("total")
        log("T4.4 /knowledge/training/recipes?kind=in-context total==3",
            total == 3, f"total={total}")
    else:
        log("T4.4 /knowledge/training/recipes?kind=in-context", False, f"status={r.status_code}")
except Exception as e:
    log("T4.4 /knowledge/training/recipes?kind=in-context", False, f"exception: {e}")

try:
    r = requests.get(f"{BASE}/knowledge/stats", timeout=TIMEOUT)
    if r.status_code == 200:
        d = r.json()
        tr  = d.get("training_recipes", 0)
        sj  = d.get("scraper_jobs", 0)
        sf  = d.get("stylometric_fingerprint", 0)
        ok = tr >= 18 and sj >= 12 and sf >= 250
        log("T4.5 /knowledge/stats Phase 4 thresholds (TR>=18, scrapers>=12, stylo>=250)",
            ok, f"training_recipes={tr} scraper_jobs={sj} stylometric_fingerprint={sf}")
    else:
        log("T4.5 /knowledge/stats", False, f"status={r.status_code}")
except Exception as e:
    log("T4.5 /knowledge/stats", False, f"exception: {e}")

# ──────────────────────────────────────────────────────────────────────────
# Test 5 — Galaxy Studio core endpoints unaffected
# ──────────────────────────────────────────────────────────────────────────
try:
    r = requests.post(f"{BASE}/galaxy-studio/create",
                      json={"title": "Plain Build", "genre": "rpg", "complexity": 5},
                      timeout=TIMEOUT)
    log("T5.1 /galaxy-studio/create (no matrices)",
        r.status_code == 200 and r.json().get("build_id"),
        f"status={r.status_code}")
except Exception as e:
    log("T5.1 /galaxy-studio/create no matrices", False, f"exception: {e}")

try:
    r = requests.get(f"{BASE}/galaxy-studio/manifest", timeout=TIMEOUT)
    log("T5.2 /galaxy-studio/manifest", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    log("T5.2 /galaxy-studio/manifest", False, f"exception: {e}")

try:
    r = requests.get(f"{BASE}/galaxy-studio/genres", timeout=TIMEOUT)
    log("T5.3 /galaxy-studio/genres", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    log("T5.3 /galaxy-studio/genres", False, f"exception: {e}")

try:
    r = requests.get(f"{BASE}/galaxy-studio/mega-dbs/list", timeout=TIMEOUT)
    if r.status_code == 200:
        d = r.json()
        rc = d.get("ready_collections")
        td = d.get("total_docs")
        ok = rc == 200 and td == 600000
        log("T5.4 /galaxy-studio/mega-dbs/list ready=200 total=600000",
            ok, f"ready_collections={rc} total_docs={td}")
    else:
        log("T5.4 /galaxy-studio/mega-dbs/list", False, f"status={r.status_code}")
except Exception as e:
    log("T5.4 /galaxy-studio/mega-dbs/list", False, f"exception: {e}")

# ──────────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
print(f"\n{'='*70}\nWAVE 2 BACKEND REGRESSION SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFAILURES:")
    for n, ok, info in results:
        if not ok:
            print(f"  ❌ {n}\n     {info}")
sys.exit(0 if passed == total else 1)
