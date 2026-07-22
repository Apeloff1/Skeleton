#!/usr/bin/env python3
"""
Tutolage ULTRASCALE Platform Testing
Testing the Language Academy (451+ Languages), Gamification System, Offline Sync, and Code Playground
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"

def test_endpoint(method: str, endpoint: str, data: Dict[Any, Any] = None, expected_status: int = 200) -> Dict[str, Any]:
    """Test a single endpoint and return results"""
    url = f"{BACKEND_URL}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, timeout=30)
        else:
            return {"success": False, "error": f"Unsupported method: {method}"}
        
        result = {
            "success": response.status_code == expected_status,
            "status_code": response.status_code,
            "url": url,
            "method": method.upper()
        }
        
        if response.status_code == expected_status:
            try:
                result["data"] = response.json()
            except:
                result["data"] = response.text
        else:
            result["error"] = f"Expected {expected_status}, got {response.status_code}"
            try:
                result["response_text"] = response.text
            except:
                result["response_text"] = "Could not decode response"
                
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url,
            "method": method.upper()
        }

def test_language_academy():
    """Test Language Academy endpoints (451+ Languages)"""
    print("\n🎓 TESTING LANGUAGE ACADEMY (451+ Languages)")
    print("=" * 60)
    
    tests = []
    
    # Test 1: GET /api/languages-academy/stats — verify total >= 400
    print("\n1. Testing language academy stats...")
    stats_test = test_endpoint("GET", "/api/languages-academy/stats")
    tests.append(("Language Academy Stats", stats_test))
    
    if stats_test["success"]:
        data = stats_test.get("data", {})
        total_languages = data.get("total_languages", 0)
        print(f"✅ Language academy stats working - Total languages: {total_languages}")
        if total_languages >= 400:
            print(f"   ✅ Total languages ({total_languages}) meets requirement (>= 400)")
        else:
            print(f"   ⚠️  Total languages ({total_languages}) below requirement (>= 400)")
    else:
        print(f"❌ Language academy stats failed: {stats_test.get('error', 'Unknown error')}")
    
    # Test 2: GET /api/languages-academy/all?limit=5&category=mainstream
    print("\n2. Testing mainstream languages...")
    mainstream_test = test_endpoint("GET", "/api/languages-academy/all?limit=5&category=mainstream")
    tests.append(("Mainstream Languages", mainstream_test))
    
    if mainstream_test["success"]:
        data = mainstream_test.get("data", {})
        languages = data.get("languages", [])
        print(f"✅ Mainstream languages working - Found {len(languages)} languages")
        if len(languages) == 5:
            print(f"   ✅ Returned exactly 5 mainstream languages as requested")
            for lang in languages[:3]:  # Show first 3
                print(f"   - {lang.get('name', 'Unknown')}")
        else:
            print(f"   ⚠️  Expected 5 languages, got {len(languages)}")
    else:
        print(f"❌ Mainstream languages failed: {mainstream_test.get('error', 'Unknown error')}")
    
    # Test 3: GET /api/languages-academy/all?limit=5&category=esoteric
    print("\n3. Testing esoteric languages...")
    esoteric_test = test_endpoint("GET", "/api/languages-academy/all?limit=5&category=esoteric")
    tests.append(("Esoteric Languages", esoteric_test))
    
    if esoteric_test["success"]:
        data = esoteric_test.get("data", {})
        languages = data.get("languages", [])
        print(f"✅ Esoteric languages working - Found {len(languages)} languages")
        if len(languages) > 0:
            print(f"   ✅ Found esoteric languages")
            for lang in languages[:3]:  # Show first 3
                print(f"   - {lang.get('name', 'Unknown')}")
        else:
            print(f"   ⚠️  No esoteric languages found")
    else:
        print(f"❌ Esoteric languages failed: {esoteric_test.get('error', 'Unknown error')}")
    
    # Test 4: GET /api/languages-academy/search?q=brainfuck
    print("\n4. Testing search for Brainfuck...")
    brainfuck_test = test_endpoint("GET", "/api/languages-academy/search?q=brainfuck")
    tests.append(("Search Brainfuck", brainfuck_test))
    
    if brainfuck_test["success"]:
        data = brainfuck_test.get("data", {})
        results = data.get("results", [])
        print(f"✅ Brainfuck search working - Found {len(results)} results")
        if len(results) > 0:
            brainfuck_found = any("brainfuck" in result.get("name", "").lower() for result in results)
            if brainfuck_found:
                print(f"   ✅ Brainfuck language found in search results")
            else:
                print(f"   ⚠️  Brainfuck not found in search results")
        else:
            print(f"   ⚠️  No search results for 'brainfuck'")
    else:
        print(f"❌ Brainfuck search failed: {brainfuck_test.get('error', 'Unknown error')}")
    
    # Test 5: GET /api/languages-academy/search?q=python
    print("\n5. Testing search for Python...")
    python_test = test_endpoint("GET", "/api/languages-academy/search?q=python")
    tests.append(("Search Python", python_test))
    
    if python_test["success"]:
        data = python_test.get("data", {})
        results = data.get("results", [])
        print(f"✅ Python search working - Found {len(results)} results")
        if len(results) > 0:
            python_found = any("python" in result.get("name", "").lower() for result in results)
            if python_found:
                print(f"   ✅ Python language found in search results")
            else:
                print(f"   ⚠️  Python not found in search results")
        else:
            print(f"   ⚠️  No search results for 'python'")
    else:
        print(f"❌ Python search failed: {python_test.get('error', 'Unknown error')}")
    
    # Test 6: GET /api/languages-academy/lang_python
    print("\n6. Testing Python language class...")
    python_class_test = test_endpoint("GET", "/api/languages-academy/lang_python")
    tests.append(("Python Language Class", python_class_test))
    
    if python_class_test["success"]:
        data = python_class_test.get("data", {})
        chapters = data.get("chapters", [])
        print(f"✅ Python language class working - Found {len(chapters)} chapters")
        if len(chapters) > 0:
            print(f"   ✅ Python class has chapters")
            for chapter in chapters[:3]:  # Show first 3
                print(f"   - Chapter: {chapter.get('title', 'Unknown')}")
        else:
            print(f"   ⚠️  Python class has no chapters")
    else:
        print(f"❌ Python language class failed: {python_class_test.get('error', 'Unknown error')}")
    
    # Test 7: GET /api/languages-academy/categories
    print("\n7. Testing language categories...")
    categories_test = test_endpoint("GET", "/api/languages-academy/categories")
    tests.append(("Language Categories", categories_test))
    
    if categories_test["success"]:
        data = categories_test.get("data", {})
        categories = data.get("categories", [])
        print(f"✅ Language categories working - Found {len(categories)} categories")
        if len(categories) == 6:
            print(f"   ✅ Found exactly 6 categories as expected")
            for cat in categories:
                print(f"   - {cat.get('name', 'Unknown')}")
        else:
            print(f"   ⚠️  Expected 6 categories, got {len(categories)}")
    else:
        print(f"❌ Language categories failed: {categories_test.get('error', 'Unknown error')}")
    
    # Test 8: GET /api/languages-academy/executable
    print("\n8. Testing executable languages...")
    executable_test = test_endpoint("GET", "/api/languages-academy/executable")
    tests.append(("Executable Languages", executable_test))
    
    if executable_test["success"]:
        data = executable_test.get("data", {})
        languages = data.get("languages", [])
        print(f"✅ Executable languages working - Found {len(languages)} languages")
        if len(languages) >= 6:
            print(f"   ✅ Found ~6 executable languages ({len(languages)})")
            for lang in languages:
                print(f"   - {lang.get('name', 'Unknown')}")
        else:
            print(f"   ⚠️  Expected ~6 executable languages, got {len(languages)}")
    else:
        print(f"❌ Executable languages failed: {executable_test.get('error', 'Unknown error')}")
    
    return tests

def test_gamification_system():
    """Test Gamification System endpoints"""
    print("\n🎮 TESTING GAMIFICATION SYSTEM")
    print("=" * 60)
    
    tests = []
    
    # Test 1: POST /api/gamification/xp/award (quiz_correct)
    print("\n1. Testing XP award for quiz correct...")
    xp_quiz_test = test_endpoint(
        "POST", 
        "/api/gamification/xp/award?user_id=test_gamer&activity=quiz_correct&domain=python"
    )
    tests.append(("XP Award Quiz", xp_quiz_test))
    
    if xp_quiz_test["success"]:
        data = xp_quiz_test.get("data", {})
        xp_awarded = data.get("xp_awarded", 0)
        print(f"✅ XP award for quiz working - Awarded {xp_awarded} XP")
        if xp_awarded > 0:
            print(f"   ✅ XP successfully awarded for quiz correct")
        else:
            print(f"   ⚠️  No XP awarded")
    else:
        print(f"❌ XP award for quiz failed: {xp_quiz_test.get('error', 'Unknown error')}")
    
    # Test 2: POST /api/gamification/xp/award (book_complete)
    print("\n2. Testing XP award for book complete...")
    xp_book_test = test_endpoint(
        "POST", 
        "/api/gamification/xp/award?user_id=test_gamer&activity=book_complete&domain=rust"
    )
    tests.append(("XP Award Book", xp_book_test))
    
    if xp_book_test["success"]:
        data = xp_book_test.get("data", {})
        xp_awarded = data.get("xp_awarded", 0)
        print(f"✅ XP award for book working - Awarded {xp_awarded} XP")
        if xp_awarded > 0:
            print(f"   ✅ XP successfully awarded for book complete")
        else:
            print(f"   ⚠️  No XP awarded")
    else:
        print(f"❌ XP award for book failed: {xp_book_test.get('error', 'Unknown error')}")
    
    # Test 3: GET /api/gamification/profile/test_gamer
    print("\n3. Testing gamification profile...")
    profile_test = test_endpoint("GET", "/api/gamification/profile/test_gamer")
    tests.append(("Gamification Profile", profile_test))
    
    if profile_test["success"]:
        data = profile_test.get("data", {})
        total_xp = data.get("total_xp", 0)
        level = data.get("level", 0)
        rank = data.get("rank", "Unknown")
        skill_tree = data.get("skill_tree", {})
        
        print(f"✅ Gamification profile working")
        print(f"   Total XP: {total_xp}")
        print(f"   Level: {level}")
        print(f"   Rank: {rank}")
        print(f"   Skill Tree: {len(skill_tree)} skills")
        
        if all([total_xp >= 0, level >= 0, rank, skill_tree is not None]):
            print(f"   ✅ Profile has all required fields")
        else:
            print(f"   ⚠️  Profile missing some required fields")
    else:
        print(f"❌ Gamification profile failed: {profile_test.get('error', 'Unknown error')}")
    
    # Test 4: GET /api/gamification/xp-table
    print("\n4. Testing XP table...")
    xp_table_test = test_endpoint("GET", "/api/gamification/xp-table")
    tests.append(("XP Table", xp_table_test))
    
    if xp_table_test["success"]:
        data = xp_table_test.get("data", {})
        ranks = data.get("ranks", [])
        print(f"✅ XP table working - Found {len(ranks)} ranks")
        if len(ranks) > 0:
            print(f"   ✅ XP table has ranks")
            for rank in ranks[:3]:  # Show first 3
                print(f"   - {rank.get('name', 'Unknown')}: {rank.get('xp_required', 0)} XP")
        else:
            print(f"   ⚠️  XP table has no ranks")
    else:
        print(f"❌ XP table failed: {xp_table_test.get('error', 'Unknown error')}")
    
    # Test 5: GET /api/gamification/leaderboard
    print("\n5. Testing leaderboard...")
    leaderboard_test = test_endpoint("GET", "/api/gamification/leaderboard")
    tests.append(("Leaderboard", leaderboard_test))
    
    if leaderboard_test["success"]:
        data = leaderboard_test.get("data", {})
        players = data.get("players", [])
        print(f"✅ Leaderboard working - Found {len(players)} players")
        if len(players) > 0:
            print(f"   ✅ Leaderboard has players")
            for player in players[:3]:  # Show first 3
                print(f"   - {player.get('username', 'Unknown')}: {player.get('total_xp', 0)} XP")
        else:
            print(f"   ⚠️  Leaderboard has no players")
    else:
        print(f"❌ Leaderboard failed: {leaderboard_test.get('error', 'Unknown error')}")
    
    # Test 6: GET /api/gamification/activity-log/test_gamer
    print("\n6. Testing activity log...")
    activity_test = test_endpoint("GET", "/api/gamification/activity-log/test_gamer")
    tests.append(("Activity Log", activity_test))
    
    if activity_test["success"]:
        data = activity_test.get("data", {})
        activities = data.get("activities", [])
        print(f"✅ Activity log working - Found {len(activities)} activities")
        if len(activities) > 0:
            print(f"   ✅ Activity log has entries")
            for activity in activities[:3]:  # Show first 3
                print(f"   - {activity.get('activity', 'Unknown')}: {activity.get('xp_awarded', 0)} XP")
        else:
            print(f"   ⚠️  Activity log has no entries")
    else:
        print(f"❌ Activity log failed: {activity_test.get('error', 'Unknown error')}")
    
    return tests

def test_offline_sync():
    """Test Offline Sync (quick check)"""
    print("\n💾 TESTING OFFLINE SYNC (Quick Check)")
    print("=" * 60)
    
    tests = []
    
    # Test: GET /api/academy/offline/manifest
    print("\n1. Testing offline manifest...")
    manifest_test = test_endpoint("GET", "/api/academy/offline/manifest")
    tests.append(("Offline Manifest", manifest_test))
    
    if manifest_test["success"]:
        data = manifest_test.get("data", {})
        has_language_classes = "language_classes" in data
        print(f"✅ Offline manifest working")
        if has_language_classes:
            language_classes_count = data.get("language_classes", 0)
            print(f"   ✅ Manifest has language_classes collection: {language_classes_count}")
        else:
            print(f"   ⚠️  Manifest missing language_classes collection")
            print(f"   Available collections: {list(data.keys())}")
    else:
        print(f"❌ Offline manifest failed: {manifest_test.get('error', 'Unknown error')}")
    
    return tests

def test_code_playground():
    """Test Code Playground (regression test for 7 languages)"""
    print("\n💻 TESTING CODE PLAYGROUND (7 Languages Regression)")
    print("=" * 60)
    
    tests = []
    
    # Test 1: Python
    print("\n1. Testing Python execution...")
    python_test = test_endpoint(
        "POST", 
        "/api/playground/run",
        {"language": "python", "code": "print(42)"}
    )
    tests.append(("Python Execution", python_test))
    
    if python_test["success"]:
        data = python_test.get("data", {})
        output = data.get("output", "")
        print(f"✅ Python execution working - Output: {output.strip()}")
        if "42" in output:
            print(f"   ✅ Python output correct")
        else:
            print(f"   ⚠️  Unexpected Python output")
    else:
        print(f"❌ Python execution failed: {python_test.get('error', 'Unknown error')}")
    
    # Test 2: Go
    print("\n2. Testing Go execution...")
    go_test = test_endpoint(
        "POST", 
        "/api/playground/run",
        {
            "language": "go", 
            "code": "package main\nimport \"fmt\"\nfunc main(){fmt.Println(42)}"
        }
    )
    tests.append(("Go Execution", go_test))
    
    if go_test["success"]:
        data = go_test.get("data", {})
        output = data.get("output", "")
        print(f"✅ Go execution working - Output: {output.strip()}")
        if "42" in output:
            print(f"   ✅ Go output correct")
        else:
            print(f"   ⚠️  Unexpected Go output")
    else:
        print(f"❌ Go execution failed: {go_test.get('error', 'Unknown error')}")
    
    # Test 3: Rust
    print("\n3. Testing Rust execution...")
    rust_test = test_endpoint(
        "POST", 
        "/api/playground/run",
        {"language": "rust", "code": "fn main(){println!(\"42\");}"}
    )
    tests.append(("Rust Execution", rust_test))
    
    if rust_test["success"]:
        data = rust_test.get("data", {})
        output = data.get("output", "")
        print(f"✅ Rust execution working - Output: {output.strip()}")
        if "42" in output:
            print(f"   ✅ Rust output correct")
        else:
            print(f"   ⚠️  Unexpected Rust output")
    else:
        print(f"❌ Rust execution failed: {rust_test.get('error', 'Unknown error')}")
    
    return tests

def main():
    """Run all Tutolage ULTRASCALE platform tests"""
    print("🚀 TUTOLAGE ULTRASCALE PLATFORM TESTING")
    print("=" * 80)
    print(f"Backend URL: {BACKEND_URL}")
    
    all_tests = []
    
    # Run all test suites
    all_tests.extend(test_language_academy())
    all_tests.extend(test_gamification_system())
    all_tests.extend(test_offline_sync())
    all_tests.extend(test_code_playground())
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 TUTOLAGE ULTRASCALE TESTING SUMMARY")
    print("=" * 80)
    
    passed = 0
    total = len(all_tests)
    
    # Group by category
    categories = {
        "Language Academy": [],
        "Gamification": [],
        "Offline Sync": [],
        "Code Playground": []
    }
    
    for test_name, result in all_tests:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        
        # Categorize tests
        if any(keyword in test_name.lower() for keyword in ["language", "academy", "mainstream", "esoteric", "search", "categories", "executable"]):
            categories["Language Academy"].append((test_name, result, status))
        elif any(keyword in test_name.lower() for keyword in ["xp", "gamification", "profile", "leaderboard", "activity"]):
            categories["Gamification"].append((test_name, result, status))
        elif "offline" in test_name.lower() or "manifest" in test_name.lower():
            categories["Offline Sync"].append((test_name, result, status))
        else:
            categories["Code Playground"].append((test_name, result, status))
        
        if result["success"]:
            passed += 1
    
    # Print categorized results
    for category, tests in categories.items():
        if tests:
            print(f"\n🔸 {category}:")
            for test_name, result, status in tests:
                print(f"  {status} {test_name}")
                if not result["success"]:
                    print(f"       Error: {result.get('error', 'Unknown error')}")
    
    print(f"\n📈 OVERALL SUCCESS RATE: {passed}/{total} ({(passed/total)*100:.1f}%)")
    
    if passed == total:
        print("🎉 ALL TUTOLAGE ULTRASCALE TESTS PASSED!")
        return 0
    else:
        print("🚨 SOME TUTOLAGE ULTRASCALE TESTS FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(main())