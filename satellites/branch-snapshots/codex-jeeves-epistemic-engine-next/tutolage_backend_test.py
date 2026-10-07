#!/usr/bin/env python3
"""
Tutolage Platform Backend API Testing
Tests the specific endpoints mentioned in the review request:

1. Code Playground — All 7 Languages
2. Achievements Catalog (9,968 entries)
3. Offline Sync Endpoints
4. Core Academy Endpoints (regression)
5. Edge Cases
"""

import requests
import json
import time
from typing import Dict, Any, List

# Backend URL from the review request
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

class TutolageAPITester:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
        
    def log_result(self, test_name: str, passed: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({
            "test": test_name,
            "status": status,
            "passed": passed,
            "details": details,
            "response_data": response_data
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        print(f"{status} {test_name}: {details}")
        
    def test_endpoint(self, method: str, endpoint: str, expected_status: int = 200, 
                     data: Dict = None, test_name: str = None, 
                     validation_func=None) -> Dict:
        """Generic endpoint tester"""
        if not test_name:
            test_name = f"{method} {endpoint}"
            
        try:
            url = f"{API_BASE}{endpoint}"
            
            if method.upper() == "GET":
                response = requests.get(url, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, json=data, timeout=30)
            else:
                self.log_result(test_name, False, f"Unsupported method: {method}")
                return {}
                
            # Check status code
            if response.status_code != expected_status:
                self.log_result(test_name, False, 
                              f"Expected status {expected_status}, got {response.status_code}. Response: {response.text[:200]}")
                return {}
                
            # Parse JSON response
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                self.log_result(test_name, False, f"Invalid JSON response. Response: {response.text[:200]}")
                return {}
                
            # Run custom validation if provided
            if validation_func:
                validation_result = validation_func(response_data)
                if not validation_result[0]:
                    self.log_result(test_name, False, validation_result[1], response_data)
                    return response_data
                    
            self.log_result(test_name, True, "Endpoint working correctly", response_data)
            return response_data
            
        except requests.exceptions.Timeout:
            self.log_result(test_name, False, "Request timeout (30s)")
            return {}
        except requests.exceptions.ConnectionError:
            self.log_result(test_name, False, "Connection error")
            return {}
        except Exception as e:
            self.log_result(test_name, False, f"Unexpected error: {str(e)}")
            return {}

    def test_code_playground_all_languages(self):
        """Test Code Playground with all 7 languages"""
        print("\n🎮 TESTING CODE PLAYGROUND - ALL 7 LANGUAGES")
        print("=" * 60)
        
        # Test cases for each language
        language_tests = [
            {
                "language": "python",
                "code": "print('Hello Python!')",
                "expected_output": "Hello Python!"
            },
            {
                "language": "javascript", 
                "code": "console.log('Hello JS!')",
                "expected_output": "Hello JS!"
            },
            {
                "language": "typescript",
                "code": "console.log('Hello TS!')",
                "expected_output": "Hello TS!"
            },
            {
                "language": "go",
                "code": 'package main\nimport "fmt"\nfunc main() { fmt.Println("Hello Go!") }',
                "expected_output": "Hello Go!"
            },
            {
                "language": "rust",
                "code": 'fn main() { println!("Hello Rust!"); }',
                "expected_output": "Hello Rust!"
            },
            {
                "language": "c",
                "code": '#include <stdio.h>\nint main() { printf("Hello C!\\n"); return 0; }',
                "expected_output": "Hello C!"
            },
            {
                "language": "cpp",
                "code": '#include <iostream>\nusing namespace std;\nint main() { cout << "Hello C++!" << endl; return 0; }',
                "expected_output": "Hello C++!"
            }
        ]
        
        for test_case in language_tests:
            lang = test_case["language"]
            code = test_case["code"]
            expected = test_case["expected_output"]
            
            response = self.test_endpoint(
                "POST", "/playground/run",
                data={"language": lang, "code": code},
                test_name=f"Code Playground - {lang.upper()} execution",
                validation_func=lambda r, exp=expected: (
                    "output" in r and exp in str(r.get("output", "")) and r.get("exit_code") == 0,
                    f"Expected output '{exp}' with exit_code 0, got output: '{r.get('output', 'No output')}', exit_code: {r.get('exit_code', 'No exit_code')}"
                )
            )
        
        # Test GET /api/playground/languages
        response = self.test_endpoint(
            "GET", "/playground/languages",
            test_name="Code Playground - Languages list (should return 7)",
            validation_func=lambda r: (
                "languages" in r and len(r["languages"]) == 7,
                f"Expected 7 languages, got: {len(r.get('languages', []))} languages: {r.get('languages', [])}"
            )
        )

    def test_achievements_catalog(self):
        """Test Achievements Catalog (9,968 entries)"""
        print("\n🏆 TESTING ACHIEVEMENTS CATALOG (9,968 ENTRIES)")
        print("=" * 60)
        
        # Test a) GET /api/academy/achievements/stats
        response = self.test_endpoint(
            "GET", "/academy/achievements/stats",
            test_name="Achievements - Statistics (verify total >= 9000)",
            validation_func=lambda r: (
                "total" in r and r["total"] >= 9000,
                f"Expected total >= 9000, got: {r.get('total', 0)}"
            )
        )
        
        # Test b) GET /api/academy/achievements?limit=5&skip=0
        response = self.test_endpoint(
            "GET", "/academy/achievements?limit=5&skip=0",
            test_name="Achievements - List with limit=5 (verify returns 5 items)",
            validation_func=lambda r: (
                "achievements" in r and len(r["achievements"]) == 5,
                f"Expected 5 achievements, got: {len(r.get('achievements', []))}"
            )
        )
        
        # Test c) GET /api/academy/achievements?rarity=legendary&limit=3
        response = self.test_endpoint(
            "GET", "/academy/achievements?rarity=legendary&limit=3",
            test_name="Achievements - Filter by rarity=legendary (verify all legendary)",
            validation_func=lambda r: (
                "achievements" in r and all(item.get("rarity") == "legendary" for item in r["achievements"]),
                f"Expected all legendary items, got rarities: {[item.get('rarity') for item in r.get('achievements', [])]}"
            )
        )
        
        # Test d) GET /api/academy/achievements?category=quiz&limit=3
        response = self.test_endpoint(
            "GET", "/academy/achievements?category=quiz&limit=3",
            test_name="Achievements - Filter by category=quiz (verify all quiz)",
            validation_func=lambda r: (
                "achievements" in r and all(item.get("category") == "quiz" for item in r["achievements"]),
                f"Expected all quiz items, got categories: {[item.get('category') for item in r.get('achievements', [])]}"
            )
        )
        
        # Test e) GET /api/academy/achievements?limit=50&skip=100
        response = self.test_endpoint(
            "GET", "/academy/achievements?limit=50&skip=100",
            test_name="Achievements - Pagination (skip=100, verify pagination works)",
            validation_func=lambda r: (
                "achievements" in r and len(r["achievements"]) <= 50,
                f"Expected max 50 achievements with skip=100, got: {len(r.get('achievements', []))}"
            )
        )

    def test_offline_sync_endpoints(self):
        """Test Offline Sync Endpoints"""
        print("\n📱 TESTING OFFLINE SYNC ENDPOINTS")
        print("=" * 60)
        
        # Test a) GET /api/academy/offline/manifest
        response = self.test_endpoint(
            "GET", "/academy/offline/manifest",
            test_name="Offline Sync - Manifest (verify collections with counts > 0)",
            validation_func=lambda r: (
                "collections" in r and all(count > 0 for count in r["collections"].values()),
                f"Expected collections with counts > 0, got: {r.get('collections', {})}"
            )
        )
        
        # Test b) GET /api/academy/offline/dump/achievements_catalog?limit=10&skip=0
        response = self.test_endpoint(
            "GET", "/academy/offline/dump/achievements_catalog?limit=10&skip=0",
            test_name="Offline Sync - Achievements dump (verify returns documents array)",
            validation_func=lambda r: (
                "documents" in r and isinstance(r["documents"], list),
                f"Expected documents array, got: {type(r.get('documents', 'No documents'))}"
            )
        )

    def test_core_academy_endpoints(self):
        """Test Core Academy Endpoints (regression)"""
        print("\n🎓 TESTING CORE ACADEMY ENDPOINTS (REGRESSION)")
        print("=" * 60)
        
        # Test a) GET /api/academy/stats
        response = self.test_endpoint(
            "GET", "/academy/stats",
            test_name="Academy - Statistics (verify returns total content counts)",
            validation_func=lambda r: (
                any(key in r for key in ["total_content", "total_items", "content_count"]),
                f"Expected content count fields, got keys: {list(r.keys())}"
            )
        )
        
        # Test b) GET /api/academy/quizzes/domains
        response = self.test_endpoint(
            "GET", "/academy/quizzes/domains",
            test_name="Academy - Quiz domains (verify returns quiz domains)",
            validation_func=lambda r: (
                "domains" in r or "quiz_domains" in r,
                f"Expected domains field, got keys: {list(r.keys())}"
            )
        )
        
        # Test c) GET /api/academy/reading-library
        response = self.test_endpoint(
            "GET", "/academy/reading-library",
            test_name="Academy - Reading library (verify returns books)",
            validation_func=lambda r: (
                "books" in r or "library" in r or "reading_materials" in r,
                f"Expected books/library field, got keys: {list(r.keys())}"
            )
        )
        
        # Test d) GET /api/academy/study-paths
        response = self.test_endpoint(
            "GET", "/academy/study-paths",
            test_name="Academy - Study paths (verify returns paths)",
            validation_func=lambda r: (
                "paths" in r or "study_paths" in r,
                f"Expected paths field, got keys: {list(r.keys())}"
            )
        )
        
        # Test e) GET /api/academy/bugfix/categories
        response = self.test_endpoint(
            "GET", "/academy/bugfix/categories",
            test_name="Academy - Bugfix categories (verify returns categories)",
            validation_func=lambda r: (
                "categories" in r,
                f"Expected categories field, got keys: {list(r.keys())}"
            )
        )

    def test_edge_cases(self):
        """Test Edge Cases"""
        print("\n⚠️  TESTING EDGE CASES")
        print("=" * 60)
        
        # Test a) POST /api/playground/run with unsupported language
        response = self.test_endpoint(
            "POST", "/playground/run",
            data={"language": "brainfuck", "code": "test"},
            expected_status=400,  # Expect error
            test_name="Edge Case - Unsupported language (brainfuck)",
            validation_func=lambda r: (
                "error" in r or "message" in r,
                f"Expected error message for unsupported language, got: {r}"
            )
        )
        
        # Test b) POST /api/playground/run with code > 10000 chars
        long_code = "print('x')\n" * 5000  # Create very long code
        response = self.test_endpoint(
            "POST", "/playground/run",
            data={"language": "python", "code": long_code},
            expected_status=400,  # Expect error
            test_name="Edge Case - Code too long (>10000 chars)",
            validation_func=lambda r: (
                "error" in r and ("length" in str(r.get("error", "")).lower() or "max" in str(r.get("error", "")).lower()),
                f"Expected max length error, got: {r.get('error', 'No error')}"
            )
        )
        
        # Test c) GET /api/academy/achievements?rarity=invalid
        response = self.test_endpoint(
            "GET", "/academy/achievements?rarity=invalid",
            test_name="Edge Case - Invalid rarity filter (expect 0 results)",
            validation_func=lambda r: (
                "achievements" in r and len(r["achievements"]) == 0,
                f"Expected 0 results for invalid rarity, got: {len(r.get('achievements', []))}"
            )
        )

    def run_all_tests(self):
        """Run all test suites"""
        print("🚀 STARTING TUTOLAGE PLATFORM BACKEND API TESTING")
        print(f"Backend URL: {BACKEND_URL}")
        print("=" * 70)
        
        start_time = time.time()
        
        # Run test suites
        self.test_code_playground_all_languages()
        self.test_achievements_catalog()
        self.test_offline_sync_endpoints()
        self.test_core_academy_endpoints()
        self.test_edge_cases()
        
        # Print summary
        end_time = time.time()
        duration = end_time - start_time
        
        print("\n" + "=" * 70)
        print("📊 TUTOLAGE BACKEND API TEST SUMMARY")
        print("=" * 70)
        print(f"Total Tests: {self.passed + self.failed}")
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"⏱️  Duration: {duration:.2f}s")
        print(f"📈 Success Rate: {(self.passed/(self.passed + self.failed)*100):.1f}%")
        
        if self.failed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.results:
                if not result["passed"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        print("\n🎯 CRITICAL FINDINGS:")
        critical_issues = []
        working_features = []
        
        for result in self.results:
            if not result["passed"]:
                critical_issues.append(f"❌ {result['test']}: {result['details']}")
            else:
                working_features.append(f"✅ {result['test']}")
        
        if critical_issues:
            print("FAILED ENDPOINTS:")
            for issue in critical_issues:
                print(f"  {issue}")
        
        if working_features:
            print("\nWORKING ENDPOINTS:")
            for feature in working_features[:5]:  # Show first 5
                print(f"  {feature}")
            if len(working_features) > 5:
                print(f"  ... and {len(working_features) - 5} more")
        
        return self.passed, self.failed

if __name__ == "__main__":
    tester = TutolageAPITester()
    passed, failed = tester.run_all_tests()
    
    # Exit with appropriate code
    exit(0 if failed == 0 else 1)