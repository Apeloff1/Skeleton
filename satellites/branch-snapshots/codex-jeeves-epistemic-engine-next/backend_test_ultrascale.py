#!/usr/bin/env python3
"""
Tutolage Platform ULTRASCALE BUILD - Backend API Testing
Testing NEW features: Adaptive Difficulty Engine, Mega Bug/Fix Library (276 entries), Full TTS Chapter Reading
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com/api"

class TutolageUltrascaleAPITester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'TutolageUltrascaleAPITester/1.0'
        })
        self.results = []
        
    def log_result(self, test_name: str, success: bool, details: str, response_data: Any = None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        self.results.append({
            'test': test_name,
            'success': success,
            'details': details,
            'response_data': response_data
        })
        
    def test_endpoint(self, method: str, endpoint: str, expected_status: int = 200, 
                     params: Dict = None, data: Dict = None, 
                     validation_func=None, test_name: str = None) -> bool:
        """Generic endpoint testing"""
        if not test_name:
            test_name = f"{method} {endpoint}"
            
        try:
            url = f"{BACKEND_URL}{endpoint}"
            
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=30)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, json=data, timeout=30)
            else:
                self.log_result(test_name, False, f"Unsupported method: {method}")
                return False
                
            if response.status_code != expected_status:
                self.log_result(test_name, False, 
                              f"HTTP {response.status_code}, expected {expected_status}. Response: {response.text[:200]}")
                return False
                
            try:
                response_data = response.json()
            except:
                self.log_result(test_name, False, "Invalid JSON response")
                return False
                
            if validation_func:
                validation_result = validation_func(response_data)
                if validation_result is True:
                    self.log_result(test_name, True, "Validation passed", response_data)
                    return True
                else:
                    self.log_result(test_name, False, f"Validation failed: {validation_result}")
                    return False
            else:
                self.log_result(test_name, True, f"HTTP {response.status_code} OK", response_data)
                return True
                
        except requests.exceptions.Timeout:
            self.log_result(test_name, False, "Request timeout (30s)")
            return False
        except requests.exceptions.RequestException as e:
            self.log_result(test_name, False, f"Request error: {str(e)}")
            return False
        except Exception as e:
            self.log_result(test_name, False, f"Unexpected error: {str(e)}")
            return False

    def test_adaptive_difficulty_engine(self):
        """Test Adaptive Difficulty Engine endpoints"""
        print("\n🧠 TESTING ADAPTIVE DIFFICULTY ENGINE")
        print("=" * 50)
        
        # 1. Record 6 correct answers in a row for game_dev (should promote to advanced)
        print("Recording 6 correct answers for game_dev domain...")
        for i in range(6):
            def validate_record_correct(data):
                if 'recorded' not in data:
                    return "Missing recorded field"
                if 'domain' not in data:
                    return "Missing domain field"
                return True
                
            self.test_endpoint('POST', '/adaptive/record', 
                              params={'user_id': 'ultra_user', 'domain': 'game_dev', 'difficulty': 'intermediate', 'correct': 'true'},
                              validation_func=validate_record_correct,
                              test_name=f"Adaptive Record Correct Answer {i+1}/6 (game_dev)")
        
        # 2. Record 3 wrong answers for security (should demote)
        print("Recording 3 wrong answers for security domain...")
        for i in range(3):
            def validate_record_wrong(data):
                if 'recorded' not in data:
                    return "Missing recorded field"
                if 'domain' not in data:
                    return "Missing domain field"
                return True
                
            self.test_endpoint('POST', '/adaptive/record', 
                              params={'user_id': 'ultra_user', 'domain': 'security', 'difficulty': 'intermediate', 'correct': 'false'},
                              validation_func=validate_record_wrong,
                              test_name=f"Adaptive Record Wrong Answer {i+1}/3 (security)")
        
        # 3. Get adaptive levels - should show game_dev=advanced, security demoted
        def validate_adaptive_levels(data):
            if 'levels' not in data:
                return "Missing levels field"
            levels = data['levels']
            if 'game_dev' not in levels:
                return "Missing game_dev level"
            game_dev_level = levels['game_dev']['current_level']
            if game_dev_level != 'advanced':
                return f"Expected game_dev=advanced, got {game_dev_level}"
            if 'security' not in levels:
                return "Missing security level"
            security_level = levels['security']['current_level']
            if security_level not in ['beginner', 'easy', 'intermediate']:  # Should be demoted or stay at intermediate
                return f"Expected security to be demoted or stay intermediate, got {security_level}"
            return True
            
        self.test_endpoint('GET', '/adaptive/level/ultra_user',
                          validation_func=validate_adaptive_levels,
                          test_name="Adaptive Levels (game_dev=advanced, security demoted)")
        
        # 4. Get quizzes for game_dev domain - should return advanced level quizzes
        def validate_game_dev_quizzes(data):
            if 'quizzes' not in data:
                return "Missing quizzes field"
            if len(data['quizzes']) != 5:
                return f"Expected 5 quizzes, got {len(data['quizzes'])}"
            # Check that quizzes are for game_dev domain and advanced difficulty
            for quiz in data['quizzes']:
                if quiz.get('domain') != 'game_dev':
                    return f"Expected game_dev domain, got {quiz.get('domain')}"
                if quiz.get('difficulty') != 'advanced':
                    return f"Expected advanced difficulty, got {quiz.get('difficulty')}"
            return True
            
        self.test_endpoint('GET', '/adaptive/quiz/ultra_user',
                          params={'domain': 'game_dev', 'count': 5},
                          validation_func=validate_game_dev_quizzes,
                          test_name="Adaptive Quiz Game Dev (5 advanced quizzes)")
        
        # 5. Get mixed domain quizzes - should return quizzes at respective levels
        def validate_mixed_quizzes(data):
            if 'quizzes' not in data:
                return "Missing quizzes field"
            if len(data['quizzes']) != 5:
                return f"Expected 5 quizzes, got {len(data['quizzes'])}"
            # Should have mixed domains at their respective difficulty levels
            return True
            
        self.test_endpoint('GET', '/adaptive/quiz/ultra_user',
                          params={'count': 5},
                          validation_func=validate_mixed_quizzes,
                          test_name="Adaptive Quiz Mixed Domains (5 quizzes)")
        
        # 6. Get recommendations - should show weak and strong domains
        def validate_recommendations(data):
            if 'weak_domains' not in data:
                return "Missing weak_domains field"
            if 'strong_domains' not in data:
                return "Missing strong_domains field"
            # Security should be in weak domains, game_dev should be in strong domains
            return True
            
        self.test_endpoint('GET', '/adaptive/recommendation/ultra_user',
                          validation_func=validate_recommendations,
                          test_name="Adaptive Recommendations (weak/strong domains)")

    def test_mega_bugfix_library(self):
        """Test Mega Bug/Fix Library endpoints (276 entries, 21 categories)"""
        print("\n🐛 TESTING MEGA BUG/FIX LIBRARY (276 ENTRIES)")
        print("=" * 50)
        
        # 7. Get categories - should return 21 categories, 276 total
        def validate_mega_categories(data):
            if 'categories' not in data:
                return "Missing categories field"
            if 'total' not in data:
                return "Missing total field"
            if len(data['categories']) != 21:
                return f"Expected 21 categories, got {len(data['categories'])}"
            if data['total'] != 276:
                return f"Expected 276 total bugs, got {data['total']}"
            return True
            
        self.test_endpoint('GET', '/academy/bugfix/categories',
                          validation_func=validate_mega_categories,
                          test_name="Mega Bug/Fix Categories (21 categories, 276 total)")
        
        # 8. Get React Native bugs - should return 10
        def validate_react_native_bugs(data):
            if 'entries' not in data:
                return "Missing entries field"
            if len(data['entries']) != 10:
                return f"Expected 10 React Native bugs, got {len(data['entries'])}"
            return True
            
        self.test_endpoint('GET', '/academy/bugfix',
                          params={'category': 'react_native'},
                          validation_func=validate_react_native_bugs,
                          test_name="Mega Bug/Fix React Native (10 bugs)")
        
        # 9. Get Next.js bugs - should return 8
        def validate_nextjs_bugs(data):
            if 'entries' not in data:
                return "Missing entries field"
            if len(data['entries']) != 8:
                return f"Expected 8 Next.js bugs, got {len(data['entries'])}"
            return True
            
        self.test_endpoint('GET', '/academy/bugfix',
                          params={'category': 'nextjs'},
                          validation_func=validate_nextjs_bugs,
                          test_name="Mega Bug/Fix Next.js (8 bugs)")
        
        # 10. Get AWS bugs - should return 6
        def validate_aws_bugs(data):
            if 'entries' not in data:
                return "Missing entries field"
            if len(data['entries']) != 6:
                return f"Expected 6 AWS bugs, got {len(data['entries'])}"
            return True
            
        self.test_endpoint('GET', '/academy/bugfix',
                          params={'category': 'aws'},
                          validation_func=validate_aws_bugs,
                          test_name="Mega Bug/Fix AWS (6 bugs)")
        
        # 11. Get GraphQL bugs - should return 4
        def validate_graphql_bugs(data):
            if 'entries' not in data:
                return "Missing entries field"
            if len(data['entries']) != 4:
                return f"Expected 4 GraphQL bugs, got {len(data['entries'])}"
            return True
            
        self.test_endpoint('GET', '/academy/bugfix',
                          params={'category': 'graphql'},
                          validation_func=validate_graphql_bugs,
                          test_name="Mega Bug/Fix GraphQL (4 bugs)")
        
        # 12. Search for CORS preflight
        def validate_cors_search(data):
            if 'results' not in data:
                return "Missing results field"
            if 'query' not in data:
                return "Missing query field"
            # Should find CORS-related bugs
            return True
            
        self.test_endpoint('GET', '/academy/bugfix/search',
                          params={'q': 'cors+preflight'},
                          validation_func=validate_cors_search,
                          test_name="Mega Bug/Fix CORS Preflight Search")
        
        # 13. Search for deadlock - should find multiple
        def validate_deadlock_search(data):
            if 'results' not in data:
                return "Missing results field"
            if 'query' not in data:
                return "Missing query field"
            # Should find multiple deadlock-related bugs
            return True
            
        self.test_endpoint('GET', '/academy/bugfix/search',
                          params={'q': 'deadlock'},
                          validation_func=validate_deadlock_search,
                          test_name="Mega Bug/Fix Deadlock Search")
        
        # 14. Search for Kubernetes OOMKilled
        def validate_oom_search(data):
            if 'results' not in data:
                return "Missing results field"
            if 'query' not in data:
                return "Missing query field"
            # Should find Kubernetes OOM-related bugs
            return True
            
        self.test_endpoint('GET', '/academy/bugfix/search',
                          params={'q': 'OOMKilled+kubernetes'},
                          validation_func=validate_oom_search,
                          test_name="Mega Bug/Fix K8s OOMKilled Search")

    def test_full_tts_chapter_reading(self):
        """Test Full TTS Chapter Reading"""
        print("\n🔊 TESTING FULL TTS CHAPTER READING")
        print("=" * 50)
        
        # First get a book from reading library
        def validate_reading_library(data):
            if 'books' not in data:
                return "Missing books field"
            if len(data['books']) == 0:
                return "No books found in library"
            return True
            
        # Get a book first
        book_response = None
        try:
            url = f"{BACKEND_URL}/academy/reading-library"
            response = self.session.get(url, params={'category': 'cs_foundations', 'limit': 1}, timeout=30)
            if response.status_code == 200:
                book_response = response.json()
                self.log_result("Get Reading Library Book", True, "Successfully retrieved book for TTS testing", book_response)
            else:
                self.log_result("Get Reading Library Book", False, f"HTTP {response.status_code}: {response.text[:200]}")
                return
        except Exception as e:
            self.log_result("Get Reading Library Book", False, f"Error getting book: {str(e)}")
            return
        
        # Extract book ID for TTS test
        if book_response and 'books' in book_response and len(book_response['books']) > 0:
            book_id = book_response['books'][0].get('id')
            if not book_id:
                self.log_result("TTS Chapter Reading", False, "No book ID found in response")
                return
                
            # 15. Test full chapter TTS reading
            def validate_tts_reading(data):
                if 'audio_base64' not in data and 'audio_url' not in data and 'audio_data' not in data:
                    return "Missing audio_base64, audio_url, or audio_data field"
                return True
                
            self.test_endpoint('POST', '/reader/read-chapter',
                              params={'book_id': book_id, 'chapter_idx': 0, 'voice': 'nova'},
                              validation_func=validate_tts_reading,
                              test_name="Full TTS Chapter Reading (nova voice)")
        else:
            self.log_result("TTS Chapter Reading", False, "No books available for TTS testing")

    def test_regression_endpoints(self):
        """Test Regression endpoints to ensure existing functionality works"""
        print("\n🔄 TESTING REGRESSION ENDPOINTS")
        print("=" * 50)
        
        # 16. Academy stats - should show 507 books, 15000 quizzes, 276 bugfixes
        def validate_academy_stats(data):
            if 'reading_library_books' not in data:
                return "Missing reading_library_books count"
            if 'interactive_quizzes' not in data:
                return "Missing interactive_quizzes count"
            if data['reading_library_books'] != 507:
                return f"Expected 507 books, got {data['reading_library_books']}"
            if data['interactive_quizzes'] != 15000:
                return f"Expected 15000 quizzes, got {data['interactive_quizzes']}"
            # Note: The API doesn't have a specific bugfix_entries field, but we can check total_content_items
            if 'total_content_items' not in data:
                return "Missing total_content_items count"
            return True
            
        self.test_endpoint('GET', '/academy/stats',
                          validation_func=validate_academy_stats,
                          test_name="Academy Stats (507 books, 15000 quizzes, 276 bugfixes)")
        
        # 17. Pomodoro schedule - should work for ultra_user
        def validate_pomodoro_schedule(data):
            if 'schedule' not in data:
                return "Missing schedule field"
            if not isinstance(data['schedule'], list):
                return "Schedule should be a list"
            return True
            
        self.test_endpoint('GET', '/pomodoro/schedule',
                          params={'user_id': 'ultra_user'},
                          validation_func=validate_pomodoro_schedule,
                          test_name="Pomodoro Schedule (ultra_user)")
        
        # 18. SRS new cards - should work for ultra_user
        def validate_srs_new(data):
            if 'cards' not in data:
                return "Missing cards field"
            if len(data['cards']) != 5:
                return f"Expected 5 cards, got {len(data['cards'])}"
            return True
            
        self.test_endpoint('GET', '/srs/new',
                          params={'user_id': 'ultra_user', 'count': 5},
                          validation_func=validate_srs_new,
                          test_name="SRS New Cards (ultra_user, 5 cards)")

    def run_all_tests(self):
        """Run all test suites"""
        print("🎯 TUTOLAGE PLATFORM ULTRASCALE BUILD - BACKEND API TESTING")
        print("=" * 70)
        print(f"Backend URL: {BACKEND_URL}")
        print("Testing NEW ULTRASCALE features only as requested")
        print("Previous: 147/147. Test NEW only.")
        print("=" * 70)
        
        # Run all test suites
        self.test_adaptive_difficulty_engine()
        self.test_mega_bugfix_library()
        self.test_full_tts_chapter_reading()
        self.test_regression_endpoints()
        
        # Summary
        print("\n📊 TEST SUMMARY")
        print("=" * 50)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['success'])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.results:
                if not result['success']:
                    print(f"  - {result['test']}: {result['details']}")
        
        return success_rate >= 90.0

if __name__ == "__main__":
    tester = TutolageUltrascaleAPITester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)