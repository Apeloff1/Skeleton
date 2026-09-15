#!/usr/bin/env python3
"""
Additional validation tests for specific counts mentioned in review request
"""

import requests
import json

BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"

def test_specific_counts():
    """Test specific counts mentioned in the review request"""
    
    print("🔍 DETAILED VALIDATION TESTING")
    print("=" * 50)
    
    # Test specific endpoints with expected counts
    tests = [
        {
            "endpoint": "/api/enhance/complexity-reference",
            "expected_count": 19,
            "count_field": "entries",
            "description": "Complexity reference (expected 19)"
        },
        {
            "endpoint": "/api/academy/workarounds/categories", 
            "expected_count": 14,
            "count_field": "categories",
            "description": "Workaround categories (expected 14)"
        },
        {
            "endpoint": "/api/academy/workarounds?category=react",
            "expected_count": 8,
            "count_field": "workarounds", 
            "description": "React workarounds (expected 8)"
        },
        {
            "endpoint": "/api/academy/workarounds?category=kubernetes",
            "expected_count": 6,
            "count_field": "workarounds",
            "description": "Kubernetes workarounds (expected 6)"
        },
        {
            "endpoint": "/api/enhance/platform-stats",
            "expected_count": 20000,
            "count_field": "total_documents",
            "description": "Platform stats total documents (expected 20,000+)"
        },
        {
            "endpoint": "/api/academy/bugfix/categories",
            "expected_count": 1900,
            "count_field": "total_bugs", 
            "description": "Total bugfixes (expected 1900+)"
        }
    ]
    
    for test in tests:
        print(f"\nTesting: {test['description']}")
        
        try:
            response = requests.get(f"{BACKEND_URL}{test['endpoint']}", timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if test['count_field'] == "categories":
                    actual_count = len(data.get("categories", []))
                elif test['count_field'] == "workarounds":
                    actual_count = len(data.get("workarounds", []))
                elif test['count_field'] == "entries":
                    actual_count = len(data.get("entries", []))
                else:
                    actual_count = data.get(test['count_field'], 0)
                
                print(f"  Expected: {test['expected_count']}")
                print(f"  Actual: {actual_count}")
                
                if test['count_field'] == "total_documents" and actual_count >= test['expected_count']:
                    print(f"  ✅ PASS: {actual_count} >= {test['expected_count']}")
                elif test['count_field'] == "total_bugs" and actual_count >= test['expected_count']:
                    print(f"  ✅ PASS: {actual_count} >= {test['expected_count']}")
                elif actual_count == test['expected_count']:
                    print(f"  ✅ PASS: Exact match")
                else:
                    print(f"  ⚠️  MISMATCH: Expected {test['expected_count']}, got {actual_count}")
                    
                # Print sample data for debugging
                if isinstance(data, dict) and len(str(data)) < 500:
                    print(f"  Sample data: {json.dumps(data, indent=2)[:200]}...")
                    
            else:
                print(f"  ❌ FAILED: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)}")

if __name__ == "__main__":
    test_specific_counts()