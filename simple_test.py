#!/usr/bin/env python3
"""
Simple Jeeves AAA Game Builder v23.0 Test
"""

import requests
import json

BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

def test_simple():
    print("🚀 Testing Jeeves AAA Game Builder v23.0 Endpoints")
    
    # Test 1: Genres
    print("\n1. Testing GET /api/jeeves-build/genres")
    try:
        response = requests.get(f"{API_BASE}/jeeves-build/genres", timeout=10)
        if response.status_code == 200:
            data = response.json()
            genres = data.get("genres", [])
            print(f"✅ SUCCESS: Found {len(genres)} genres")
            if len(genres) == 11:
                print("✅ Correct count: 11 genres")
            else:
                print(f"❌ Expected 11 genres, got {len(genres)}")
        else:
            print(f"❌ FAILED: Status {response.status_code}")
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Test 2: Phases
    print("\n2. Testing GET /api/jeeves-build/phases")
    try:
        response = requests.get(f"{API_BASE}/jeeves-build/phases", timeout=10)
        if response.status_code == 200:
            data = response.json()
            phases = data.get("phases", [])
            total_steps = data.get("total_steps", 0)
            print(f"✅ SUCCESS: Found {len(phases)} phases, {total_steps} total steps")
            if len(phases) == 7 and total_steps == 200:
                print("✅ Correct structure: 7 phases, 200 steps")
            else:
                print(f"❌ Expected 7 phases and 200 steps, got {len(phases)} phases and {total_steps} steps")
        else:
            print(f"❌ FAILED: Status {response.status_code}")
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Test 3: Create Project
    print("\n3. Testing POST /api/jeeves-build/create")
    project_id = None
    try:
        create_data = {
            "description": "An open-world RPG where you play as a shapeshifting mage",
            "genre": "action_rpg",
            "quality_tier": "aaa"
        }
        response = requests.post(f"{API_BASE}/jeeves-build/create", json=create_data, timeout=30)
        if response.status_code == 200:
            data = response.json()
            project_id = data.get("project_id")
            status = data.get("status")
            gdd = data.get("gdd")
            aaa_doctrine = data.get("aaa_doctrine_enforced")
            print(f"✅ SUCCESS: Created project {project_id}")
            print(f"   Status: {status}, GDD: {'present' if gdd else 'missing'}, AAA: {aaa_doctrine}")
            
            if project_id and project_id.startswith("aaa-"):
                print("✅ Project ID format correct")
            else:
                print(f"❌ Project ID should start with 'aaa-', got {project_id}")
        else:
            print(f"❌ FAILED: Status {response.status_code}")
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Test 4: Health (regression)
    print("\n4. Testing GET /api/health (regression)")
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            print(f"✅ SUCCESS: Health status = {status}")
        else:
            print(f"❌ FAILED: Status {response.status_code}")
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Test 5: Quantum Factory (regression)
    print("\n5. Testing GET /api/quantum-factory/status (regression)")
    try:
        response = requests.get(f"{API_BASE}/quantum-factory/status", timeout=10)
        if response.status_code == 200:
            data = response.json()
            domains = data.get("domains", [])
            print(f"✅ SUCCESS: Found {len(domains)} domains")
            if len(domains) == 7:
                total_specialists = 0
                for domain in domains:
                    specialists = domain.get("specialists", [])
                    total_specialists += len(specialists)
                print(f"   Total specialists: {total_specialists}")
                if total_specialists == 56:
                    print("✅ Correct: 7 domains, 56 specialists")
                else:
                    print(f"❌ Expected 56 specialists, got {total_specialists}")
            else:
                print(f"❌ Expected 7 domains, got {len(domains)}")
        else:
            print(f"❌ FAILED: Status {response.status_code}")
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    print("\n🎯 Basic endpoint testing complete")
    return project_id

if __name__ == "__main__":
    test_simple()