#!/usr/bin/env python3
"""
Backend API Testing for Tutolage Game Factory - Team Hierarchy Endpoints
Tests the newly added team hierarchy endpoints and regression tests.
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com/api"

def test_endpoint(method: str, endpoint: str, expected_status: int = 200, data: Dict = None) -> Dict[str, Any]:
    """Test a single endpoint and return results."""
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
            "endpoint": endpoint,
            "method": method
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
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}",
            "endpoint": endpoint,
            "method": method
        }

def run_tests():
    """Run all Team Hierarchy tests."""
    print("🎮 TUTOLAGE GAME FACTORY - TEAM HIERARCHY ENDPOINTS TESTING")
    print("=" * 80)
    
    tests = []
    
    # =============================================================================
    # NEW HIERARCHY ENDPOINTS TESTING
    # =============================================================================
    
    print("\n🏢 NEW HIERARCHY ENDPOINTS TESTING")
    print("-" * 50)
    
    # Test 1: GET /api/game-factory/hierarchy-agents (should return 52 total agents across 4 categories)
    print("1. Testing GET /api/game-factory/hierarchy-agents...")
    result = test_endpoint("GET", "/game-factory/hierarchy-agents")
    tests.append(result)
    
    if result["success"]:
        data = result["data"]
        agents = data.get("agents", [])
        total_agents = len(agents)
        
        # Count by category
        division_directors = len([a for a in agents if a.get("category") == "division_directors"])
        team_leaders = len([a for a in agents if a.get("category") == "team_leaders"])
        qa_sub_agents = len([a for a in agents if a.get("category") == "qa_sub_agents"])
        coordination = len([a for a in agents if a.get("category") == "coordination"])
        
        print(f"   ✅ SUCCESS: Found {total_agents} total hierarchy agents")
        print(f"   📊 Division Directors: {division_directors} agents")
        print(f"   📊 Team Leaders: {team_leaders} agents")
        print(f"   📊 QA Sub Agents: {qa_sub_agents} agents")
        print(f"   📊 Coordination: {coordination} agents")
        
        if (total_agents == 52 and division_directors == 6 and team_leaders == 18 
            and qa_sub_agents == 16 and coordination == 12):
            print("   🎯 PERFECT: Exactly 52 agents (6+18+16+12) as expected")
        else:
            print(f"   ⚠️  WARNING: Expected 52 agents (6+18+16+12), got {total_agents} ({division_directors}+{team_leaders}+{qa_sub_agents}+{coordination})")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 2: GET /api/game-factory/hierarchy-agents/division_directors (should return 6 agents)
    print("\n2. Testing GET /api/game-factory/hierarchy-agents/division_directors...")
    result = test_endpoint("GET", "/game-factory/hierarchy-agents/division_directors")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        print(f"   ✅ SUCCESS: Found {len(agents)} Division Directors")
        if len(agents) == 6:
            print("   🎯 PERFECT: Exactly 6 Division Directors")
        else:
            print(f"   ⚠️  WARNING: Expected 6 agents, got {len(agents)}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 3: GET /api/game-factory/hierarchy-agents/team_leaders (should return 18 agents)
    print("\n3. Testing GET /api/game-factory/hierarchy-agents/team_leaders...")
    result = test_endpoint("GET", "/game-factory/hierarchy-agents/team_leaders")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        print(f"   ✅ SUCCESS: Found {len(agents)} Team Leaders")
        if len(agents) == 18:
            print("   🎯 PERFECT: Exactly 18 Team Leaders")
        else:
            print(f"   ⚠️  WARNING: Expected 18 agents, got {len(agents)}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 4: GET /api/game-factory/hierarchy-agents/qa_sub_agents (should return 16 agents)
    print("\n4. Testing GET /api/game-factory/hierarchy-agents/qa_sub_agents...")
    result = test_endpoint("GET", "/game-factory/hierarchy-agents/qa_sub_agents")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        print(f"   ✅ SUCCESS: Found {len(agents)} QA Sub Agents")
        if len(agents) == 16:
            print("   🎯 PERFECT: Exactly 16 QA Sub Agents")
        else:
            print(f"   ⚠️  WARNING: Expected 16 agents, got {len(agents)}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 5: GET /api/game-factory/hierarchy-agents/coordination (should return 12 agents)
    print("\n5. Testing GET /api/game-factory/hierarchy-agents/coordination...")
    result = test_endpoint("GET", "/game-factory/hierarchy-agents/coordination")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        print(f"   ✅ SUCCESS: Found {len(agents)} Coordination agents")
        if len(agents) == 12:
            print("   🎯 PERFECT: Exactly 12 Coordination agents")
        else:
            print(f"   ⚠️  WARNING: Expected 12 agents, got {len(agents)}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 6: GET /api/game-factory/directors (should return 6 agents - C-Suite)
    print("\n6. Testing GET /api/game-factory/directors...")
    result = test_endpoint("GET", "/game-factory/directors")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        print(f"   ✅ SUCCESS: Found {len(agents)} Directors (C-Suite)")
        if len(agents) == 6:
            print("   🎯 PERFECT: Exactly 6 Directors")
        else:
            print(f"   ⚠️  WARNING: Expected 6 agents, got {len(agents)}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 7: GET /api/game-factory/team-leads (should return 18 agents)
    print("\n7. Testing GET /api/game-factory/team-leads...")
    result = test_endpoint("GET", "/game-factory/team-leads")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        print(f"   ✅ SUCCESS: Found {len(agents)} Team Leads")
        if len(agents) == 18:
            print("   🎯 PERFECT: Exactly 18 Team Leads")
        else:
            print(f"   ⚠️  WARNING: Expected 18 agents, got {len(agents)}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 8: GET /api/game-factory/qa-agents (should return 16 agents)
    print("\n8. Testing GET /api/game-factory/qa-agents...")
    result = test_endpoint("GET", "/game-factory/qa-agents")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        print(f"   ✅ SUCCESS: Found {len(agents)} QA Agents")
        if len(agents) == 16:
            print("   🎯 PERFECT: Exactly 16 QA Agents")
        else:
            print(f"   ⚠️  WARNING: Expected 16 agents, got {len(agents)}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 9: GET /api/game-factory/coordination-agents (should return 12 agents)
    print("\n9. Testing GET /api/game-factory/coordination-agents...")
    result = test_endpoint("GET", "/game-factory/coordination-agents")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        print(f"   ✅ SUCCESS: Found {len(agents)} Coordination Agents")
        if len(agents) == 12:
            print("   🎯 PERFECT: Exactly 12 Coordination Agents")
        else:
            print(f"   ⚠️  WARNING: Expected 12 agents, got {len(agents)}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 10: GET /api/game-factory/all-agents-summary (grand total should be 579)
    print("\n10. Testing GET /api/game-factory/all-agents-summary...")
    result = test_endpoint("GET", "/game-factory/all-agents-summary")
    tests.append(result)
    
    if result["success"]:
        data = result["data"]
        grand_total = data.get("grand_total", 0)
        breakdown = data.get("breakdown", {})
        
        print(f"   ✅ SUCCESS: Grand total is {grand_total}")
        print(f"   📊 Breakdown: {breakdown}")
        
        if grand_total == 579:
            print("   🎯 PERFECT: Grand total is exactly 579 (527 + 52 hierarchy)")
        else:
            print(f"   ⚠️  WARNING: Expected grand total 579, got {grand_total}")
            
        # Check if hierarchy agents are included in breakdown
        hierarchy_agents = breakdown.get("hierarchy_agents", 0)
        if hierarchy_agents == 52:
            print("   ✅ Hierarchy agents: 52 (correct)")
        else:
            print(f"   ⚠️  Hierarchy agents: {hierarchy_agents} (expected 52)")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 11: GET /api/agents/chat/rooms (should return 22 rooms total)
    print("\n11. Testing GET /api/agents/chat/rooms...")
    result = test_endpoint("GET", "/agents/chat/rooms")
    tests.append(result)
    
    if result["success"]:
        rooms = result["data"].get("rooms", [])
        total_rooms = len(rooms)
        
        print(f"   ✅ SUCCESS: Found {total_rooms} chat rooms")
        
        if total_rooms == 22:
            print("   🎯 PERFECT: Exactly 22 rooms (18 previous + 4 hierarchy)")
        else:
            print(f"   ⚠️  WARNING: Expected 22 rooms, got {total_rooms}")
        
        # Check for hierarchy rooms
        room_ids = [room.get("id") for room in rooms]
        hierarchy_rooms = ["c_suite", "team_leads", "qa_hub", "coordination_hub"]
        found_hierarchy_rooms = [room for room in hierarchy_rooms if room in room_ids]
        
        if len(found_hierarchy_rooms) == 4:
            print(f"   ✅ All hierarchy rooms found: {found_hierarchy_rooms}")
        else:
            print(f"   ⚠️  WARNING: Expected 4 hierarchy rooms, found {len(found_hierarchy_rooms)}: {found_hierarchy_rooms}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # =============================================================================
    # REGRESSION TESTING
    # =============================================================================
    
    print("\n🔄 REGRESSION TESTING")
    print("-" * 50)
    
    # Test 12: GET /api/game-factory/pipeline (should return 200 total_steps)
    print("12. Testing GET /api/game-factory/pipeline...")
    result = test_endpoint("GET", "/game-factory/pipeline")
    tests.append(result)
    
    if result["success"]:
        data = result["data"]
        steps = data.get("steps", [])
        total_steps = data.get("total_steps", len(steps))
        print(f"   ✅ SUCCESS: Pipeline has {total_steps} steps")
        if total_steps == 200:
            print("   🎯 PERFECT: Exactly 200 steps (no regression)")
        else:
            print(f"   ⚠️  WARNING: Expected 200 steps, got {total_steps}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 13: GET /api/game-factory/genres (should return 52 genres)
    print("\n13. Testing GET /api/game-factory/genres...")
    result = test_endpoint("GET", "/game-factory/genres")
    tests.append(result)
    
    if result["success"]:
        genres = result["data"].get("genres", [])
        total_genres = len(genres)
        print(f"   ✅ SUCCESS: Found {total_genres} genres")
        if total_genres == 52:
            print("   🎯 PERFECT: Exactly 52 genres (no regression)")
        else:
            print(f"   ⚠️  WARNING: Expected 52 genres, got {total_genres}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 14: GET /api/game-factory/roster-agents (should return 76 agents)
    print("\n14. Testing GET /api/game-factory/roster-agents...")
    result = test_endpoint("GET", "/game-factory/roster-agents")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        total_agents = len(agents)
        print(f"   ✅ SUCCESS: Found {total_agents} roster agents")
        if total_agents == 76:
            print("   🎯 PERFECT: Exactly 76 roster agents (no regression)")
        else:
            print(f"   ⚠️  WARNING: Expected 76 agents, got {total_agents}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 15: GET /api/game-factory/academic-agents (should return 32 agents)
    print("\n15. Testing GET /api/game-factory/academic-agents...")
    result = test_endpoint("GET", "/game-factory/academic-agents")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        total_agents = len(agents)
        print(f"   ✅ SUCCESS: Found {total_agents} academic agents")
        if total_agents == 32:
            print("   🎯 PERFECT: Exactly 32 academic agents (no regression)")
        else:
            print(f"   ⚠️  WARNING: Expected 32 agents, got {total_agents}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Test 16: GET /api/game-factory/traffic-control (should return 14 agents)
    print("\n16. Testing GET /api/game-factory/traffic-control...")
    result = test_endpoint("GET", "/game-factory/traffic-control")
    tests.append(result)
    
    if result["success"]:
        agents = result["data"].get("agents", [])
        total_agents = len(agents)
        print(f"   ✅ SUCCESS: Found {total_agents} traffic control agents")
        if total_agents == 14:
            print("   🎯 PERFECT: Exactly 14 traffic control agents (no regression)")
        else:
            print(f"   ⚠️  WARNING: Expected 14 agents, got {total_agents}")
    else:
        print(f"   ❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # =============================================================================
    # SUMMARY
    # =============================================================================
    
    print("\n" + "=" * 80)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed_tests = [t for t in tests if t["success"]]
    failed_tests = [t for t in tests if not t["success"]]
    
    print(f"✅ PASSED: {len(passed_tests)}/{len(tests)} tests")
    print(f"❌ FAILED: {len(failed_tests)}/{len(tests)} tests")
    print(f"📈 SUCCESS RATE: {len(passed_tests)/len(tests)*100:.1f}%")
    
    if failed_tests:
        print("\n❌ FAILED TESTS:")
        for test in failed_tests:
            print(f"   • {test['method']} {test['endpoint']}: {test.get('error', 'Unknown error')}")
    
    print("\n🎯 KEY FINDINGS:")
    
    # Check if all new hierarchy endpoints are working
    new_endpoint_tests = tests[:11]  # First 11 tests are new hierarchy endpoints
    new_passed = len([t for t in new_endpoint_tests if t["success"]])
    
    if new_passed == 11:
        print("   ✅ ALL NEW HIERARCHY ENDPOINTS WORKING")
    else:
        print(f"   ⚠️  NEW HIERARCHY ENDPOINTS: {new_passed}/11 working")
    
    # Check regression tests
    regression_tests = tests[11:]  # Last 5 tests are regression
    regression_passed = len([t for t in regression_tests if t["success"]])
    
    if regression_passed == 5:
        print("   ✅ ALL REGRESSION TESTS PASSED")
    else:
        print(f"   ⚠️  REGRESSION TESTS: {regression_passed}/5 passed")
    
    return len(passed_tests) == len(tests)

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)