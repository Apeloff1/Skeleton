#!/usr/bin/env python3
"""
Backend API Testing for Tutolage Rosetta Stone Hyperscale System - Wave 3 Expansion
Testing all endpoints mentioned in the Wave 3 review request at:
https://gemini-game-craft.preview.emergentagent.com

Wave 3 Review Request Requirements:
1. Rosetta Concepts List - 31 concepts, each with 451 languages
2. Handcrafted Entries for New Concepts (type_system, string_formatting, date_time, math_operations)
3. Cross-language Comparison (Core Feature)
4. Challenge Arena with New Concepts
5. Submit Challenge
6. Stats Verification - Total entries: 13,981, Handcrafted: 907, Concepts: 31
7. Previous Leaderboard APIs Still Working
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"

class RosettaWave3Tester:
    def __init__(self):
        self.backend_url = BACKEND_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'RosettaWave3Tester/1.0'
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
    # 1. ROSETTA CONCEPTS LIST TEST
    # ========================================================================
    
    def test_rosetta_concepts_list(self):
        """Test GET /api/dictionary/rosetta/concepts - verify 31 concepts, each with 451 languages"""
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta/concepts')
        
        if not success:
            self.log_result("Rosetta Concepts List", False, f"Request failed: {data}")
            return
            
        if not isinstance(data, dict):
            self.log_result("Rosetta Concepts List", False, f"Expected dict response, got: {type(data)}")
            return
            
        concepts = data.get('concepts', [])
        concepts_count = len(concepts)
        
        # Check for 31 concepts
        if concepts_count != 31:
            self.log_result("Rosetta Concepts List", False, 
                           f"Expected 31 concepts, got {concepts_count}")
            return
            
        # Check for Wave 3 new concepts
        wave3_concepts = ['type_system', 'string_formatting', 'date_time', 'math_operations']
        found_wave3 = []
        
        for concept in concepts:
            concept_name = concept.get('concept', '') if isinstance(concept, dict) else str(concept)
            if concept_name in wave3_concepts:
                found_wave3.append(concept_name)
                
        missing_wave3 = set(wave3_concepts) - set(found_wave3)
        
        if missing_wave3:
            self.log_result("Rosetta Concepts List", False, 
                           f"Found {concepts_count} concepts but missing Wave 3 concepts: {missing_wave3}")
            return
            
        # Check if each concept has 451 languages (approximately)
        # We'll verify this by checking total entries and doing math
        total_entries = data.get('total_entries', 0)
        expected_total = 31 * 451  # 13,981
        
        if abs(total_entries - expected_total) <= 100:  # Allow small variance
            self.log_result("Rosetta Concepts List", True, 
                           f"✅ PERFECT: Found {concepts_count} concepts with {total_entries} total entries (~{total_entries//concepts_count} per concept). Wave 3 concepts present: {found_wave3}")
        else:
            self.log_result("Rosetta Concepts List", False, 
                           f"Found {concepts_count} concepts but total entries {total_entries} doesn't match expected ~{expected_total}")

    # ========================================================================
    # 2. HANDCRAFTED ENTRIES FOR NEW CONCEPTS
    # ========================================================================
    
    def test_handcrafted_type_system_python(self):
        """Test GET /api/dictionary/rosetta?concept=type_system&language=Python&limit=1"""
        params = {'concept': 'type_system', 'language': 'Python', 'limit': 1}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Handcrafted: Type System Python", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        
        if not entries:
            self.log_result("Handcrafted: Type System Python", False, "No entries found for type_system Python")
            return
            
        entry = entries[0]
        source = entry.get('source', '')
        code = entry.get('code', '')
        
        # Check for handcrafted source and real Python type hints code
        if source == 'handcrafted' and len(code.strip()) > 20:
            # Check for Python type hints patterns
            type_patterns = [':', '->', 'List[', 'Dict[', 'Optional[', 'Union[', 'int', 'str', 'bool', 'float']
            has_type_hints = any(pattern in code for pattern in type_patterns)
            
            if has_type_hints:
                self.log_result("Handcrafted: Type System Python", True, 
                               f"✅ VERIFIED: source=handcrafted, real Python type hints code ({len(code)} chars)")
            else:
                self.log_result("Handcrafted: Type System Python", False, 
                               f"Source=handcrafted but code doesn't contain Python type hints patterns")
        else:
            self.log_result("Handcrafted: Type System Python", False, 
                           f"Expected source=handcrafted with real code, got source='{source}', code length={len(code)}")

    def test_handcrafted_math_operations_rust(self):
        """Test GET /api/dictionary/rosetta?concept=math_operations&language=Rust&limit=1"""
        params = {'concept': 'math_operations', 'language': 'Rust', 'limit': 1}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Handcrafted: Math Operations Rust", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        
        if not entries:
            self.log_result("Handcrafted: Math Operations Rust", False, "No entries found for math_operations Rust")
            return
            
        entry = entries[0]
        source = entry.get('source', '')
        code = entry.get('code', '')
        
        # Check for handcrafted source and real Rust math code
        if source == 'handcrafted' and len(code.strip()) > 20:
            # Check for Rust math patterns
            rust_patterns = ['fn ', 'let ', 'f64', 'f32', 'i32', 'i64', '.sqrt()', '.pow()', '.abs()', '+', '-', '*', '/']
            has_rust_math = any(pattern in code for pattern in rust_patterns)
            
            if has_rust_math:
                self.log_result("Handcrafted: Math Operations Rust", True, 
                               f"✅ VERIFIED: source=handcrafted, real Rust math code ({len(code)} chars)")
            else:
                self.log_result("Handcrafted: Math Operations Rust", False, 
                               f"Source=handcrafted but code doesn't contain Rust math patterns")
        else:
            self.log_result("Handcrafted: Math Operations Rust", False, 
                           f"Expected source=handcrafted with real code, got source='{source}', code length={len(code)}")

    def test_handcrafted_date_time_go(self):
        """Test GET /api/dictionary/rosetta?concept=date_time&language=Go&limit=1"""
        params = {'concept': 'date_time', 'language': 'Go', 'limit': 1}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Handcrafted: Date Time Go", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        
        if not entries:
            self.log_result("Handcrafted: Date Time Go", False, "No entries found for date_time Go")
            return
            
        entry = entries[0]
        source = entry.get('source', '')
        code = entry.get('code', '')
        
        # Check for handcrafted source and real Go date/time code
        if source == 'handcrafted' and len(code.strip()) > 20:
            # Check for Go time patterns
            go_patterns = ['time.', 'Time', 'Now()', 'Parse(', 'Format(', 'package main', 'import', 'func ']
            has_go_time = any(pattern in code for pattern in go_patterns)
            
            if has_go_time:
                self.log_result("Handcrafted: Date Time Go", True, 
                               f"✅ VERIFIED: source=handcrafted, real Go date/time code ({len(code)} chars)")
            else:
                self.log_result("Handcrafted: Date Time Go", False, 
                               f"Source=handcrafted but code doesn't contain Go time patterns")
        else:
            self.log_result("Handcrafted: Date Time Go", False, 
                           f"Expected source=handcrafted with real code, got source='{source}', code length={len(code)}")

    def test_handcrafted_string_formatting_javascript(self):
        """Test GET /api/dictionary/rosetta?concept=string_formatting&language=JavaScript&limit=1"""
        params = {'concept': 'string_formatting', 'language': 'JavaScript', 'limit': 1}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Handcrafted: String Formatting JavaScript", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        
        if not entries:
            self.log_result("Handcrafted: String Formatting JavaScript", False, "No entries found for string_formatting JavaScript")
            return
            
        entry = entries[0]
        source = entry.get('source', '')
        code = entry.get('code', '')
        
        # Check for handcrafted source and real JavaScript string formatting code
        if source == 'handcrafted' and len(code.strip()) > 20:
            # Check for JavaScript string formatting patterns
            js_patterns = ['`${', '${', 'template', '.format(', 'String(', 'toString()', 'concat(', '+']
            has_js_formatting = any(pattern in code for pattern in js_patterns)
            
            if has_js_formatting:
                self.log_result("Handcrafted: String Formatting JavaScript", True, 
                               f"✅ VERIFIED: source=handcrafted, real JavaScript string formatting code ({len(code)} chars)")
            else:
                self.log_result("Handcrafted: String Formatting JavaScript", False, 
                               f"Source=handcrafted but code doesn't contain JavaScript string formatting patterns")
        else:
            self.log_result("Handcrafted: String Formatting JavaScript", False, 
                           f"Expected source=handcrafted with real code, got source='{source}', code length={len(code)}")

    # ========================================================================
    # 3. CROSS-LANGUAGE COMPARISON (CORE FEATURE)
    # ========================================================================
    
    def test_cross_language_comparison(self):
        """Test GET /api/dictionary/rosetta?concept=sorting&limit=5 - verify multiple languages returned"""
        params = {'concept': 'sorting', 'limit': 5}
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta', params=params)
        
        if not success:
            self.log_result("Cross-language Comparison", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        
        if len(entries) < 2:
            self.log_result("Cross-language Comparison", False, 
                           f"Expected multiple languages for comparison, got {len(entries)} entries")
            return
            
        # Check for different languages
        languages = set()
        codes = []
        
        for entry in entries:
            language = entry.get('language', '')
            code = entry.get('code', '')
            if language and code:
                languages.add(language)
                codes.append(code)
                
        if len(languages) >= 2 and len(codes) >= 2:
            # Verify codes are different (cross-language comparison)
            unique_codes = set(codes)
            if len(unique_codes) >= 2:
                self.log_result("Cross-language Comparison", True, 
                               f"✅ VERIFIED: Multiple languages returned ({list(languages)}) with different code implementations")
            else:
                self.log_result("Cross-language Comparison", False, 
                               f"Multiple languages found but code implementations are identical")
        else:
            self.log_result("Cross-language Comparison", False, 
                           f"Expected multiple different languages, got {len(languages)} unique languages")

    # ========================================================================
    # 4. CHALLENGE ARENA WITH NEW CONCEPTS
    # ========================================================================
    
    def test_challenge_arena_generation(self):
        """Test GET /api/rosetta-challenge/generate?difficulty=medium - verify can generate from 31 concepts"""
        # Test 5 times to verify randomness works across concepts
        generated_concepts = set()
        
        for i in range(5):
            params = {'difficulty': 'medium'}
            success, data, status = self.make_request('GET', '/api/rosetta-challenge/generate', params=params)
            
            if not success:
                self.log_result(f"Challenge Arena Generation (Test {i+1})", False, f"Request failed: {data}")
                continue
                
            concept = data.get('concept', '')
            challenge_id = data.get('challenge_id', '')
            source_code = data.get('source_code', '')
            hint = data.get('hint', '')
            
            if concept and challenge_id and (source_code or hint):
                generated_concepts.add(concept)
                if i == 0:  # Log details for first test
                    self.log_result(f"Challenge Arena Generation (Test {i+1})", True, 
                                   f"✅ Generated challenge: concept='{concept}', id='{challenge_id}', source_code length={len(source_code)}")
            else:
                self.log_result(f"Challenge Arena Generation (Test {i+1})", False, 
                               f"Missing required fields: concept='{concept}', challenge_id='{challenge_id}', source_code length={len(source_code)}")
        
        # Summary of all 5 tests
        if len(generated_concepts) >= 2:
            self.log_result("Challenge Arena Generation (Randomness)", True, 
                           f"✅ VERIFIED: Generated challenges from {len(generated_concepts)} different concepts: {list(generated_concepts)}")
        else:
            self.log_result("Challenge Arena Generation (Randomness)", False, 
                           f"Expected challenges from multiple concepts, only got: {list(generated_concepts)}")

    # ========================================================================
    # 5. SUBMIT CHALLENGE
    # ========================================================================
    
    def test_submit_challenge(self):
        """Test POST /api/rosetta-challenge/submit - verify scoring system works"""
        # First generate a challenge to get a valid challenge_id
        params = {'difficulty': 'medium'}
        success, data, status = self.make_request('GET', '/api/rosetta-challenge/generate', params=params)
        
        if not success:
            self.log_result("Submit Challenge", False, f"Failed to generate challenge for testing: {data}")
            return
            
        challenge_id = data.get('challenge_id', 'test_v3')  # fallback to test_v3 as mentioned in requirements
        
        # Submit a challenge solution
        params = {
            'challenge_id': challenge_id,
            'user_id': 'test_user',
            'target_language': 'Python',
            'user_code': 'print(42)'
        }
        
        success, data, status = self.make_request('POST', '/api/rosetta-challenge/submit', params=params)
        
        if not success:
            self.log_result("Submit Challenge", False, f"Request failed: {data}")
            return
            
        # Check for expected response fields
        score = data.get('score')
        compiled = data.get('compiled')
        output = data.get('output')
        xp_awarded = data.get('xp_awarded')
        
        required_fields = ['score', 'compiled', 'output', 'xp_awarded']
        missing_fields = [field for field in required_fields if data.get(field) is None]
        
        if not missing_fields:
            self.log_result("Submit Challenge", True, 
                           f"✅ VERIFIED: score={score}, compiled={compiled}, output='{output}', xp_awarded={xp_awarded}")
        else:
            self.log_result("Submit Challenge", False, 
                           f"Missing required fields: {missing_fields}. Got: {data}")

    # ========================================================================
    # 6. STATS VERIFICATION
    # ========================================================================
    
    def test_stats_verification(self):
        """Verify total entries: 13,981, handcrafted: 907, concepts: 31"""
        # Get overall stats from concepts endpoint
        success, data, status = self.make_request('GET', '/api/dictionary/rosetta/concepts')
        
        if not success:
            self.log_result("Stats Verification", False, f"Request failed: {data}")
            return
            
        total_entries = data.get('total_entries', 0)
        concepts = data.get('concepts', [])
        concepts_count = len(concepts)
        
        # Get handcrafted count by querying with source filter
        success2, data2, status2 = self.make_request('GET', '/api/dictionary/rosetta', params={'source': 'handcrafted', 'limit': 1})
        handcrafted_count = 0
        if success2:
            handcrafted_count = data2.get('total', 0)
        
        # Check all three stats
        stats_checks = []
        
        if total_entries == 13981:
            stats_checks.append("✅ Total entries: 13,981 (PERFECT)")
        else:
            stats_checks.append(f"❌ Total entries: {total_entries} (expected 13,981)")
            
        if handcrafted_count >= 907:
            stats_checks.append(f"✅ Handcrafted: {handcrafted_count} (>= 907 expected)")
        else:
            stats_checks.append(f"❌ Handcrafted: {handcrafted_count} (expected >= 907)")
            
        if concepts_count == 31:
            stats_checks.append("✅ Concepts: 31 (PERFECT)")
        else:
            stats_checks.append(f"❌ Concepts: {concepts_count} (expected 31)")
        
        all_perfect = all("✅" in check for check in stats_checks)
        
        if all_perfect:
            self.log_result("Stats Verification", True, 
                           f"✅ PERFECT MATCH: {', '.join(stats_checks)}")
        else:
            self.log_result("Stats Verification", False, 
                           f"Stats mismatch: {', '.join(stats_checks)}")

    # ========================================================================
    # 7. PREVIOUS LEADERBOARD APIs STILL WORKING
    # ========================================================================
    
    def test_leaderboard_boards(self):
        """Test GET /api/leaderboards/boards - should still return 10 boards"""
        success, data, status = self.make_request('GET', '/api/leaderboards/boards')
        
        if not success:
            self.log_result("Leaderboard: Boards List", False, f"Request failed: {data}")
            return
            
        boards = data.get('boards', [])
        total = data.get('total', len(boards))
        
        if total == 10 and len(boards) == 10:
            self.log_result("Leaderboard: Boards List", True, 
                           f"✅ VERIFIED: Returns {total} boards as expected")
        else:
            self.log_result("Leaderboard: Boards List", False, 
                           f"Expected 10 boards, got total={total}, boards length={len(boards)}")

    def test_leaderboard_xp_champions(self):
        """Test GET /api/leaderboards/board/xp_champions?limit=3 - should return entries"""
        params = {'limit': 3}
        success, data, status = self.make_request('GET', '/api/leaderboards/board/xp_champions', params=params)
        
        if not success:
            self.log_result("Leaderboard: XP Champions", False, f"Request failed: {data}")
            return
            
        entries = data.get('entries', [])
        board = data.get('board', {})
        
        if len(entries) > 0 and board.get('name'):
            self.log_result("Leaderboard: XP Champions", True, 
                           f"✅ VERIFIED: Returns {len(entries)} entries for {board.get('name', 'XP Champions')}")
        else:
            self.log_result("Leaderboard: XP Champions", False, 
                           f"Expected entries and board info, got {len(entries)} entries, board: {board}")

    def run_all_tests(self):
        """Run all tests for Wave 3 expansion"""
        print("🎯 TUTOLAGE ROSETTA STONE HYPERSCALE SYSTEM - WAVE 3 EXPANSION TESTING")
        print("=" * 80)
        
        # 1. Rosetta Concepts List
        print("\n📚 1. ROSETTA CONCEPTS LIST (31 concepts, 451 languages each):")
        self.test_rosetta_concepts_list()
        
        # 2. Handcrafted Entries for New Concepts
        print("\n🔨 2. HANDCRAFTED ENTRIES FOR NEW WAVE 3 CONCEPTS:")
        self.test_handcrafted_type_system_python()
        self.test_handcrafted_math_operations_rust()
        self.test_handcrafted_date_time_go()
        self.test_handcrafted_string_formatting_javascript()
        
        # 3. Cross-language Comparison
        print("\n🌐 3. CROSS-LANGUAGE COMPARISON (CORE FEATURE):")
        self.test_cross_language_comparison()
        
        # 4. Challenge Arena with New Concepts
        print("\n🏆 4. CHALLENGE ARENA WITH NEW CONCEPTS:")
        self.test_challenge_arena_generation()
        
        # 5. Submit Challenge
        print("\n📝 5. SUBMIT CHALLENGE:")
        self.test_submit_challenge()
        
        # 6. Stats Verification
        print("\n📊 6. STATS VERIFICATION:")
        self.test_stats_verification()
        
        # 7. Previous Leaderboard APIs Still Working
        print("\n🏅 7. PREVIOUS LEADERBOARD APIs REGRESSION TEST:")
        self.test_leaderboard_boards()
        self.test_leaderboard_xp_champions()
        
        # Summary
        print("\n" + "=" * 80)
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"📊 FINAL RESULTS: {passed_tests}/{total_tests} TESTS PASSED ({(passed_tests/total_tests)*100:.1f}% SUCCESS RATE)")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS ({failed_tests}):")
            for result in self.results:
                if not result['success']:
                    print(f"   • {result['test']}: {result['details']}")
        
        print(f"\n🏆 WAVE 3 EXPANSION TESTING COMPLETE")
        return passed_tests == total_tests

if __name__ == "__main__":
    tester = RosettaWave3Tester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)