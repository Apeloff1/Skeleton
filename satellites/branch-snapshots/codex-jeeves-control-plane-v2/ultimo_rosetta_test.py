#!/usr/bin/env python3
"""
Backend API Testing for ULTIMO Rosetta Stone Review Request
Testing all endpoints mentioned in the specific review request at:
https://gemini-game-craft.preview.emergentagent.com

Review Request Requirements:
1. Scale Verification - total_entries >= 6000, concepts count = 15, each concept has ~453 languages
2. Code Quality - verify specific language entries have real handcrafted code
3. All 15 Concepts - verify all concept endpoints exist and work
4. Regression - verify academy achievements (9968) and languages academy (451)
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"

class UltimoRosettaTester:
    def __init__(self):
        self.backend_url = BACKEND_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'UltimoRosettaTester/1.0'
        })
        self.results = []
        
    def log_result(self, test_name: str, success: bool, details: str, data: Any = None):
        """Log test result"""
        result = {
            'test': test_name,
            'success': success,
            'details': details,
            'data': data
        }
        self.results.append(result)
        status = "✅" if success else "❌"
        print(f"{status} {test_name}: {details}")
        
    def make_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> tuple:
        """Make HTTP request and return (success, response_data, status_code)"""
        try:
            url = f"{self.backend_url}{endpoint}"
            
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=30)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data, params=params, timeout=30)
            else:
                return False, f"Unsupported method: {method}", 0
                
            if response.status_code == 200:
                try:
                    return True, response.json(), response.status_code
                except json.JSONDecodeError:
                    return False, f"Invalid JSON response: {response.text[:200]}", response.status_code
            else:
                return False, f"HTTP {response.status_code}: {response.text[:200]}", response.status_code
                
        except requests.exceptions.Timeout:
            return False, "Request timeout (30s)", 0
        except requests.exceptions.ConnectionError:
            return False, "Connection error", 0
        except Exception as e:
            return False, f"Request error: {str(e)}", 0

    # ========================================================================
    # 1. SCALE VERIFICATION TESTS
    # ========================================================================
    
    def test_scale_concepts_overview(self):
        """Test GET /api/dictionary/rosetta/concepts - verify total_entries >= 6000, concepts count = 15"""
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta/concepts')
        
        if not success:
            self.log_result("Scale: Concepts Overview", False, f"Request failed: {data}")
            return
            
        if not isinstance(data, dict):
            self.log_result("Scale: Concepts Overview", False, f"Expected dict response, got: {type(data)}")
            return
            
        total_entries = data.get('total_entries', 0)
        concepts = data.get('concepts', [])
        concepts_count = len(concepts)
        
        # Check requirements: total_entries >= 6000, concepts count = 15
        if total_entries >= 6000 and concepts_count == 15:
            # Check if each concept has ~453 languages (6000/15 ≈ 400, allow range 350-550)
            avg_per_concept = total_entries / concepts_count if concepts_count > 0 else 0
            if 350 <= avg_per_concept <= 550:
                self.log_result("Scale: Concepts Overview", True, 
                               f"PERFECT: {concepts_count} concepts, {total_entries} total entries (~{avg_per_concept:.0f} per concept)")
            else:
                self.log_result("Scale: Concepts Overview", False, 
                               f"Concepts count OK ({concepts_count}), total entries OK ({total_entries}), but avg per concept {avg_per_concept:.0f} not ~453")
        else:
            self.log_result("Scale: Concepts Overview", False, 
                           f"Expected 15 concepts and >=6000 entries, got {concepts_count} concepts and {total_entries} entries")

    def test_scale_language_brainfuck(self):
        """Test GET /api/dictionary/rosetta?language=Brainfuck&limit=15 - verify 15 entries for esoteric language"""
        params = {'language': 'Brainfuck', 'limit': 15}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Scale: Brainfuck Language", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        brainfuck_entries = [e for e in entries if e.get('language', '').lower() == 'brainfuck']
        
        if len(brainfuck_entries) == 15:
            self.log_result("Scale: Brainfuck Language", True, 
                           f"Found exactly 15 Brainfuck entries as expected")
        else:
            self.log_result("Scale: Brainfuck Language", False, 
                           f"Expected 15 Brainfuck entries, got {len(brainfuck_entries)}")

    def test_scale_language_cobol(self):
        """Test GET /api/dictionary/rosetta?language=COBOL&limit=15 - verify 15 entries for historic language"""
        params = {'language': 'COBOL', 'limit': 15}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Scale: COBOL Language", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        cobol_entries = [e for e in entries if e.get('language', '').lower() == 'cobol']
        
        if len(cobol_entries) == 15:
            self.log_result("Scale: COBOL Language", True, 
                           f"Found exactly 15 COBOL entries as expected")
        else:
            self.log_result("Scale: COBOL Language", False, 
                           f"Expected 15 COBOL entries, got {len(cobol_entries)}")

    def test_scale_language_mojo(self):
        """Test GET /api/dictionary/rosetta?language=Mojo&limit=15 - verify 15 entries for emerging language"""
        params = {'language': 'Mojo', 'limit': 15}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Scale: Mojo Language", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        mojo_entries = [e for e in entries if e.get('language', '').lower() == 'mojo']
        
        if len(mojo_entries) == 15:
            self.log_result("Scale: Mojo Language", True, 
                           f"Found exactly 15 Mojo entries as expected")
        else:
            self.log_result("Scale: Mojo Language", False, 
                           f"Expected 15 Mojo entries, got {len(mojo_entries)}")

    def test_scale_language_solidity(self):
        """Test GET /api/dictionary/rosetta?language=Solidity&limit=15 - verify entries for blockchain language"""
        params = {'language': 'Solidity', 'limit': 15}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Scale: Solidity Language", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        solidity_entries = [e for e in entries if e.get('language', '').lower() == 'solidity']
        
        if len(solidity_entries) > 0:
            self.log_result("Scale: Solidity Language", True, 
                           f"Found {len(solidity_entries)} Solidity entries for blockchain language")
        else:
            self.log_result("Scale: Solidity Language", False, 
                           "No Solidity entries found for blockchain language")

    # ========================================================================
    # 2. CODE QUALITY TESTS
    # ========================================================================
    
    def test_quality_closures_haskell(self):
        """Test GET /api/dictionary/rosetta/closures - verify Haskell entry has source=handcrafted with real code"""
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta/closures')
        
        if not success:
            self.log_result("Quality: Closures Haskell", False, f"Request failed: {data}")
            return
            
        languages = data.get('languages', [])
        haskell_entry = None
        
        for entry in languages:
            if entry.get('language', '').lower() == 'haskell':
                haskell_entry = entry
                break
                
        if not haskell_entry:
            self.log_result("Quality: Closures Haskell", False, "No Haskell entry found in closures")
            return
            
        source = haskell_entry.get('source', '')
        code = haskell_entry.get('code', '')
        
        if source == 'handcrafted' and len(code.strip()) > 20:
            self.log_result("Quality: Closures Haskell", True, 
                           f"Haskell entry has source=handcrafted with real code ({len(code)} chars)")
        else:
            self.log_result("Quality: Closures Haskell", False, 
                           f"Haskell entry source='{source}', code length={len(code)} (expected handcrafted with real code)")

    def test_quality_error_handling_go(self):
        """Test GET /api/dictionary/rosetta/error_handling - verify Go entry has real error handling code"""
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta/error_handling')
        
        if not success:
            self.log_result("Quality: Error Handling Go", False, f"Request failed: {data}")
            return
            
        languages = data.get('languages', [])
        go_entry = None
        
        for entry in languages:
            if entry.get('language', '').lower() == 'go':
                go_entry = entry
                break
                
        if not go_entry:
            self.log_result("Quality: Error Handling Go", False, "No Go entry found in error_handling")
            return
            
        code = go_entry.get('code', '')
        
        # Check for Go error handling patterns
        if ('err' in code.lower() and ('if err != nil' in code or 'error' in code.lower())) and len(code.strip()) > 30:
            self.log_result("Quality: Error Handling Go", True, 
                           f"Go entry has real error handling code with 'err' patterns ({len(code)} chars)")
        else:
            self.log_result("Quality: Error Handling Go", False, 
                           f"Go entry doesn't have proper error handling patterns, code length={len(code)}")

    def test_quality_pattern_matching_rust(self):
        """Test GET /api/dictionary/rosetta/pattern_matching - verify Rust entry has real match expressions"""
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta/pattern_matching')
        
        if not success:
            self.log_result("Quality: Pattern Matching Rust", False, f"Request failed: {data}")
            return
            
        languages = data.get('languages', [])
        rust_entry = None
        
        for entry in languages:
            if entry.get('language', '').lower() == 'rust':
                rust_entry = entry
                break
                
        if not rust_entry:
            self.log_result("Quality: Pattern Matching Rust", False, "No Rust entry found in pattern_matching")
            return
            
        code = rust_entry.get('code', '')
        
        # Check for Rust match expressions
        if 'match' in code and ('=>' in code or 'Some(' in code or 'None' in code) and len(code.strip()) > 30:
            self.log_result("Quality: Pattern Matching Rust", True, 
                           f"Rust entry has real match expressions ({len(code)} chars)")
        else:
            self.log_result("Quality: Pattern Matching Rust", False, 
                           f"Rust entry doesn't have proper match expressions, code length={len(code)}")

    def test_quality_async_await_python(self):
        """Test GET /api/dictionary/rosetta/concurrency - verify Python entry has asyncio code"""
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta/concurrency')
        
        if not success:
            self.log_result("Quality: Async/Await Python", False, f"Request failed: {data}")
            return
            
        languages = data.get('languages', [])
        python_entry = None
        
        for entry in languages:
            if entry.get('language', '').lower() == 'python':
                python_entry = entry
                break
                
        if not python_entry:
            self.log_result("Quality: Async/Await Python", False, "No Python entry found in concurrency")
            return
            
        code = python_entry.get('code', '')
        
        # Check for Python asyncio patterns
        if ('async' in code and 'await' in code) or 'asyncio' in code and len(code.strip()) > 30:
            self.log_result("Quality: Async/Await Python", True, 
                           f"Python entry has asyncio code with async/await patterns ({len(code)} chars)")
        else:
            self.log_result("Quality: Async/Await Python", False, 
                           f"Python entry doesn't have proper asyncio patterns, code length={len(code)}")

    # ========================================================================
    # 3. ALL 15 CONCEPTS TESTS
    # ========================================================================
    
    def test_concept_endpoint(self, concept: str):
        """Test specific concept endpoint exists and returns data"""
        success, data, status = self.make_request('GET', f'/api/dictionary/rosetta/{concept}')
        
        if not success:
            self.log_result(f"Concept: {concept.title()}", False, f"Request failed: {data}")
            return
            
        languages = data.get('languages', [])
        
        if len(languages) > 0:
            self.log_result(f"Concept: {concept.title()}", True, 
                           f"Found {len(languages)} language entries")
        else:
            self.log_result(f"Concept: {concept.title()}", False, 
                           "No language entries found")

    # ========================================================================
    # 4. REGRESSION TESTS
    # ========================================================================
    
    def test_regression_academy_achievements(self):
        """Test GET /api/academy/achievements/stats - verify 9968"""
        success, data, status = self.make_request('GET', '/api/academy/achievements/stats')
        
        if not success:
            self.log_result("Regression: Academy Achievements", False, f"Request failed: {data}")
            return
            
        total = data.get('total', 0)
        
        if total == 9968:
            self.log_result("Regression: Academy Achievements", True, 
                           f"Exactly 9968 achievements found (PERFECT)")
        else:
            self.log_result("Regression: Academy Achievements", False, 
                           f"Expected 9968 achievements, got {total}")

    def test_regression_languages_academy(self):
        """Test GET /api/languages-academy/stats - verify 451"""
        success, data, status = self.make_request('GET', '/api/languages-academy/stats')
        
        if not success:
            self.log_result("Regression: Languages Academy", False, f"Request failed: {data}")
            return
            
        total = data.get('total', 0)
        
        if total == 451:
            self.log_result("Regression: Languages Academy", True, 
                           f"Exactly 451 languages found (PERFECT)")
        else:
            self.log_result("Regression: Languages Academy", False, 
                           f"Expected 451 languages, got {total}")

    def run_all_tests(self):
        """Run all tests from the ULTIMO Rosetta Stone review request"""
        print("🎯 ULTIMO ROSETTA STONE REVIEW REQUEST TESTING")
        print("=" * 70)
        
        # 1. Scale Verification Tests
        print("\n📏 1. SCALE VERIFICATION TESTS:")
        self.test_scale_concepts_overview()
        self.test_scale_language_brainfuck()
        self.test_scale_language_cobol()
        self.test_scale_language_mojo()
        self.test_scale_language_solidity()
        
        # 2. Code Quality Tests
        print("\n🔍 2. CODE QUALITY TESTS:")
        self.test_quality_closures_haskell()
        self.test_quality_error_handling_go()
        self.test_quality_pattern_matching_rust()
        self.test_quality_async_await_python()
        
        # 3. All 15 Concepts Tests
        print("\n📚 3. ALL 15 CONCEPTS TESTS:")
        concepts = [
            'variables', 'functions', 'loops', 'structs', 'io', 
            'generics', 'testing', 'modules', 'closures', 'error_handling',
            'pattern_matching', 'concurrency', 'arrays', 'strings', 'conditionals'
        ]
        
        for concept in concepts:
            self.test_concept_endpoint(concept)
        
        # 4. Regression Tests
        print("\n🔄 4. REGRESSION TESTS:")
        self.test_regression_academy_achievements()
        self.test_regression_languages_academy()
        
        # Summary
        print("\n" + "=" * 70)
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"📊 FINAL RESULTS: {passed_tests}/{total_tests} TESTS PASSED ({(passed_tests/total_tests)*100:.1f}% SUCCESS RATE)")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS ({failed_tests}):")
            for result in self.results:
                if not result['success']:
                    print(f"   • {result['test']}: {result['details']}")
        
        print(f"\n🏆 ULTIMO ROSETTA STONE TESTING COMPLETE")
        return passed_tests == total_tests

if __name__ == "__main__":
    tester = UltimoRosettaTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)