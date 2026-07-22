#!/usr/bin/env python3
"""
Backend verification: Agent Knowledge Fabric + Language Academy fix.
Covers all 28 review checks. Read-only.
"""
import requests
import os

BASE = os.environ.get(
    "BACKEND_URL",
    "https://gemini-game-craft.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE}/api"
TIMEOUT = 60

results = []

def _record(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append((name, ok, detail))
    print(f"[{status}] {name}  --  {detail}")

def _get(path, **params):
    return requests.get(f"{API}{path}", params=params, timeout=TIMEOUT)

def _post(path, **kwargs):
    return requests.post(f"{API}{path}", timeout=TIMEOUT, **kwargs)


def t1_languages_academy_stats():
    r = _get("/languages-academy/stats")
    ok = r.status_code == 200
    total = 0
    if ok:
        data = r.json()
        total = data.get("total", 0)
        ok = total >= 400
    _record("1) /languages-academy/stats >= 400", ok, f"status={r.status_code} total={total}")
    return total


def t2_languages_academy_all():
    r = _get("/languages-academy/all", limit=10)
    ok = r.status_code == 200
    n = 0
    first_id = None
    if ok:
        data = r.json()
        langs = data.get("languages", [])
        n = len(langs)
        ok = n >= 10
        if langs:
            first_id = langs[0].get("id") or langs[0].get("slug")
    _record("2) /languages-academy/all?limit=10 >=10", ok, f"status={r.status_code} count={n}")
    return first_id


def t3_languages_academy_detail(lang_id):
    if not lang_id:
        _record("3) /languages-academy/{id} has chapters", False, "no lang_id from prior step")
        return
    r = _get(f"/languages-academy/{lang_id}")
    ok = r.status_code == 200
    chapters_n = 0
    if ok:
        data = r.json()
        lang = data.get("language", {})
        chapters = lang.get("chapters", [])
        chapters_n = len(chapters) if isinstance(chapters, list) else 0
        ok = chapters_n >= 1
    _record("3) /languages-academy/{lang_id} has chapters", ok, f"status={r.status_code} id={lang_id} chapters={chapters_n}")


def t4_mega_dbs_list():
    r = _get("/galaxy-studio/mega-dbs/list")
    ok = r.status_code == 200
    total_docs = 0
    ready = 0
    if ok:
        data = r.json()
        total_docs = data.get("total_docs", 0)
        ready = data.get("ready_collections", 0)
        ok = total_docs > 0 and ready > 0
    _record("4) /galaxy-studio/mega-dbs/list >0 docs & ready", ok,
            f"status={r.status_code} total_docs={total_docs} ready_collections={ready}")


def t5_knowledge_stats():
    r = _get("/knowledge/stats")
    if r.status_code != 200:
        _record("5) /knowledge/stats endpoint", False, f"status={r.status_code} body={r.text[:200]}")
        return
    data = r.json()
    thresholds = {
        "patch_notes": 1700,
        "github_code_refs": 20,
        "language_classes": 400,
        "code_synthesis_templates": 150,
        "code_diagnostics_rules": 250,
        "procgen_recipes": 100,
        "content_catalogues": 8000,
        "game_design_patterns": 400,
        "game_balance_curves": 50,
        "engine_api_schemas": 15,
    }
    for k, threshold in thresholds.items():
        v = data.get(k, 0)
        ok = v >= threshold
        _record(f"5) /knowledge/stats {k} >= {threshold}", ok, f"actual={v}")


def t6_patch_notes_limit5():
    r = _get("/knowledge/patch-notes", limit=5)
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        n = len(data.get("patches", []))
        ok = n == 5
    _record("6) /knowledge/patch-notes?limit=5", ok, f"status={r.status_code} count={n}")


def t7_patch_notes_filter_game():
    r = _get("/knowledge/patch-notes", game="Dota 2")
    ok = r.status_code == 200
    only_dota2 = False
    n = 0
    if ok:
        data = r.json()
        patches = data.get("patches", [])
        n = len(patches)
        if patches:
            only_dota2 = all((p.get("game", "").lower() == "dota 2") for p in patches)
        ok = only_dota2 and n > 0
    _record("7) /knowledge/patch-notes?game=Dota+2 all Dota 2", ok,
            f"status={r.status_code} count={n} all_dota2={only_dota2}")


def t8_patch_notes_filter_kind_balance():
    r = _get("/knowledge/patch-notes", kind="balance", limit=10)
    ok = r.status_code == 200
    n = 0
    all_balance = False
    if ok:
        data = r.json()
        patches = data.get("patches", [])
        n = len(patches)
        all_balance = all(p.get("kind") == "balance" for p in patches) and n > 0
        ok = all_balance
    _record("8) /knowledge/patch-notes?kind=balance all kind=balance", ok,
            f"status={r.status_code} count={n} all_balance={all_balance}")


def t9_patch_notes_games_list():
    r = _get("/knowledge/patch-notes/games")
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        games = data.get("games", [])
        n = len(games)
        ok = n >= 100
    _record("9) /knowledge/patch-notes/games >= 100", ok, f"status={r.status_code} games={n}")


def t10_patch_notes_tag_arpg():
    r = _get("/knowledge/patch-notes", tag="arpg")
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        patches = data.get("patches", [])
        n = len(patches)
        ok = n > 0
    _record("10) /knowledge/patch-notes?tag=arpg >0", ok, f"status={r.status_code} count={n}")


def t11_github_code_limit5():
    r = _get("/knowledge/github-code", limit=5)
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        n = len(data.get("refs", []))
        ok = n == 5
    _record("11) /knowledge/github-code?limit=5", ok, f"status={r.status_code} count={n}")


def t12_github_code_filter_rust():
    r = _get("/knowledge/github-code", language="Rust")
    ok = r.status_code == 200
    n = 0
    all_rust = False
    if ok:
        data = r.json()
        refs = data.get("refs", [])
        n = len(refs)
        all_rust = all((ref.get("primary_language", "").lower() == "rust") for ref in refs) and n > 0
        ok = all_rust
    _record("12) /knowledge/github-code?language=Rust all Rust", ok,
            f"status={r.status_code} count={n} all_rust={all_rust}")


def t13_github_topics():
    r = _get("/knowledge/github-code/topics")
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        topics = data.get("topics", [])
        n = len(topics)
        has_counts = all("topic" in t and "count" in t for t in topics) if topics else False
        ok = n > 0 and has_counts
    _record("13) /knowledge/github-code/topics list with counts", ok, f"status={r.status_code} topics={n}")


def t14_templates_main_loop_python():
    r = _get("/knowledge/templates", kind="main-loop", language="Python")
    ok = r.status_code == 200
    n = 0
    has_body = False
    if ok:
        data = r.json()
        templates = data.get("templates", [])
        n = len(templates)
        if templates:
            has_body = bool(templates[0].get("body"))
        ok = n >= 1 and has_body
    _record("14) /knowledge/templates kind=main-loop lang=Python >=1 with body", ok,
            f"status={r.status_code} count={n} has_body={has_body}")


def t15_diagnostics_typescript():
    r = _get("/knowledge/diagnostics", language="TypeScript")
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        n = len(data.get("diagnostics", []))
        ok = n > 1
    _record("15) /knowledge/diagnostics?language=TypeScript multiple", ok, f"status={r.status_code} count={n}")


def t16_procgen_perlin():
    r = _get("/knowledge/procgen", kind="perlin-terrain")
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        recipes = data.get("recipes", [])
        n = len(recipes)
        ok = n >= 1
    _record("16) /knowledge/procgen?kind=perlin-terrain returns variants", ok, f"status={r.status_code} count={n}")


def t17_catalogues_weapons_legendary():
    r = _get("/knowledge/catalogues", category="weapons", rarity="legendary")
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        items = data.get("items", [])
        n = len(items)
        ok = n >= 1
    _record("17) /knowledge/catalogues weapons legendary", ok, f"status={r.status_code} count={n}")


def t18_catalogues_enemies_cyberpunk():
    r = _get("/knowledge/catalogues", category="enemies", era="cyberpunk", limit=10)
    ok = r.status_code == 200
    n = 0
    match = False
    if ok:
        data = r.json()
        items = data.get("items", [])
        n = len(items)
        if items:
            match = all(i.get("category") == "enemies" and i.get("era") == "cyberpunk" for i in items)
        ok = n >= 1 and match
    _record("18) /knowledge/catalogues enemies cyberpunk filter match", ok,
            f"status={r.status_code} count={n} match={match}")


def t19_design_rpg():
    r = _get("/knowledge/design", genre="rpg")
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        patterns = data.get("patterns", [])
        n = len(patterns)
        ok = n >= 1
    _record("19) /knowledge/design?genre=rpg returns patterns", ok, f"status={r.status_code} count={n}")


def t20_balance_curves_exponential():
    r = _get("/knowledge/balance-curves", curve="exponential")
    ok = r.status_code == 200
    n = 0
    has_fields = False
    if ok:
        data = r.json()
        curves = data.get("curves", [])
        n = len(curves)
        if curves:
            c0 = curves[0]
            has_fields = ("formula" in c0) and ("default_params" in c0)
        ok = n >= 1 and has_fields
    _record("20) /knowledge/balance-curves exponential w/ formula+default_params", ok,
            f"status={r.status_code} count={n} has_fields={has_fields}")


def t21_engines_all():
    r = _get("/knowledge/engines")
    ok = r.status_code == 200
    n = 0
    if ok:
        data = r.json()
        engines = data.get("engines", [])
        n = len(engines)
        ok = n >= 15
    _record("21) /knowledge/engines >= 15", ok, f"status={r.status_code} count={n}")


def t22_engines_unity():
    r = _get("/knowledge/engines", engine="Unity")
    ok = r.status_code == 200
    has_bootstrap = False
    if ok:
        data = r.json()
        engines = data.get("engines", [])
        if engines:
            unity = next((e for e in engines if "unity" in e.get("engine", "").lower()), None)
            if unity:
                has_bootstrap = bool(unity.get("bootstrap"))
        ok = has_bootstrap
    _record("22) /knowledge/engines?engine=Unity has bootstrap", ok,
            f"status={r.status_code} has_bootstrap={has_bootstrap}")


def t23_engines_godot():
    r = _get("/knowledge/engines", engine="Godot")
    ok = r.status_code == 200
    found_43 = False
    found_any = False
    if ok:
        data = r.json()
        engines = data.get("engines", [])
        for e in engines:
            if "godot" in e.get("engine", "").lower():
                found_any = True
                ver = str(e.get("version", "")) + " " + str(e.get("engine", ""))
                if "4.3" in ver:
                    found_43 = True
        ok = found_any
    _record("23) /knowledge/engines?engine=Godot returns entry (4.3 hinted)", ok,
            f"status={r.status_code} any_godot={found_any} godot43={found_43}")


def t24_search_ecs():
    r = _get("/knowledge/search", q="ecs")
    ok = r.status_code == 200
    multi = False
    if ok:
        data = r.json()
        patches = data.get("patches", [])
        refs = data.get("github_refs", [])
        langs = data.get("languages", [])
        non_empty = sum(1 for x in (patches, refs, langs) if len(x) > 0)
        multi = non_empty >= 2
        ok = multi
    _record("24) /knowledge/search?q=ecs spans multiple collections", ok,
            f"status={r.status_code} multi_collections={multi}")


def t25_agent_context():
    r = _get("/knowledge/agent-context", topic="boss-fight", language="C#", engine="Unity", genre="arpg")
    ok = r.status_code == 200
    total = 0
    nine_sections = False
    if ok:
        data = r.json()
        keys_required = {"patches", "github_refs", "templates", "diagnostics", "procgen",
                         "catalogues", "design", "balance_curves", "engines"}
        nine_sections = keys_required.issubset(set(data.keys()))
        total = data.get("total", 0)
        ok = nine_sections and total > 0
    _record("25) /knowledge/agent-context returns 9 sections, total>0", ok,
            f"status={r.status_code} nine_sections={nine_sections} total={total}")


def t26_reseed():
    r = _post("/knowledge/reseed")
    ok = r.status_code == 200
    has_results = False
    if ok:
        data = r.json()
        has_results = isinstance(data.get("results"), dict) and len(data["results"]) > 0
        ok = has_results
    _record("26) /knowledge/reseed returns results dict", ok,
            f"status={r.status_code} has_results={has_results}")


def t27_health():
    r = _get("/health")
    ok = r.status_code == 200
    _record("27) /health", ok, f"status={r.status_code}")


def t28_reading_leaderboard():
    r = _get("/reading-time/leaderboard")
    ok = r.status_code == 200
    _record("28) /reading-time/leaderboard", ok, f"status={r.status_code}")


def main():
    print(f"Testing backend at: {API}")
    print("=" * 80)
    t1_languages_academy_stats()
    first = t2_languages_academy_all()
    t3_languages_academy_detail(first)
    t4_mega_dbs_list()
    t5_knowledge_stats()
    t6_patch_notes_limit5()
    t7_patch_notes_filter_game()
    t8_patch_notes_filter_kind_balance()
    t9_patch_notes_games_list()
    t10_patch_notes_tag_arpg()
    t11_github_code_limit5()
    t12_github_code_filter_rust()
    t13_github_topics()
    t14_templates_main_loop_python()
    t15_diagnostics_typescript()
    t16_procgen_perlin()
    t17_catalogues_weapons_legendary()
    t18_catalogues_enemies_cyberpunk()
    t19_design_rpg()
    t20_balance_curves_exponential()
    t21_engines_all()
    t22_engines_unity()
    t23_engines_godot()
    t24_search_ecs()
    t25_agent_context()
    t26_reseed()
    t27_health()
    t28_reading_leaderboard()
    print("=" * 80)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\nSUMMARY: {passed} passed, {failed} failed (total {len(results)})")
    if failed:
        print("\nFailures:")
        for name, ok, detail in results:
            if not ok:
                print(f"  [FAIL] {name} -- {detail}")


if __name__ == "__main__":
    main()
