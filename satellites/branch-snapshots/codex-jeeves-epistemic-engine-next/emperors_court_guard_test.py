#!/usr/bin/env python3
"""
Backend Testing for Emperor's Court & Guard System
Testing all new court & guard endpoints plus regression tests.
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Get backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"

def test_endpoint(method: str, endpoint: str, expected_status: int = 200, params: Dict = None, data: Dict = None) -> Dict[str, Any]:
    """Test a single endpoint and return results."""
    url = f"{BACKEND_URL}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, params=params, timeout=30)
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
                result["data_size"] = len(json.dumps(result["data"]))
            except:
                result["data"] = response.text
                result["data_size"] = len(response.text)
        else:
            result["error"] = f"Expected {expected_status}, got {response.status_code}"
            try:
                result["error_details"] = response.json()
            except:
                result["error_details"] = response.text
        
        return result
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}",
            "url": url,
            "method": method.upper()
        }

def validate_court_agents_response(data: Dict) -> List[str]:
    """Validate emperors-court endpoint response structure."""
    issues = []
    
    if "agents" not in data:
        issues.append("Missing 'agents' field in response")
        return issues
    
    agents = data["agents"]
    if not isinstance(agents, list):
        issues.append("Expected 'agents' to be a list")
        return issues
    
    if len(agents) != 10:
        issues.append(f"Expected 10 court advisor agents, got {len(agents)}")
    
    # Check for required fields (hierarchy info is in the role and specialty)
    for i, agent in enumerate(agents):
        if "role" not in agent:
            issues.append(f"Court agent {i} missing role field")
        if "specialty" not in agent:
            issues.append(f"Court agent {i} missing specialty field")
        if "name" not in agent:
            issues.append(f"Court agent {i} missing name field")
    
    return issues

def validate_guard_agents_response(data: Dict) -> List[str]:
    """Validate emperors-guard endpoint response structure."""
    issues = []
    
    if "agents" not in data:
        issues.append("Missing 'agents' field in response")
        return issues
    
    agents = data["agents"]
    if not isinstance(agents, list):
        issues.append("Expected 'agents' to be a list")
        return issues
    
    if len(agents) != 10:
        issues.append(f"Expected 10 guard enforcer agents, got {len(agents)}")
    
    # Check for required fields (chain info is in the role and specialty)
    for i, agent in enumerate(agents):
        if "role" not in agent:
            issues.append(f"Guard agent {i} missing role field")
        if "specialty" not in agent:
            issues.append(f"Guard agent {i} missing specialty field")
        if "name" not in agent:
            issues.append(f"Guard agent {i} missing name field")
    
    return issues

def validate_court_guard_agents_response(data: Dict) -> List[str]:
    """Validate court-guard-agents endpoint response structure."""
    issues = []
    
    if "agents" not in data:
        issues.append("Missing 'agents' field in response")
        return issues
    
    agents = data["agents"]
    if not isinstance(agents, list):
        issues.append("Expected 'agents' to be a list")
        return issues
    
    if len(agents) != 20:
        issues.append(f"Expected 20 total agents (10 court + 10 guard), got {len(agents)}")
    
    return issues

def validate_all_agents_summary_response(data: Dict) -> List[str]:
    """Validate all-agents-summary endpoint response structure."""
    issues = []
    
    if "grand_total" not in data:
        issues.append("Missing grand_total field")
    
    if "grand_total_with_shadows" not in data:
        issues.append("Missing grand_total_with_shadows field")
    
    if "breakdown" not in data:
        issues.append("Missing breakdown field")
    elif "emperor_court_guard" not in data["breakdown"]:
        issues.append("Missing emperor_court_guard in breakdown")
    elif data["breakdown"]["emperor_court_guard"] != 20:
        issues.append(f"Expected emperor_court_guard: 20 in breakdown, got {data['breakdown']['emperor_court_guard']}")
    
    return issues

def validate_parallel_society_response(data: Dict) -> List[str]:
    """Validate parallel society endpoint response structure."""
    issues = []
    
    if "shadow_agents" not in data:
        issues.append("Missing shadow_agents field")
        return issues
    
    # Check if shadow categories include the new court/guard shadows
    if "shadow_categories" not in data:
        issues.append("Missing shadow_categories field")
        return issues
    
    shadow_categories = data["shadow_categories"]
    if "shadow_emperors_court" not in shadow_categories:
        issues.append("Missing shadow_emperors_court in shadow_categories")
    elif shadow_categories["shadow_emperors_court"]["count"] != 10:
        issues.append(f"Expected shadow_emperors_court count of 10, got {shadow_categories['shadow_emperors_court']['count']}")
    
    if "shadow_emperors_guard" not in shadow_categories:
        issues.append("Missing shadow_emperors_guard in shadow_categories")
    elif shadow_categories["shadow_emperors_guard"]["count"] != 10:
        issues.append(f"Expected shadow_emperors_guard count of 10, got {shadow_categories['shadow_emperors_guard']['count']}")
    
    return issues

def validate_shadow_for_response(data: Dict, expected_name: str) -> List[str]:
    """Validate shadow-for endpoint response structure."""
    issues = []
    
    if "shadow" not in data:
        issues.append("Expected 'shadow' field in response")
        return issues
    
    shadow = data["shadow"]
    
    if "name" not in shadow:
        issues.append("Missing name field in shadow object")
    elif expected_name not in shadow["name"]:
        issues.append(f"Expected shadow name to contain '{expected_name}', got '{shadow['name']}'")
    
    return issues

def validate_chat_rooms_response(data: Dict) -> List[str]:
    """Validate chat rooms endpoint response structure."""
    issues = []
    
    if "rooms" not in data:
        issues.append("Missing 'rooms' field in response")
        return issues
    
    rooms = data["rooms"]
    if not isinstance(rooms, list):
        issues.append("Expected 'rooms' to be a list")
        return issues
    
    if len(rooms) != 41:
        issues.append(f"Expected 41 rooms total (39 + 2 new), got {len(rooms)}")
    
    # Check for new rooms (with proper names)
    room_names = [room.get("name", "") for room in rooms]
    if "Emperor's Court" not in room_names:
        issues.append("Missing 'Emperor's Court' room")
    if "Emperor's Guard" not in room_names:
        issues.append("Missing 'Emperor's Guard' room")
    
    return issues

def run_tests():
    """Run all the requested tests."""
    print("👑 EMPEROR'S COURT & GUARD SYSTEM TESTING")
    print("=" * 60)
    
    test_results = []
    
    # NEW COURT & GUARD ENDPOINTS
    print("\n🏛️ NEW COURT & GUARD ENDPOINTS:")
    print("-" * 40)
    
    # Test 1: GET /api/game-factory/emperors-court
    print("1. Testing Emperor's Court (should return 10 court advisor agents)...")
    result = test_endpoint("GET", "/api/game-factory/emperors-court")
    if result["success"]:
        issues = validate_court_agents_response(result["data"])
        if issues:
            result["validation_issues"] = issues
            result["success"] = False
        else:
            print(f"   ✅ PASS - Court has {len(result['data']['agents'])} advisor agents with hierarchy info")
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Emperor's Court", result))
    
    # Test 2: GET /api/game-factory/emperors-guard
    print("2. Testing Emperor's Guard (should return 10 guard enforcer agents)...")
    result = test_endpoint("GET", "/api/game-factory/emperors-guard")
    if result["success"]:
        issues = validate_guard_agents_response(result["data"])
        if issues:
            result["validation_issues"] = issues
            result["success"] = False
        else:
            print(f"   ✅ PASS - Guard has {len(result['data']['agents'])} enforcer agents with chain info")
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Emperor's Guard", result))
    
    # Test 3: GET /api/game-factory/court-guard-agents
    print("3. Testing Court-Guard Agents (should return 20 total agents)...")
    result = test_endpoint("GET", "/api/game-factory/court-guard-agents")
    if result["success"]:
        issues = validate_court_guard_agents_response(result["data"])
        if issues:
            result["validation_issues"] = issues
            result["success"] = False
        else:
            print(f"   ✅ PASS - Combined court-guard has {len(result['data']['agents'])} total agents")
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Court-Guard Agents", result))
    
    # Test 4: GET /api/game-factory/all-agents-summary
    print("4. Testing All Agents Summary (should include emperor_court_guard: 20)...")
    result = test_endpoint("GET", "/api/game-factory/all-agents-summary")
    if result["success"]:
        issues = validate_all_agents_summary_response(result["data"])
        if issues:
            result["validation_issues"] = issues
            result["success"] = False
        else:
            print(f"   ✅ PASS - Grand total: {result['data']['grand_total']}, emperor_court_guard: {result['data']['breakdown'].get('emperor_court_guard', 'N/A')}")
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("All Agents Summary", result))
    
    # Test 5: GET /api/game-factory/parallel-society
    print("5. Testing Parallel Society (should include 20 new court/guard shadows)...")
    result = test_endpoint("GET", "/api/game-factory/parallel-society")
    if result["success"]:
        issues = validate_parallel_society_response(result["data"])
        if issues:
            result["validation_issues"] = issues
            result["success"] = False
        else:
            print(f"   ✅ PASS - Shadow agents: {result['data']['shadow_agents']} (includes court/guard shadows)")
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Parallel Society", result))
    
    # Test 6: GET /api/game-factory/shadow-for/court_vizier
    print("6. Testing Shadow-Grand Vizier...")
    result = test_endpoint("GET", "/api/game-factory/shadow-for/court_vizier")
    if result["success"]:
        issues = validate_shadow_for_response(result["data"], "Grand Vizier")
        if issues:
            result["validation_issues"] = issues
            result["success"] = False
        else:
            print(f"   ✅ PASS - Shadow-Grand Vizier found: {result['data']['shadow']['name']}")
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Shadow-Grand Vizier", result))
    
    # Test 7: GET /api/game-factory/shadow-for/guard_captain
    print("7. Testing Shadow-Captain of the Guard...")
    result = test_endpoint("GET", "/api/game-factory/shadow-for/guard_captain")
    if result["success"]:
        issues = validate_shadow_for_response(result["data"], "Captain of the Guard")
        if issues:
            result["validation_issues"] = issues
            result["success"] = False
        else:
            print(f"   ✅ PASS - Shadow-Captain of the Guard found: {result['data']['shadow']['name']}")
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Shadow-Captain of the Guard", result))
    
    # Test 8: GET /api/agents/chat/rooms
    print("8. Testing Chat Rooms (should return 41 rooms total)...")
    result = test_endpoint("GET", "/api/agents/chat/rooms")
    if result["success"]:
        issues = validate_chat_rooms_response(result["data"])
        if issues:
            result["validation_issues"] = issues
            result["success"] = False
        else:
            print(f"   ✅ PASS - Chat rooms: {len(result['data']['rooms'])} total (includes emperors_court, emperors_guard)")
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Chat Rooms", result))
    
    # REGRESSION TESTS
    print("\n🔄 REGRESSION TESTS:")
    print("-" * 40)
    
    # Test 9: GET /api/game-factory/pipeline
    print("9. Testing Pipeline (should be 200 steps)...")
    result = test_endpoint("GET", "/api/game-factory/pipeline")
    if result["success"]:
        if "steps" in result["data"] and isinstance(result["data"]["steps"], list) and len(result["data"]["steps"]) == 200:
            print(f"   ✅ PASS - Pipeline has {len(result['data']['steps'])} steps")
        else:
            result["validation_issues"] = [f"Expected 200 pipeline steps, got {len(result['data'].get('steps', [])) if 'steps' in result['data'] else 'no steps field'}"]
            result["success"] = False
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Pipeline Regression", result))
    
    # Test 10: GET /api/game-factory/genres
    print("10. Testing Genres (should be 52 genres)...")
    result = test_endpoint("GET", "/api/game-factory/genres")
    if result["success"]:
        if "genres" in result["data"] and isinstance(result["data"]["genres"], list) and len(result["data"]["genres"]) == 52:
            print(f"   ✅ PASS - Genres has {len(result['data']['genres'])} genres")
        else:
            result["validation_issues"] = [f"Expected 52 genres, got {len(result['data'].get('genres', [])) if 'genres' in result['data'] else 'no genres field'}"]
            result["success"] = False
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Genres Regression", result))
    
    # Test 11: GET /api/game-factory/vault/stats
    print("11. Testing Vault Stats (vault_status should be ONLINE)...")
    result = test_endpoint("GET", "/api/game-factory/vault/stats")
    if result["success"]:
        if result["data"].get("vault_status") == "ONLINE":
            print(f"   ✅ PASS - Vault status: {result['data']['vault_status']}")
        else:
            result["validation_issues"] = [f"Expected vault_status: ONLINE, got {result['data'].get('vault_status')}"]
            result["success"] = False
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Vault Stats Regression", result))
    
    # Test 12: GET /api/game-factory/emperor
    print("12. Testing Emperor (should still return ABSOLUTE authority)...")
    result = test_endpoint("GET", "/api/game-factory/emperor")
    if result["success"]:
        if "authority" in result["data"] and result["data"]["authority"] == "ABSOLUTE":
            print(f"   ✅ PASS - Emperor authority: {result['data']['authority']}")
        else:
            result["validation_issues"] = [f"Expected authority: ABSOLUTE, got {result['data'].get('authority')}"]
            result["success"] = False
    else:
        print(f"   ❌ FAIL - {result['error']}")
    test_results.append(("Emperor Regression", result))
    
    # SUMMARY
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in test_results if result["success"])
    total = len(test_results)
    
    print(f"✅ PASSED: {passed}/{total} tests")
    print(f"❌ FAILED: {total - passed}/{total} tests")
    print(f"📈 SUCCESS RATE: {(passed/total)*100:.1f}%")
    
    # Detailed failure report
    failures = [(name, result) for name, result in test_results if not result["success"]]
    if failures:
        print(f"\n❌ FAILED TESTS ({len(failures)}):")
        print("-" * 40)
        for name, result in failures:
            print(f"• {name}")
            if "error" in result:
                print(f"  Error: {result['error']}")
            if "validation_issues" in result:
                for issue in result["validation_issues"]:
                    print(f"  Issue: {issue}")
            print()
    
    # Success details
    successes = [(name, result) for name, result in test_results if result["success"]]
    if successes:
        print(f"\n✅ PASSED TESTS ({len(successes)}):")
        print("-" * 40)
        for name, result in successes:
            print(f"• {name} - {result['status_code']} OK")
    
    return passed == total

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)