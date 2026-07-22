#!/usr/bin/env python3
"""
Post-Refactoring Verification Test
Testing ALL key endpoints to ensure nothing broke during extraction of layers, build, and competitor endpoints into sub-routers.
"""

import requests
import json
import sys
from typing import Dict, Any

# Backend URL from environment
BASE_URL = "https://gemini-game-craft.preview.emergentagent.com/api"

def test_endpoint(method: str, endpoint: str, expected_status: int = 200, data: Dict = None) -> Dict[str, Any]:
    """Test a single endpoint and return response data."""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, timeout=30)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        print(f"[{method}] {endpoint} -> {response.status_code}")
        
        if response.status_code != expected_status:
            return {
                "error": f"Expected {expected_status}, got {response.status_code}",
                "status_code": response.status_code,
                "response": response.text[:500]
            }
        
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response", "response": response.text[:500]}
            
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}

def test_all_agents_summary():
    """Test GET /api/game-factory/all-agents-summary — grand_total_with_all_layers = 25994, 6 quality_layers, competency_matrices + knowledge_engine present"""
    print("\n=== Testing All Agents Summary ===")
    
    result = test_endpoint("GET", "/game-factory/all-agents-summary")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify grand_total_with_all_layers = 25994
    expected_grand_total = 25994
    actual_grand_total = result.get("grand_total_with_all_layers", 0)
    if actual_grand_total != expected_grand_total:
        print(f"❌ FAILED: grand_total_with_all_layers expected {expected_grand_total}, got {actual_grand_total}")
        return False
    print(f"✅ grand_total_with_all_layers: {actual_grand_total}")
    
    # Verify 6 quality_layers (it's an object, not array)
    quality_layers = result.get("quality_layers", {})
    if not isinstance(quality_layers, dict) or len(quality_layers) != 6:
        print(f"❌ FAILED: Expected 6 quality_layers, got {len(quality_layers) if isinstance(quality_layers, dict) else 'N/A'}")
        return False
    print(f"✅ quality_layers: {len(quality_layers)} layers")
    
    # Verify competency_matrices section exists
    competency_matrices = result.get("competency_matrices")
    if not competency_matrices:
        print(f"❌ FAILED: Expected competency_matrices section, got {competency_matrices}")
        return False
    print(f"✅ competency_matrices section present")
    
    # Verify knowledge_engine section exists
    knowledge_engine = result.get("knowledge_engine")
    if not knowledge_engine:
        print(f"❌ FAILED: Expected knowledge_engine section, got {knowledge_engine}")
        return False
    print(f"✅ knowledge_engine section present")
    
    print("✅ All Agents Summary test PASSED")
    return True

def test_hexa_layer():
    """Test GET /api/game-factory/hexa-layer/level_architect_2d — hexa_layer_complete = true, 17 counterparts, all 6 layers"""
    print("\n=== Testing Hexa Layer ===")
    
    result = test_endpoint("GET", "/game-factory/hexa-layer/level_architect_2d")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify hexa_layer_complete = true
    hexa_layer_complete = result.get("hexa_layer_complete")
    if hexa_layer_complete is not True:
        print(f"❌ FAILED: Expected hexa_layer_complete = true, got {hexa_layer_complete}")
        return False
    print(f"✅ hexa_layer_complete: {hexa_layer_complete}")
    
    # Verify 17 counterparts (check total_counterparts field)
    total_counterparts = result.get("total_counterparts", 0)
    if total_counterparts != 17:
        print(f"❌ FAILED: Expected 17 counterparts, got {total_counterparts}")
        return False
    print(f"✅ total_counterparts: {total_counterparts} agents")
    
    # Verify all 6 layers
    layers = result.get("layers", {})
    expected_layer_keys = ["original", "shadow", "ghost", "angels", "seraphim", "cherubim"]
    for layer_key in expected_layer_keys:
        if layer_key not in layers:
            print(f"❌ FAILED: Missing layer: {layer_key}")
            return False
    print(f"✅ All 6 layers present: {list(layers.keys())}")
    
    print("✅ Hexa Layer test PASSED")
    return True

def test_quad_layer():
    """Test GET /api/game-factory/quad-layer/level_architect_2d — backward compat"""
    print("\n=== Testing Quad Layer (Backward Compatibility) ===")
    
    result = test_endpoint("GET", "/game-factory/quad-layer/level_architect_2d")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Should have basic structure for backward compatibility
    if not isinstance(result, dict):
        print(f"❌ FAILED: Expected dict response, got {type(result)}")
        return False
    
    print(f"✅ Quad layer backward compatibility working")
    print("✅ Quad Layer test PASSED")
    return True

def test_angel_class():
    """Test GET /api/game-factory/angel-class — total_angels = 4326"""
    print("\n=== Testing Angel Class ===")
    
    result = test_endpoint("GET", "/game-factory/angel-class")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify total_angels = 4326
    expected_total_angels = 4326
    actual_total_angels = result.get("total_angels", 0)
    if actual_total_angels != expected_total_angels:
        print(f"❌ FAILED: Expected total_angels = {expected_total_angels}, got {actual_total_angels}")
        return False
    print(f"✅ total_angels: {actual_total_angels}")
    
    print("✅ Angel Class test PASSED")
    return True

def test_ghost_society():
    """Test GET /api/game-factory/ghost-society — ghost_agents = 1442"""
    print("\n=== Testing Ghost Society ===")
    
    result = test_endpoint("GET", "/game-factory/ghost-society")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify ghost_agents = 1442
    expected_ghost_agents = 1442
    actual_ghost_agents = result.get("ghost_agents", 0)
    if actual_ghost_agents != expected_ghost_agents:
        print(f"❌ FAILED: Expected ghost_agents = {expected_ghost_agents}, got {actual_ghost_agents}")
        return False
    print(f"✅ ghost_agents: {actual_ghost_agents}")
    
    print("✅ Ghost Society test PASSED")
    return True

def test_parallel_society():
    """Test GET /api/game-factory/parallel-society — shadow_agents exist"""
    print("\n=== Testing Parallel Society ===")
    
    result = test_endpoint("GET", "/game-factory/parallel-society")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify shadow_agents exist
    shadow_agents = result.get("shadow_agents")
    if shadow_agents is None or shadow_agents <= 0:
        print(f"❌ FAILED: Expected shadow_agents > 0, got {shadow_agents}")
        return False
    print(f"✅ shadow_agents: {shadow_agents}")
    
    print("✅ Parallel Society test PASSED")
    return True

def test_pipeline():
    """Test GET /api/game-factory/pipeline — 200 steps"""
    print("\n=== Testing Pipeline ===")
    
    result = test_endpoint("GET", "/game-factory/pipeline")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify 200 steps
    expected_steps = 200
    actual_steps = result.get("total_steps", 0)
    if actual_steps != expected_steps:
        print(f"❌ FAILED: Expected {expected_steps} steps, got {actual_steps}")
        return False
    print(f"✅ total_steps: {actual_steps}")
    
    print("✅ Pipeline test PASSED")
    return True

def test_genres():
    """Test GET /api/game-factory/genres — 52 genres"""
    print("\n=== Testing Genres ===")
    
    result = test_endpoint("GET", "/game-factory/genres")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify 52 genres
    genres = result.get("genres", [])
    expected_genres = 52
    actual_genres = len(genres) if isinstance(genres, list) else 0
    if actual_genres != expected_genres:
        print(f"❌ FAILED: Expected {expected_genres} genres, got {actual_genres}")
        return False
    print(f"✅ genres: {actual_genres} total")
    
    print("✅ Genres test PASSED")
    return True

def test_competitor_knowledge():
    """Test GET /api/game-factory/competitor/knowledge — Oracle knowledge"""
    print("\n=== Testing Competitor Knowledge ===")
    
    result = test_endpoint("GET", "/game-factory/competitor/knowledge")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify Oracle knowledge exists
    if not isinstance(result, dict):
        print(f"❌ FAILED: Expected dict response, got {type(result)}")
        return False
    
    # Look for Oracle-related content
    result_str = json.dumps(result).lower()
    if "oracle" not in result_str:
        print(f"❌ FAILED: Expected Oracle knowledge content, but 'oracle' not found in response")
        return False
    print(f"✅ Oracle knowledge content found")
    
    print("✅ Competitor Knowledge test PASSED")
    return True

def test_competency_matrices():
    """Test GET /api/game-factory/competency-matrices — 12 dimensions"""
    print("\n=== Testing Competency Matrices ===")
    
    result = test_endpoint("GET", "/game-factory/competency-matrices")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify 12 dimensions
    expected_dimensions = 12
    actual_dimensions = result.get("dimensions", 0)
    if actual_dimensions != expected_dimensions:
        print(f"❌ FAILED: Expected {expected_dimensions} dimensions, got {actual_dimensions}")
        return False
    print(f"✅ dimensions: {actual_dimensions}")
    
    print("✅ Competency Matrices test PASSED")
    return True

def test_knowledge_engine():
    """Test GET /api/game-factory/knowledge-engine — 41+ domains"""
    print("\n=== Testing Knowledge Engine ===")
    
    result = test_endpoint("GET", "/game-factory/knowledge-engine")
    
    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False
    
    # Verify 41+ domains
    min_domains = 41
    actual_domains = result.get("total_knowledge_domains", 0)
    if actual_domains < min_domains:
        print(f"❌ FAILED: Expected >= {min_domains} domains, got {actual_domains}")
        return False
    print(f"✅ total_knowledge_domains: {actual_domains}")
    
    print("✅ Knowledge Engine test PASSED")
    return True

def main():
    """Run all post-refactoring verification tests."""
    print("🧪 Starting Post-Refactoring Verification Tests")
    print("🎯 Testing ALL key endpoints to ensure nothing broke during sub-router extraction")
    print(f"🌐 Base URL: {BASE_URL}")
    
    tests = [
        ("All Agents Summary", test_all_agents_summary),
        ("Hexa Layer", test_hexa_layer),
        ("Quad Layer (Backward Compat)", test_quad_layer),
        ("Angel Class", test_angel_class),
        ("Ghost Society", test_ghost_society),
        ("Parallel Society", test_parallel_society),
        ("Pipeline", test_pipeline),
        ("Genres", test_genres),
        ("Competitor Knowledge", test_competitor_knowledge),
        ("Competency Matrices", test_competency_matrices),
        ("Knowledge Engine", test_knowledge_engine),
    ]
    
    passed = 0
    total = len(tests)
    failed_tests = []
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed_tests.append(test_name)
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {str(e)}")
            failed_tests.append(f"{test_name} (Exception: {str(e)})")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if failed_tests:
        print(f"\n❌ Failed Tests:")
        for failed_test in failed_tests:
            print(f"   - {failed_test}")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - Post-refactoring verification successful!")
        print("✅ All sub-routers (layers, build, competitor) are working correctly")
        return True
    else:
        print("💥 SOME TESTS FAILED - Refactoring may have broken functionality")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)