#!/usr/bin/env python3
"""
Jeeves Master Build Backend API Testing
Full game creation → code → download pipeline testing
"""

import requests
import json
import time
import zipfile
import io
from typing import Dict, Any, Optional

# Backend URL from frontend/.env
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com/api"

class JeevesMasterTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'JeevesMasterTester/1.0'
        })
        self.results = []
        self.build_id = None  # For sequential testing
        
    def log_result(self, test_name: str, success: bool, details: str, response_data: Any = None):
        """Log test result"""
        result = {
            'test': test_name,
            'success': success,
            'details': details,
            'response_data': response_data
        }
        self.results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        
    def test_endpoint(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     expected_fields: Optional[list] = None, test_name: str = None,
                     expected_status: int = 200) -> Dict[str, Any]:
        """Generic endpoint tester"""
        if not test_name:
            test_name = f"{method} {endpoint}"
            
        try:
            url = f"{BACKEND_URL}{endpoint}"
            
            if method.upper() == "GET":
                response = self.session.get(url, timeout=30)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            if response.status_code == expected_status:
                if expected_status == 200:
                    try:
                        json_data = response.json()
                        
                        # Check expected fields if provided
                        if expected_fields:
                            missing_fields = [field for field in expected_fields if field not in json_data]
                            if missing_fields:
                                self.log_result(test_name, False, f"Missing fields: {missing_fields}", json_data)
                                return {"success": False, "data": json_data}
                        
                        self.log_result(test_name, True, f"Status {expected_status}, response length: {len(str(json_data))}", json_data)
                        return {"success": True, "data": json_data}
                        
                    except json.JSONDecodeError:
                        self.log_result(test_name, False, f"Status {expected_status} but invalid JSON response", response.text)
                        return {"success": False, "data": response.text}
                else:
                    # For non-200 status codes, just return success
                    self.log_result(test_name, True, f"Status {expected_status} as expected", response.text)
                    return {"success": True, "data": response.text}
            else:
                self.log_result(test_name, False, f"HTTP {response.status_code}: {response.text}")
                return {"success": False, "data": response.text}
                
        except requests.exceptions.Timeout:
            self.log_result(test_name, False, "Request timeout (30s)")
            return {"success": False, "data": "timeout"}
        except requests.exceptions.RequestException as e:
            self.log_result(test_name, False, f"Request error: {str(e)}")
            return {"success": False, "data": str(e)}
    
    def test_agent_manifest(self):
        """Test 1: GET /api/jeeves-master/agent-manifest"""
        result = self.test_endpoint(
            "GET", "/jeeves-master/agent-manifest",
            expected_fields=["total_agents", "genres", "build_phases"],
            test_name="Jeeves Master - Agent Manifest"
        )
        
        if result["success"]:
            data = result["data"]
            total_agents = data.get("total_agents", 0)
            genres = data.get("genres", 0)
            build_phases = data.get("build_phases", 0)
            
            # Verify expected values
            if total_agents == 28662:
                self.log_result("Agent Manifest - Total Agents", True, f"Found {total_agents} agents as expected")
            else:
                self.log_result("Agent Manifest - Total Agents", False, f"Expected 28662 agents, got {total_agents}")
            
            if genres == 11:
                self.log_result("Agent Manifest - Genres", True, f"Found {genres} genres as expected")
            else:
                self.log_result("Agent Manifest - Genres", False, f"Expected 11 genres, got {genres}")
                
            if build_phases == 12:
                self.log_result("Agent Manifest - Build Phases", True, f"Found {build_phases} build phases as expected")
            else:
                self.log_result("Agent Manifest - Build Phases", False, f"Expected 12 build phases, got {build_phases}")
        
        return result
    
    def test_genres(self):
        """Test 2: GET /api/jeeves-master/genres"""
        result = self.test_endpoint(
            "GET", "/jeeves-master/genres",
            expected_fields=["genres"],
            test_name="Jeeves Master - Genres List"
        )
        
        if result["success"]:
            data = result["data"]
            genres = data.get("genres", [])
            
            # Expected genres
            expected_genres = ["rpg", "platformer", "puzzle", "shooter", "survival", "racing", "horror", "simulation", "card_game", "roguelike", "open_world"]
            
            if len(genres) == 11:
                self.log_result("Genres - Count", True, f"Found {len(genres)} genres as expected")
                
                # Check if all expected genres are present
                genre_ids = [g.get("id") if isinstance(g, dict) else g for g in genres]
                missing_genres = [g for g in expected_genres if g not in genre_ids]
                
                if not missing_genres:
                    self.log_result("Genres - Content", True, f"All expected genres found: {genre_ids}")
                else:
                    self.log_result("Genres - Content", False, f"Missing genres: {missing_genres}. Found: {genre_ids}")
            else:
                self.log_result("Genres - Count", False, f"Expected 11 genres, got {len(genres)}")
        
        return result
    
    def test_create_game(self):
        """Test 3: POST /api/jeeves-master/create"""
        create_data = {
            "title": "Test Game",
            "genre": "rpg",
            "description": "Test RPG"
        }
        
        result = self.test_endpoint(
            "POST", "/jeeves-master/create",
            data=create_data,
            expected_fields=["build_id"],
            test_name="Jeeves Master - Create Game"
        )
        
        if result["success"]:
            data = result["data"]
            self.build_id = data.get("build_id")
            
            if self.build_id:
                self.log_result("Create Game - Build ID", True, f"Build ID received: {self.build_id}")
            else:
                self.log_result("Create Game - Build ID", False, "No build_id in response")
        
        return result
    
    def test_advance_all_phases(self):
        """Test 4: POST /api/jeeves-master/advance - Advance through ALL 12 phases"""
        if not self.build_id:
            self.log_result("Advance Phases", False, "No build_id available from create test")
            return {"success": False, "data": "no_build_id"}
        
        advance_data = {
            "build_id": self.build_id
        }
        
        # Advance through all 12 phases
        for phase in range(1, 13):
            result = self.test_endpoint(
                "POST", "/jeeves-master/advance",
                data=advance_data,
                expected_fields=["build_id", "progress"],
                test_name=f"Jeeves Master - Advance Phase {phase}"
            )
            
            if result["success"]:
                data = result["data"]
                progress = data.get("progress", 0)
                self.log_result(f"Advance Phase {phase} - Progress", True, f"Progress: {progress}%")
                
                # Check if we reached 100% on the final phase
                if phase == 12 and progress == 100:
                    self.log_result("Advance All Phases - Completion", True, "Reached 100% progress after 12 phases")
                elif phase == 12 and progress != 100:
                    self.log_result("Advance All Phases - Completion", False, f"Expected 100% after 12 phases, got {progress}%")
            else:
                self.log_result(f"Advance Phase {phase}", False, f"Failed to advance phase {phase}")
                return result
        
        return {"success": True, "data": "all_phases_completed"}
    
    def test_build_status(self):
        """Test 5: GET /api/jeeves-master/status/{build_id}"""
        if not self.build_id:
            self.log_result("Build Status", False, "No build_id available from create test")
            return {"success": False, "data": "no_build_id"}
        
        result = self.test_endpoint(
            "GET", f"/jeeves-master/status/{self.build_id}",
            expected_fields=["build_id", "status", "phases"],
            test_name="Jeeves Master - Build Status"
        )
        
        if result["success"]:
            data = result["data"]
            status = data.get("status")
            phases = data.get("phases", [])
            
            if status == "completed":
                self.log_result("Build Status - Completion", True, f"Build status: {status}")
            else:
                self.log_result("Build Status - Completion", False, f"Expected 'completed', got '{status}'")
                
            if len(phases) == 12:
                self.log_result("Build Status - Phases", True, f"Found {len(phases)} phases as expected")
            else:
                self.log_result("Build Status - Phases", False, f"Expected 12 phases, got {len(phases)}")
        
        return result
    
    def test_build_files(self):
        """Test 6: GET /api/jeeves-master/files/{build_id}"""
        if not self.build_id:
            self.log_result("Build Files", False, "No build_id available from create test")
            return {"success": False, "data": "no_build_id"}
        
        result = self.test_endpoint(
            "GET", f"/jeeves-master/files/{self.build_id}",
            expected_fields=["files", "total_files", "total_lines"],
            test_name="Jeeves Master - Build Files"
        )
        
        if result["success"]:
            data = result["data"]
            files = data.get("files", [])
            total_files = data.get("total_files", 0)
            total_lines = data.get("total_lines", 0)
            
            if total_files >= 30:
                self.log_result("Build Files - File Count", True, f"Found {total_files} files (≥30)")
            else:
                self.log_result("Build Files - File Count", False, f"Expected ≥30 files, got {total_files}")
                
            if total_lines >= 1000:
                self.log_result("Build Files - Line Count", True, f"Found {total_lines} total lines (≥1000)")
            else:
                self.log_result("Build Files - Line Count", False, f"Expected ≥1000 lines, got {total_lines}")
        
        return result
    
    def test_specific_file(self):
        """Test 7: GET /api/jeeves-master/file/{build_id}/screens/GameScreen.tsx"""
        if not self.build_id:
            self.log_result("Specific File", False, "No build_id available from create test")
            return {"success": False, "data": "no_build_id"}
        
        result = self.test_endpoint(
            "GET", f"/jeeves-master/file/{self.build_id}/screens/GameScreen.tsx",
            expected_fields=["file_path", "content", "lines"],
            test_name="Jeeves Master - GameScreen.tsx File"
        )
        
        if result["success"]:
            data = result["data"]
            content = data.get("content", "")
            lines = data.get("lines", 0)
            
            if lines >= 200:
                self.log_result("GameScreen File - Line Count", True, f"Found {lines} lines (≥200)")
            else:
                self.log_result("GameScreen File - Line Count", False, f"Expected ≥200 lines, got {lines}")
                
            # Check if content looks like intricate game code
            if "GameScreen" in content and ("tsx" in content.lower() or "react" in content.lower() or "component" in content.lower()):
                self.log_result("GameScreen File - Content", True, "Content appears to be intricate game code")
            else:
                self.log_result("GameScreen File - Content", False, "Content doesn't appear to be game code")
        
        return result
    
    def test_download_zip(self):
        """Test 8: GET /api/jeeves-master/download/{build_id}"""
        if not self.build_id:
            self.log_result("Download ZIP", False, "No build_id available from create test")
            return {"success": False, "data": "no_build_id"}
        
        try:
            url = f"{BACKEND_URL}/jeeves-master/download/{self.build_id}"
            response = self.session.get(url, timeout=60)  # Longer timeout for download
            
            if response.status_code == 200:
                # Check if response is a ZIP file
                content_type = response.headers.get('content-type', '')
                
                if 'zip' in content_type.lower() or 'application/octet-stream' in content_type:
                    # Try to read as ZIP
                    try:
                        zip_data = io.BytesIO(response.content)
                        with zipfile.ZipFile(zip_data, 'r') as zip_file:
                            file_list = zip_file.namelist()
                            self.log_result("Download ZIP - Format", True, f"Valid ZIP file with {len(file_list)} files")
                            return {"success": True, "data": f"zip_with_{len(file_list)}_files"}
                    except zipfile.BadZipFile:
                        self.log_result("Download ZIP - Format", False, "Response is not a valid ZIP file")
                        return {"success": False, "data": "invalid_zip"}
                else:
                    self.log_result("Download ZIP - Content Type", False, f"Expected ZIP content type, got: {content_type}")
                    return {"success": False, "data": content_type}
            else:
                self.log_result("Download ZIP", False, f"HTTP {response.status_code}: {response.text}")
                return {"success": False, "data": response.text}
                
        except requests.exceptions.Timeout:
            self.log_result("Download ZIP", False, "Request timeout (60s)")
            return {"success": False, "data": "timeout"}
        except requests.exceptions.RequestException as e:
            self.log_result("Download ZIP", False, f"Request error: {str(e)}")
            return {"success": False, "data": str(e)}
    
    def test_create_invalid_genre(self):
        """Test 9: POST /api/jeeves-master/create with invalid genre"""
        create_data = {
            "title": "Invalid Game",
            "genre": "invalid_genre",
            "description": "Test with invalid genre"
        }
        
        result = self.test_endpoint(
            "POST", "/jeeves-master/create",
            data=create_data,
            test_name="Jeeves Master - Create with Invalid Genre",
            expected_status=400
        )
        
        return result
    
    def test_regression_hyperscale(self):
        """Test 10: GET /api/hyperscale/status (regression)"""
        result = self.test_endpoint(
            "GET", "/hyperscale/status",
            expected_fields=["domains"],
            test_name="Regression - Hyperscale Status"
        )
        
        if result["success"]:
            data = result["data"]
            domains = data.get("domains", 0)
            
            if domains == 300:
                self.log_result("Regression - Hyperscale Domains", True, f"Found {domains} domains as expected")
            else:
                self.log_result("Regression - Hyperscale Domains", False, f"Expected 300 domains, got {domains}")
        
        return result
    
    def test_regression_health(self):
        """Test 11: GET /api/health (regression)"""
        result = self.test_endpoint(
            "GET", "/health",
            expected_fields=["status"],
            test_name="Regression - Health Check"
        )
        
        if result["success"]:
            data = result["data"]
            status = data.get("status")
            if status == "healthy":
                self.log_result("Regression - Health Status", True, "Health check returned 'healthy'")
            else:
                self.log_result("Regression - Health Status", False, f"Expected 'healthy', got '{status}'")
        
        return result
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting Jeeves Master Build Backend API Testing")
        print("=" * 60)
        
        # Core Jeeves Master Build Tests
        print("\n🎮 JEEVES MASTER BUILD TESTS")
        print("-" * 40)
        self.test_agent_manifest()
        self.test_genres()
        self.test_create_game()
        
        # Only continue with sequential tests if create was successful
        if self.build_id:
            self.test_advance_all_phases()
            self.test_build_status()
            self.test_build_files()
            self.test_specific_file()
            self.test_download_zip()
        else:
            print("⚠️  Skipping sequential tests due to failed game creation")
        
        # Error handling test
        print("\n🚫 ERROR HANDLING TESTS")
        print("-" * 40)
        self.test_create_invalid_genre()
        
        # Regression Tests
        print("\n🔄 REGRESSION TESTS")
        print("-" * 40)
        self.test_regression_hyperscale()
        self.test_regression_health()
        
        # Summary
        print("\n📊 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['success'])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.results:
                if not result['success']:
                    print(f"  - {result['test']}: {result['details']}")
        
        print(f"\n🎯 Jeeves Master Build Testing Complete!")
        return {
            'total': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'success_rate': success_rate,
            'results': self.results
        }

if __name__ == "__main__":
    tester = JeevesMasterTester()
    summary = tester.run_all_tests()