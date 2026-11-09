"""
Backend tests for:
  TEST 1 — Galaxy Studio era_year type tolerance (int + str)
  TEST 2 — Reading Content endpoints (/api/academy/reading-library/book/{id}/chapter/{idx}/content,
           class-progress CRUD, continue, prewarm)

Run: python /app/backend_test_era_reading.py
"""
import requests
import json
import time
import sys

BASE = "http://localhost:8001"


def _log(ok, label, detail=""):
    tag = "PASS" if ok else "FAIL"
    marker = "✅" if ok else "❌"
    print(f"{marker} [{tag}] {label}" + (f"  :: {detail}" if detail else ""))


def section(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


results = {"test1": [], "test2": []}


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1 — Galaxy Studio era_year type tolerance
# ═══════════════════════════════════════════════════════════════════════════
section("TEST 1 — Galaxy Studio build-revert bug fix (era_year number+string)")


def _galaxy_create(era_year_value, label):
    payload = {
        "title": f"E2E Verify {label}",
        "genre": "rpg",
        "subgenre": "action_rpg",
        "description": "test",
        "era_id": "modern",
        "era_label": "Modern",
        "era_year": era_year_value,
        "age_era_year": 2026,
        "locomotion_depth": 5,
        "locomotion_style": "als",
    }
    r = requests.post(f"{BASE}/api/galaxy-studio/create", json=payload, timeout=45)
    ok = r.status_code == 200
    build_id = None
    total_agents = None
    detail = f"HTTP {r.status_code}"
    if ok:
        j = r.json()
        build_id = j.get("build_id")
        total_agents = j.get("total_agents")
        detail += f", build_id={build_id}, total_agents={total_agents}"
    else:
        detail += f", body={r.text[:300]}"
    _log(ok and build_id and (total_agents is not None),
         f"POST /api/galaxy-studio/create era_year={label}", detail)
    results["test1"].append((f"create era_year={label}", ok, detail))
    return build_id


bid_int = _galaxy_create(2026, "int(2026)")
bid_str = _galaxy_create("2026", "str('2026')")

# start-build on the int-version build
if bid_int:
    r = requests.post(
        f"{BASE}/api/galaxy-studio/start-build",
        json={"build_id": bid_int, "build_duration_minutes": 15, "phase_weights": {}},
        timeout=30,
    )
    ok = r.status_code == 200
    detail = f"HTTP {r.status_code}, body={r.text[:250]}"
    _log(ok, f"POST /api/galaxy-studio/start-build build_id={bid_int}", detail)
    results["test1"].append(("start-build int-build", ok, detail))
else:
    results["test1"].append(("start-build int-build", False, "skipped: create failed"))


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2 — Reading Content endpoints
# ═══════════════════════════════════════════════════════════════════════════
section("TEST 2 — Reading Content endpoints")

# A) GET /api/academy/reading-library
r = requests.get(f"{BASE}/api/academy/reading-library", timeout=30)
ok_a = r.status_code == 200
books = []
detail = f"HTTP {r.status_code}"
if ok_a:
    j = r.json()
    # Try common shape: {"books": [...]} or list
    if isinstance(j, dict):
        books = j.get("books") or j.get("items") or j.get("data") or []
    elif isinstance(j, list):
        books = j
    detail += f", total_books={len(books)}"
    ok_a = ok_a and len(books) >= 300
else:
    detail += f", body={r.text[:200]}"
_log(ok_a, "A) GET /api/academy/reading-library (>=300 books)", detail)
results["test2"].append(("A reading-library list", ok_a, detail))

if not books:
    print("No books returned; aborting reading tests.")
    sys.exit(1)

first_book = books[0]
book_id = first_book.get("id") or first_book.get("book_id")
expected_title = first_book.get("title")
print(f"   Using book_id={book_id}, title={expected_title}")

required_section_titles = [
    "Orientation", "Core Concepts", "Worked Example", "Deeper Reading",
    "Common Pitfalls", "Exercises", "Looking Ahead"
]


def _check_chapter_payload(j, expected_idx):
    issues = []
    for key in ["book_title", "author", "chapter_idx", "total_chapters", "chapter_name", "content"]:
        if key not in j:
            issues.append(f"missing '{key}'")
    if j.get("chapter_idx") != expected_idx:
        issues.append(f"chapter_idx={j.get('chapter_idx')} != {expected_idx}")
    if (j.get("total_chapters") or 0) <= 0:
        issues.append("total_chapters <=0")
    content = j.get("content") or {}
    body_md = content.get("body_md") or ""
    if not isinstance(body_md, str):
        issues.append("body_md not str")
    if len(body_md) < 1500:
        issues.append(f"body_md_len={len(body_md)} < 1500")
    wc = content.get("word_count") or 0
    if wc < 400:
        issues.append(f"word_count={wc} < 400")
    sections = content.get("sections") or []
    if not isinstance(sections, list):
        issues.append("sections not list")
    elif len(sections) != 7:
        issues.append(f"sections_len={len(sections)} != 7")
    else:
        titles = [s.get("title") for s in sections]
        if titles != required_section_titles:
            issues.append(f"sections titles={titles} (expected {required_section_titles})")
    return (len(issues) == 0, issues, body_md, content)


# B) First call → cached:false
r = requests.get(
    f"{BASE}/api/academy/reading-library/book/{book_id}/chapter/0/content",
    timeout=45,
)
ok_b = r.status_code == 200
detail_b = f"HTTP {r.status_code}"
body_md_1 = ""
if ok_b:
    j = r.json()
    passed, issues, body_md_1, content_1 = _check_chapter_payload(j, 0)
    cached_first = j.get("cached")
    detail_b += (
        f", book_title={j.get('book_title')}, total_chapters={j.get('total_chapters')}, "
        f"body_md_len={len(body_md_1)}, word_count={content_1.get('word_count')}, "
        f"sections={len(content_1.get('sections') or [])}, cached={cached_first}"
    )
    if issues:
        detail_b += f", ISSUES={issues}"
    ok_b = passed
    # cached=false expected (but may already be True if tests ran before; note it)
else:
    detail_b += f", body={r.text[:300]}"
_log(ok_b, "B) GET chapter/0/content (first call, schema check)", detail_b)
results["test2"].append(("B chapter/0 first", ok_b, detail_b))

# C) Second call → cached:true + identical body_md
r2 = requests.get(
    f"{BASE}/api/academy/reading-library/book/{book_id}/chapter/0/content",
    timeout=30,
)
ok_c = r2.status_code == 200
detail_c = f"HTTP {r2.status_code}"
if ok_c:
    j2 = r2.json()
    body_md_2 = (j2.get("content") or {}).get("body_md") or ""
    cached_second = j2.get("cached")
    identical = body_md_1 == body_md_2
    detail_c += f", cached={cached_second}, identical_body_md={identical}, len={len(body_md_2)}"
    ok_c = (cached_second is True) and identical
else:
    detail_c += f", body={r2.text[:300]}"
_log(ok_c, "C) GET chapter/0/content (second call, cached=true + deterministic)", detail_c)
results["test2"].append(("C chapter/0 cached", ok_c, detail_c))

# D) Chapter 1
total_chapters = (r.json().get("total_chapters") if ok_b else 0) if r.status_code == 200 else 0
ok_d = False
detail_d = ""
if total_chapters >= 2:
    r3 = requests.get(
        f"{BASE}/api/academy/reading-library/book/{book_id}/chapter/1/content",
        timeout=45,
    )
    ok_d = r3.status_code == 200
    detail_d = f"HTTP {r3.status_code}"
    if ok_d:
        j3 = r3.json()
        passed, issues, _, content_3 = _check_chapter_payload(j3, 1)
        ch0_name = (r.json().get("chapter_name") if ok_b else None) if r.status_code == 200 else None
        ch1_name = j3.get("chapter_name")
        differs = (ch0_name is None) or (ch0_name != ch1_name)
        detail_d += f", chapter_name={ch1_name}, differs_from_ch0={differs}"
        if issues:
            detail_d += f", ISSUES={issues}"
        ok_d = passed and differs
    else:
        detail_d += f", body={r3.text[:300]}"
else:
    ok_d = True
    detail_d = f"only {total_chapters} chapters; skipping"
_log(ok_d, "D) GET chapter/1/content (different chapter_name)", detail_d)
results["test2"].append(("D chapter/1", ok_d, detail_d))

# E) POST class-progress/update
user_id = "test_user_e2e"
r4 = requests.post(
    f"{BASE}/api/academy/class-progress/update",
    json={
        "user_id": user_id,
        "item_type": "book",
        "item_id": book_id,
        "chapter_idx": 0,
        "scroll_ratio": 0.5,
    },
    timeout=30,
)
ok_e = r4.status_code == 200
detail_e = f"HTTP {r4.status_code}"
if ok_e:
    j4 = r4.json()
    ok_flag = j4.get("ok") is True
    prog = j4.get("progress") or {}
    sr = prog.get("scroll_ratio")
    detail_e += f", ok={ok_flag}, scroll_ratio={sr}"
    ok_e = ok_flag and (abs((sr or 0) - 0.5) < 1e-6)
else:
    detail_e += f", body={r4.text[:300]}"
_log(ok_e, "E) POST /api/academy/class-progress/update", detail_e)
results["test2"].append(("E class-progress update", ok_e, detail_e))

# F) GET class-progress/{user_id}
r5 = requests.get(f"{BASE}/api/academy/class-progress/{user_id}", timeout=30)
ok_f = r5.status_code == 200
detail_f = f"HTTP {r5.status_code}"
if ok_f:
    j5 = r5.json()
    count = j5.get("count") or 0
    items = j5.get("items") or []
    first_item = items[0] if items else {}
    detail_f += f", count={count}, items[0].item_id={first_item.get('item_id')}"
    ok_f = (count >= 1) and (first_item.get("item_id") == book_id)
else:
    detail_f += f", body={r5.text[:300]}"
_log(ok_f, "F) GET /api/academy/class-progress/{user_id}", detail_f)
results["test2"].append(("F class-progress list", ok_f, detail_f))

# G) GET class-progress/{user_id}/continue
r6 = requests.get(f"{BASE}/api/academy/class-progress/{user_id}/continue", timeout=30)
ok_g = r6.status_code == 200
detail_g = f"HTTP {r6.status_code}"
if ok_g:
    j6 = r6.json()
    cont = j6.get("continue")
    meta = j6.get("meta") or {}
    meta_title = meta.get("title")
    detail_g += (
        f", continue.item_id={cont.get('item_id') if cont else None}, "
        f"meta.title={meta_title}, expected={expected_title}"
    )
    ok_g = (cont is not None) and (meta_title == expected_title)
else:
    detail_g += f", body={r6.text[:300]}"
_log(ok_g, "G) GET /api/academy/class-progress/{user_id}/continue", detail_g)
results["test2"].append(("G continue", ok_g, detail_g))

# H) POST prewarm
r7 = requests.post(
    f"{BASE}/api/academy/reading-library/book/{book_id}/prewarm",
    timeout=120,
)
ok_h = r7.status_code == 200
detail_h = f"HTTP {r7.status_code}"
if ok_h:
    j7 = r7.json()
    ok_flag = j7.get("ok") is True
    generated = j7.get("generated")
    total_ch = j7.get("chapters")
    detail_h += f", ok={ok_flag}, chapters={total_ch}, generated={generated}"
    ok_h = ok_flag and (generated is not None) and (generated >= 0)
else:
    detail_h += f", body={r7.text[:300]}"
_log(ok_h, "H) POST /api/academy/reading-library/book/{book_id}/prewarm", detail_h)
results["test2"].append(("H prewarm", ok_h, detail_h))


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
section("SUMMARY")
total = 0
passed = 0
for group, cases in results.items():
    print(f"\n--- {group} ---")
    for name, ok, det in cases:
        total += 1
        if ok:
            passed += 1
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] {name}  :: {det}")
print(f"\nTotal: {passed}/{total} passed")
sys.exit(0 if passed == total else 1)
