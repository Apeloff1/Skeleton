"""Quick verification of new Academy endpoints + Galaxy Studio regression.
Runs against http://localhost:8001 per review request."""
from __future__ import annotations
import json
import sys
import requests

BASE = "http://localhost:8001"
results = []


def record(name: str, ok: bool, detail: str):
    status = "PASS" if ok else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}: {detail}")


def main() -> int:
    # --- Test 5 first: idempotent import (so books exist in DB before tests 1, 2, 6) ---
    try:
        r = requests.post(f"{BASE}/api/academy/reading-library/import-open-license", timeout=60)
        ok = r.status_code == 200
        data = r.json() if ok else {}
        total = data.get("total")
        updated = data.get("updated")
        inserted = data.get("inserted")
        record(
            "T5 POST /api/academy/reading-library/import-open-license (run 1)",
            ok and total == 23,
            f"HTTP {r.status_code} total={total} inserted={inserted} updated={updated}",
        )
        # Run again to test idempotency
        r2 = requests.post(f"{BASE}/api/academy/reading-library/import-open-license", timeout=60)
        ok2 = r2.status_code == 200
        data2 = r2.json() if ok2 else {}
        record(
            "T5b POST /reading-library/import-open-license (idempotent run 2: updated=23)",
            ok2 and data2.get("total") == 23 and data2.get("updated") == 23,
            f"HTTP {r2.status_code} total={data2.get('total')} updated={data2.get('updated')} inserted={data2.get('inserted')}",
        )
    except Exception as e:
        record("T5 POST import-open-license", False, f"EXC {e}")

    # --- Test 1: Pro Git book chapter 0 ---
    try:
        r = requests.get(
            f"{BASE}/api/academy/reading-library/book/open_pro_git/chapter/0/content", timeout=60
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        cond = (
            ok
            and data.get("is_open_license") is True
            and data.get("license") == "CC BY 3.0"
            and data.get("official_url") == "https://git-scm.com/book"
            and data.get("total_chapters") == 12
            and (data.get("content", {}).get("word_count", 0) > 1000)
        )
        record(
            "T1 GET reading-library/book/open_pro_git/chapter/0/content",
            cond,
            (
                f"HTTP {r.status_code} is_open={data.get('is_open_license')} "
                f"license={data.get('license')!r} url={data.get('official_url')!r} "
                f"total_chapters={data.get('total_chapters')} "
                f"word_count={data.get('content', {}).get('word_count')}"
            ),
        )
    except Exception as e:
        record("T1 pro_git chapter 0", False, f"EXC {e}")

    # --- Test 2: The Rust Programming Language chapter 3 ---
    try:
        r = requests.get(
            f"{BASE}/api/academy/reading-library/book/open_the_rust_programming_language/chapter/3/content",
            timeout=60,
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        license_str = str(data.get("license") or "")
        url_str = str(data.get("official_url") or "")
        cond = (
            ok
            and data.get("is_open_license") is True
            and "MIT" in license_str
            and "rust-lang.org" in url_str
        )
        record(
            "T2 GET reading-library/book/open_the_rust_programming_language/chapter/3/content",
            cond,
            (
                f"HTTP {r.status_code} is_open={data.get('is_open_license')} "
                f"license={license_str!r} url={url_str!r}"
            ),
        )
    except Exception as e:
        record("T2 rust book chapter 3", False, f"EXC {e}")

    # --- Test 3: Subject sub_rosetta_variables chapter 0 ---
    try:
        r = requests.get(
            f"{BASE}/api/academy/subject/sub_rosetta_variables/chapter/0/content", timeout=60
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        wc = data.get("content", {}).get("word_count", 0)
        sections = data.get("content", {}).get("sections") or []
        cond = ok and wc >= 2000 and len(sections) == 15
        record(
            "T3 GET subject/sub_rosetta_variables/chapter/0/content",
            cond,
            f"HTTP {r.status_code} word_count={wc} sections={len(sections)}",
        )
    except Exception as e:
        record("T3 sub_rosetta_variables chapter 0", False, f"EXC {e}")

    # --- Test 4: Tracks dedupe ---
    try:
        r = requests.post(f"{BASE}/api/academy/tracks/dedupe", timeout=30)
        ok = r.status_code == 200
        data = r.json() if ok else {}
        rd = data.get("removed_duplicates")
        cond = ok and data.get("ok") is True and isinstance(rd, int) and rd >= 0
        record(
            "T4 POST academy/tracks/dedupe",
            cond,
            f"HTTP {r.status_code} ok={data.get('ok')} removed_duplicates={rd} unique={data.get('unique_track_ids')}",
        )
    except Exception as e:
        record("T4 tracks/dedupe", False, f"EXC {e}")

    # --- Test 6: Auto-quiz (book_8f2c53efc1, chapter 0) ---
    # First make sure chapter is generated/cached
    try:
        requests.get(
            f"{BASE}/api/academy/reading-library/book/book_8f2c53efc1/chapter/0/content", timeout=60
        )
    except Exception:
        pass

    try:
        r = requests.post(
            f"{BASE}/api/academy/reading-library/quiz",
            json={"item_type": "book", "item_id": "book_8f2c53efc1", "chapter_idx": 0},
            timeout=120,
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        questions = data.get("questions") or []
        # validate shape
        valid_shape = True
        msg_extra = ""
        if len(questions) < 5:
            valid_shape = False
            msg_extra = f" only {len(questions)} questions"
        else:
            for i, q in enumerate(questions[:5]):
                if not (isinstance(q, dict) and "q" in q and "options" in q and "answer_idx" in q and "explanation" in q):
                    valid_shape = False
                    msg_extra = f" item {i} missing keys: {list(q.keys()) if isinstance(q, dict) else type(q)}"
                    break
                opts = q.get("options")
                if not (isinstance(opts, list) and len(opts) == 4 and all(isinstance(o, str) for o in opts)):
                    valid_shape = False
                    msg_extra = f" item {i} options invalid: {opts}"
                    break
                ai = q.get("answer_idx")
                if not (isinstance(ai, int) and 0 <= ai <= 3):
                    valid_shape = False
                    msg_extra = f" item {i} answer_idx invalid: {ai}"
                    break
                if not isinstance(q.get("explanation"), str):
                    valid_shape = False
                    msg_extra = f" item {i} explanation not string"
                    break
        cond = ok and valid_shape and len(questions) >= 5
        record(
            "T6 POST reading-library/quiz",
            cond,
            f"HTTP {r.status_code} q_count={len(questions)} cached={data.get('cached')}{msg_extra}",
        )
    except Exception as e:
        record("T6 reading-library/quiz", False, f"EXC {e}")

    # --- Test 7: Galaxy Studio create regression ---
    try:
        payload = {
            "title": "qa",
            "genre": "rpg",
            "subgenre": "action_rpg",
            "description": "qa",
            "era_id": "modern",
            "era_label": "Modern",
            "era_year": 2026,
            "locomotion_depth": 5,
            "locomotion_style": "als",
        }
        r = requests.post(f"{BASE}/api/galaxy-studio/create", json=payload, timeout=60)
        ok = r.status_code == 200
        data = r.json() if ok else {}
        bid = data.get("build_id")
        cond = ok and bool(bid)
        record(
            "T7 POST galaxy-studio/create regression",
            cond,
            f"HTTP {r.status_code} build_id={bid} body_keys={list(data.keys())[:6]}",
        )
    except Exception as e:
        record("T7 galaxy-studio/create", False, f"EXC {e}")

    # Summary
    print("\n=== SUMMARY ===")
    passed = sum(1 for s, _, _ in results if s == "PASS")
    total = len(results)
    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
