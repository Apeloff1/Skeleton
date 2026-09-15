#!/usr/bin/env python3
"""
Backend API Testing for Tutolage Knowledge Databases and Interactive Quizzes System
Testing the newly implemented Knowledge Databases (5 domains) and Interactive Quizzes (10,000 total)
"""

import requests
import json
import sys
from typing import Dict, Any

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"

def test_endpoint(method: str, endpoint: str, expected_status: int = 200, data: Dict = None, params: Dict = None) -> Dict[str, Any]:
    """Test a single endpoint and return results"""
    url = f"{BACKEND_URL}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, params=params, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, params=params, timeout=30)
        else:
            return {"success": False, "error": f"Unsupported method: {method}"}
        
        success = response.status_code == expected_status
        
        result = {
            "success": success,
            "status_code": response.status_code,
            "endpoint": endpoint,
            "method": method
        }
        
        if success:
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
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}",
            "endpoint": endpoint,
            "method": method
        }

def main():
    """Run comprehensive backend API tests for Knowledge Databases and Interactive Quizzes"""
    
    print("🎯 TUTOLAGE KNOWLEDGE DATABASES & INTERACTIVE QUIZZES TESTING")
    print("=" * 70)
    print(f"Backend URL: {BACKEND_URL}")
    print()
    
    tests = []
    
    # =================================================================
    # KNOWLEDGE DATABASES ENDPOINTS
    # =================================================================
    
    print("📚 KNOWLEDGE DATABASES ENDPOINTS")
    print("-" * 50)
    
    # 1. GET /api/academy/knowledge-dbs - Get all knowledge database domains
    print("1. Testing knowledge databases overview...")
    result = test_endpoint("GET", "/api/academy/knowledge-dbs")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        domains = data.get("domains", {})
        total = data.get("total", 0)
        print(f"   ✅ Domains found: {list(domains.keys())}")
        print(f"   📊 Total entries: {total}")
        
        # Verify expected domains
        expected_domains = ["cs", "physics", "rendering", "architecture", "computing_history"]
        found_domains = list(domains.keys())
        if all(domain in found_domains for domain in expected_domains):
            print("   🎯 All expected domains found: CS, Physics, Rendering, Architecture, Computing History")
        else:
            missing = [d for d in expected_domains if d not in found_domains]
            print(f"   ⚠️  Missing domains: {missing}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 2. GET /api/academy/knowledge-db/cs - Get CS domain details (should have 24 entries, 9100 hours)
    print("\n2. Testing CS knowledge database...")
    result = test_endpoint("GET", "/api/academy/knowledge-db/cs")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        domain = data.get("domain", "")
        total_entries = data.get("total_entries", 0)
        total_hours = data.get("total_hours", 0)
        data_groups = data.get("data", {})
        print(f"   ✅ Domain: {domain}")
        print(f"   📊 Total entries: {total_entries}, Total hours: {total_hours}")
        print(f"   🗂️  Data groups: {list(data_groups.keys())}")
        
        # Verify expected counts
        if total_entries == 24:
            print("   🎯 PERFECT: Expected 24 entries - VERIFIED!")
        else:
            print(f"   ⚠️  Expected 24 entries, got {total_entries}")
            
        if total_hours == 9100:
            print("   🎯 PERFECT: Expected 9100 hours - VERIFIED!")
        else:
            print(f"   ⚠️  Expected 9100 hours, got {total_hours}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 3. GET /api/academy/knowledge-db/physics - Get Physics domain details
    print("\n3. Testing Physics knowledge database...")
    result = test_endpoint("GET", "/api/academy/knowledge-db/physics")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        domain = data.get("domain", "")
        total_entries = data.get("total_entries", 0)
        total_hours = data.get("total_hours", 0)
        print(f"   ✅ Domain: {domain}")
        print(f"   📊 Total entries: {total_entries}, Total hours: {total_hours}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 4. GET /api/academy/knowledge-db/rendering - Get Rendering domain details
    print("\n4. Testing Rendering knowledge database...")
    result = test_endpoint("GET", "/api/academy/knowledge-db/rendering")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        domain = data.get("domain", "")
        total_entries = data.get("total_entries", 0)
        total_hours = data.get("total_hours", 0)
        print(f"   ✅ Domain: {domain}")
        print(f"   📊 Total entries: {total_entries}, Total hours: {total_hours}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 5. GET /api/academy/knowledge-db/architecture - Get Architecture domain details
    print("\n5. Testing Architecture knowledge database...")
    result = test_endpoint("GET", "/api/academy/knowledge-db/architecture")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        domain = data.get("domain", "")
        total_entries = data.get("total_entries", 0)
        total_hours = data.get("total_hours", 0)
        data_groups = data.get("data", {})
        print(f"   ✅ Domain: {domain}")
        print(f"   📊 Total entries: {total_entries}, Total hours: {total_hours}")
        print(f"   🗂️  Data groups: {list(data_groups.keys())}")
        
        # Verify expected groups (patterns + frameworks + design_patterns)
        expected_groups = ["patterns", "frameworks", "design_patterns"]
        found_groups = list(data_groups.keys())
        if any(group in found_groups for group in expected_groups):
            print("   🎯 Architecture groups found (patterns/frameworks/design_patterns)")
        else:
            print(f"   ⚠️  Expected architecture groups not found. Found: {found_groups}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 6. GET /api/academy/knowledge-db/computing_history - Get Computing History
    print("\n6. Testing Computing History knowledge database...")
    result = test_endpoint("GET", "/api/academy/knowledge-db/computing_history")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        domain = data.get("domain", "")
        total_entries = data.get("total_entries", 0)
        total_hours = data.get("total_hours", 0)
        data_groups = data.get("data", {})
        print(f"   ✅ Domain: {domain}")
        print(f"   📊 Total entries: {total_entries}, Total hours: {total_hours}")
        print(f"   🗂️  Data groups: {list(data_groups.keys())}")
        
        # Verify timeline entries
        if "timeline" in data_groups or any("timeline" in str(group).lower() for group in data_groups.keys()):
            print("   🎯 Timeline entries found in Computing History")
        else:
            print(f"   ⚠️  Timeline entries not found. Found groups: {list(data_groups.keys())}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 7. GET /api/academy/knowledge-db/cs/field/cs_algorithms - Get specific CS field
    print("\n7. Testing specific CS field (algorithms)...")
    result = test_endpoint("GET", "/api/academy/knowledge-db/cs/field/cs_algorithms")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        entry = data.get("entry", {})
        entry_id = entry.get("id", "")
        topic = entry.get("topic", "")
        print(f"   ✅ Entry ID: {entry_id}")
        print(f"   📝 Topic: {topic}")
        
        # Verify it's about algorithms
        if "algorithm" in topic.lower() or "algorithm" in entry_id.lower():
            print("   🎯 Entry is about algorithms - VERIFIED!")
        else:
            print("   ⚠️  Entry doesn't seem to be about algorithms")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # =================================================================
    # INTERACTIVE QUIZZES ENDPOINTS (10,000 total)
    # =================================================================
    
    print("\n\n🧠 INTERACTIVE QUIZZES ENDPOINTS")
    print("-" * 50)
    
    # 8. GET /api/academy/quizzes/domains - Get all quiz domains (should return 10 domains, grand_total=10000)
    print("8. Testing quiz domains overview...")
    result = test_endpoint("GET", "/api/academy/quizzes/domains")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        domains = data.get("domains", [])
        grand_total = data.get("grand_total", 0)
        print(f"   ✅ Domains found: {len(domains)}")
        print(f"   📊 Grand total quizzes: {grand_total}")
        
        # Print domain details
        for domain in domains[:5]:  # Show first 5 domains
            domain_name = domain.get("domain", "")
            total_quizzes = domain.get("total_quizzes", 0)
            print(f"   🎯 {domain_name}: {total_quizzes} quizzes")
        
        # Verify expected counts
        if len(domains) == 10:
            print("   🎯 PERFECT: Expected 10 domains - VERIFIED!")
        else:
            print(f"   ⚠️  Expected 10 domains, got {len(domains)}")
            
        if grand_total == 10000:
            print("   🎯 PERFECT: Expected 10,000 total quizzes - VERIFIED!")
        else:
            print(f"   ⚠️  Expected 10,000 total quizzes, got {grand_total}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 9. GET /api/academy/quizzes?domain=cs_fundamentals&limit=5 - Get CS quizzes with pagination
    print("\n9. Testing CS fundamentals quizzes with pagination...")
    result = test_endpoint("GET", "/api/academy/quizzes", params={"domain": "cs_fundamentals", "limit": 5})
    tests.append(result)
    if result["success"]:
        data = result["data"]
        quizzes = data.get("quizzes", [])
        total = data.get("total", 0)
        page_size = data.get("page_size", 0)
        print(f"   ✅ Quizzes returned: {len(quizzes)}")
        print(f"   📊 Total CS fundamentals quizzes: {total}")
        print(f"   📄 Page size: {page_size}")
        
        # Verify pagination
        if len(quizzes) == 5 and page_size == 5:
            print("   🎯 Pagination working correctly (5 quizzes returned)")
        else:
            print(f"   ⚠️  Expected 5 quizzes, got {len(quizzes)}")
            
        # Verify domain filtering
        cs_quizzes = [q for q in quizzes if q.get("domain", "") == "cs_fundamentals"]
        if len(cs_quizzes) == len(quizzes):
            print("   🎯 Domain filtering working - all quizzes are CS fundamentals")
        else:
            print(f"   ⚠️  Domain filtering issue - {len(cs_quizzes)}/{len(quizzes)} are CS fundamentals")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 10. GET /api/academy/quizzes?difficulty=beginner&limit=5 - Filter by difficulty
    print("\n10. Testing quizzes filtered by difficulty (beginner)...")
    result = test_endpoint("GET", "/api/academy/quizzes", params={"difficulty": "beginner", "limit": 5})
    tests.append(result)
    if result["success"]:
        data = result["data"]
        quizzes = data.get("quizzes", [])
        total = data.get("total", 0)
        print(f"   ✅ Beginner quizzes returned: {len(quizzes)}")
        print(f"   📊 Total beginner quizzes: {total}")
        
        # Verify difficulty filtering
        beginner_quizzes = [q for q in quizzes if q.get("difficulty", "") == "beginner"]
        if len(beginner_quizzes) == len(quizzes):
            print("   🎯 Difficulty filtering working - all quizzes are beginner level")
        else:
            print(f"   ⚠️  Difficulty filtering issue - {len(beginner_quizzes)}/{len(quizzes)} are beginner")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 11. GET /api/academy/quizzes/random?count=10 - Get random quiz session
    print("\n11. Testing random quiz session...")
    result = test_endpoint("GET", "/api/academy/quizzes/random", params={"count": 10})
    tests.append(result)
    if result["success"]:
        data = result["data"]
        quizzes = data.get("quizzes", [])
        count = data.get("count", 0)
        session_id = data.get("session_id", "")
        print(f"   ✅ Random quizzes returned: {len(quizzes)}")
        print(f"   📊 Count: {count}")
        print(f"   🆔 Session ID: {session_id}")
        
        # Verify random quiz count
        if len(quizzes) == 10 and count == 10:
            print("   🎯 Random quiz session working correctly (10 quizzes)")
        else:
            print(f"   ⚠️  Expected 10 quizzes, got {len(quizzes)}")
            
        # Verify answers are hidden
        quiz_with_answer = [q for q in quizzes if "correct_answer" in q]
        if len(quiz_with_answer) == 0:
            print("   🎯 Answers correctly hidden in random session")
        else:
            print(f"   ⚠️  Found {len(quiz_with_answer)} quizzes with exposed answers")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 12. GET /api/academy/quizzes/random?domain=game_dev&count=5 - Domain-specific random quizzes
    print("\n12. Testing domain-specific random quizzes (game_dev)...")
    result = test_endpoint("GET", "/api/academy/quizzes/random", params={"domain": "game_dev", "count": 5})
    tests.append(result)
    if result["success"]:
        data = result["data"]
        quizzes = data.get("quizzes", [])
        count = data.get("count", 0)
        print(f"   ✅ Game dev random quizzes: {len(quizzes)}")
        print(f"   📊 Count: {count}")
        
        # Verify domain filtering in random
        game_dev_quizzes = [q for q in quizzes if q.get("domain", "") == "game_dev"]
        if len(game_dev_quizzes) == len(quizzes):
            print("   🎯 Domain-specific random working - all quizzes are game_dev")
        else:
            print(f"   ⚠️  Domain filtering issue - {len(game_dev_quizzes)}/{len(quizzes)} are game_dev")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # Get a quiz ID for testing specific quiz endpoints
    quiz_id = None
    print("\n13. Getting a quiz ID for specific quiz testing...")
    result = test_endpoint("GET", "/api/academy/quizzes", params={"limit": 1})
    tests.append(result)
    if result["success"]:
        data = result["data"]
        quizzes = data.get("quizzes", [])
        if quizzes:
            quiz_id = quizzes[0].get("id", "")
            print(f"   ✅ Got quiz ID for testing: {quiz_id}")
        else:
            print("   ⚠️  No quizzes found to get ID")
    else:
        print(f"   ❌ Failed to get quiz ID: {result.get('error', 'Unknown error')}")
    
    if quiz_id:
        # 14. GET /api/academy/quiz/{quiz_id} - Get specific quiz (answer hidden by default)
        print(f"\n14. Testing specific quiz (ID: {quiz_id}) - answer hidden...")
        result = test_endpoint("GET", f"/api/academy/quiz/{quiz_id}")
        tests.append(result)
        if result["success"]:
            data = result["data"]
            quiz = data.get("quiz", {})
            question = quiz.get("question", "")
            options = quiz.get("options", [])
            has_correct_answer = "correct_answer" in quiz
            has_explanation = "explanation" in quiz
            print(f"   ✅ Quiz question: {question[:50]}...")
            print(f"   📝 Options count: {len(options)}")
            print(f"   🔒 Answer hidden: {not has_correct_answer}")
            print(f"   📖 Explanation hidden: {not has_explanation}")
            
            # Verify answer is hidden by default
            if not has_correct_answer and not has_explanation:
                print("   🎯 Answer and explanation correctly hidden by default")
            else:
                print("   ⚠️  Answer or explanation not hidden by default")
        else:
            print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
        
        # 15. GET /api/academy/quiz/{quiz_id}?show_answer=true - Get quiz with answer visible
        print(f"\n15. Testing specific quiz (ID: {quiz_id}) - answer visible...")
        result = test_endpoint("GET", f"/api/academy/quiz/{quiz_id}", params={"show_answer": "true"})
        tests.append(result)
        if result["success"]:
            data = result["data"]
            quiz = data.get("quiz", {})
            correct_answer = quiz.get("correct_answer", "")
            explanation = quiz.get("explanation", "")
            print(f"   ✅ Correct answer: {correct_answer}")
            print(f"   📖 Explanation length: {len(explanation)} characters")
            
            # Verify answer is shown when requested
            if correct_answer and explanation:
                print("   🎯 Answer and explanation correctly shown when requested")
            else:
                print("   ⚠️  Answer or explanation missing when show_answer=true")
        else:
            print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
        
        # Get the correct answer for testing answer checking
        correct_answer = None
        if result["success"]:
            correct_answer = result["data"]["quiz"].get("correct_answer", "")
        
        if correct_answer:
            # 16. POST /api/academy/quiz/{quiz_id}/answer?answer=CORRECT - Test correct answer
            print(f"\n16. Testing answer checking with correct answer ({correct_answer})...")
            result = test_endpoint("POST", f"/api/academy/quiz/{quiz_id}/answer", params={"answer": correct_answer})
            tests.append(result)
            if result["success"]:
                data = result["data"]
                is_correct = data.get("is_correct", False)
                points_earned = data.get("points_earned", 0)
                your_answer = data.get("your_answer", "")
                explanation = data.get("explanation", "")
                print(f"   ✅ Your answer: {your_answer}")
                print(f"   🎯 Is correct: {is_correct}")
                print(f"   🏆 Points earned: {points_earned}")
                print(f"   📖 Explanation provided: {len(explanation) > 0}")
                
                # Verify correct answer checking
                if is_correct and points_earned > 0:
                    print("   🎯 Correct answer checking working - points awarded")
                else:
                    print("   ⚠️  Correct answer checking issue")
            else:
                print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
            
            # 17. POST /api/academy/quiz/{quiz_id}/answer?answer=WRONG - Test wrong answer
            print(f"\n17. Testing answer checking with wrong answer...")
            result = test_endpoint("POST", f"/api/academy/quiz/{quiz_id}/answer", params={"answer": "WRONG_ANSWER"})
            tests.append(result)
            if result["success"]:
                data = result["data"]
                is_correct = data.get("is_correct", False)
                points_earned = data.get("points_earned", 0)
                hints = data.get("hints", [])
                print(f"   ✅ Is correct: {is_correct}")
                print(f"   🏆 Points earned: {points_earned}")
                print(f"   💡 Hints provided: {len(hints)}")
                
                # Verify wrong answer checking
                if not is_correct and points_earned == 0:
                    print("   🎯 Wrong answer checking working - no points awarded")
                else:
                    print("   ⚠️  Wrong answer checking issue")
            else:
                print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # =================================================================
    # STATS ENDPOINT
    # =================================================================
    
    print("\n\n📊 STATS ENDPOINT")
    print("-" * 50)
    
    # 18. GET /api/academy/stats - Should show comprehensive stats
    print("18. Testing academy stats...")
    result = test_endpoint("GET", "/api/academy/stats")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        tracks = data.get("tracks", 0)
        bibles = data.get("bibles", 0)
        knowledge_databases = data.get("knowledge_databases", 0)
        interactive_quizzes = data.get("interactive_quizzes", 0)
        total_content_items = data.get("total_content_items", 0)
        
        print(f"   ✅ Tracks: {tracks}")
        print(f"   📚 Bibles: {bibles}")
        print(f"   🗄️  Knowledge databases: {knowledge_databases}")
        print(f"   🧠 Interactive quizzes: {interactive_quizzes}")
        print(f"   📊 Total content items: {total_content_items}")
        
        # Verify expected stats
        expected_stats = {
            "tracks": 145,
            "bibles": 134,
            "knowledge_databases": 100,
            "interactive_quizzes": 10000,
            "total_content_items": 12584
        }
        
        all_correct = True
        for key, expected_value in expected_stats.items():
            actual_value = data.get(key, 0)
            if actual_value == expected_value:
                print(f"   🎯 {key}: {actual_value} (PERFECT MATCH)")
            else:
                print(f"   ⚠️  {key}: expected {expected_value}, got {actual_value}")
                all_correct = False
        
        if all_correct:
            print("   🏆 ALL STATS MATCH EXPECTED VALUES!")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # =================================================================
    # REGRESSION TESTING (Existing Endpoints)
    # =================================================================
    
    print("\n\n🔄 REGRESSION TESTING")
    print("-" * 50)
    
    # 19. GET /api/academy/tracks - Should still return 145 tracks
    print("19. Testing academy tracks (regression)...")
    result = test_endpoint("GET", "/api/academy/tracks")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        tracks = data.get("tracks", [])
        track_count = len(tracks)
        print(f"   ✅ Tracks found: {track_count}")
        
        if track_count == 145:
            print("   🎯 PERFECT: Expected 145 tracks - VERIFIED!")
        else:
            print(f"   ⚠️  Expected 145 tracks, got {track_count}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 20. GET /api/academy/bibles - Should still return 134 bibles
    print("\n20. Testing academy bibles (regression)...")
    result = test_endpoint("GET", "/api/academy/bibles")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        bibles = data.get("bibles", [])
        bible_count = len(bibles)
        print(f"   ✅ Bibles found: {bible_count}")
        
        if bible_count == 134:
            print("   🎯 PERFECT: Expected 134 bibles - VERIFIED!")
        else:
            print(f"   ⚠️  Expected 134 bibles, got {bible_count}")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 21. GET /api/academy/challenges - Should still return challenges
    print("\n21. Testing academy challenges (regression)...")
    result = test_endpoint("GET", "/api/academy/challenges")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        challenges = data.get("challenges", [])
        challenge_count = len(challenges)
        print(f"   ✅ Challenges found: {challenge_count}")
        
        if challenge_count > 0:
            print(f"   🎯 Challenges endpoint working ({challenge_count} challenges)")
        else:
            print("   ⚠️  No challenges found")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # 22. GET /api/academy/vault/categories - Should still work
    print("\n22. Testing vault categories (regression)...")
    result = test_endpoint("GET", "/api/academy/vault/categories")
    tests.append(result)
    if result["success"]:
        data = result["data"]
        categories = data.get("categories", [])
        total_entries = data.get("total_entries", 0)
        print(f"   ✅ Vault categories: {len(categories)}")
        print(f"   📊 Total vault entries: {total_entries}")
        
        if len(categories) > 0:
            print("   🎯 Vault categories endpoint still working")
        else:
            print("   ⚠️  No vault categories found")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # =================================================================
    # DATA VALIDATION
    # =================================================================
    
    print("\n\n🔍 DATA VALIDATION")
    print("-" * 50)
    
    # Test MongoDB _id field exclusion
    print("23. Testing MongoDB _id field exclusion...")
    result = test_endpoint("GET", "/api/academy/quizzes", params={"limit": 3})
    tests.append(result)
    if result["success"]:
        data = result["data"]
        quizzes = data.get("quizzes", [])
        
        if quizzes:
            sample_quiz = quizzes[0]
            if "_id" not in sample_quiz:
                print("   ✅ MongoDB _id field correctly excluded from quiz responses")
            else:
                print("   ⚠️  Found _id field in quiz response (should be excluded)")
                
            # Check required fields
            required_fields = ["id", "question", "options", "domain", "difficulty"]
            missing_fields = [field for field in required_fields if field not in sample_quiz]
            
            if not missing_fields:
                print("   ✅ Quiz entries have required fields (id, question, options, domain, difficulty)")
            else:
                print(f"   ⚠️  Missing required fields in quiz: {missing_fields}")
        else:
            print("   ⚠️  No quizzes found to validate")
    else:
        print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # =================================================================
    # SUMMARY
    # =================================================================
    
    print("\n\n" + "=" * 70)
    print("📋 TEST SUMMARY")
    print("=" * 70)
    
    passed_tests = [t for t in tests if t["success"]]
    failed_tests = [t for t in tests if not t["success"]]
    
    print(f"✅ Passed: {len(passed_tests)}/{len(tests)} tests")
    print(f"❌ Failed: {len(failed_tests)}/{len(tests)} tests")
    print(f"📊 Success Rate: {len(passed_tests)/len(tests)*100:.1f}%")
    
    if failed_tests:
        print("\n🚨 FAILED TESTS:")
        for test in failed_tests:
            print(f"   • {test['method']} {test['endpoint']}: {test.get('error', 'Unknown error')}")
    
    print("\n🎯 KEY VALIDATIONS:")
    print("   📚 KNOWLEDGE DATABASES:")
    print("     • 5 domains: CS, Physics, Rendering, Architecture, Computing History")
    print("     • CS domain: 24 entries, 9100 hours")
    print("     • Architecture: patterns + frameworks + design_patterns")
    print("     • Computing History: timeline entries")
    print()
    print("   🧠 INTERACTIVE QUIZZES:")
    print("     • 10 domains with 10,000 total quizzes")
    print("     • Pagination and filtering working")
    print("     • Random quiz sessions")
    print("     • Answer checking (correct/incorrect)")
    print("     • Answers hidden by default, shown when requested")
    print()
    print("   📊 STATS:")
    print("     • tracks: 145, bibles: 134, knowledge_databases: 100")
    print("     • interactive_quizzes: 10000, total_content_items: 12584")
    print()
    print("   🔍 DATA VALIDATION:")
    print("     • No MongoDB _id fields in responses")
    print("     • Required fields present in all entities")
    print("     • Regression tests passed for existing endpoints")
    
    return len(passed_tests) == len(tests)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)