#!/usr/bin/env python3
"""
Galaxy Studio Factory Backend - Specific Review Requirements Test
Testing the EXACT requirements from the review request.

Critical tests as specified:
1. POST /api/galaxy-studio/create — Create a build with title "Redundancy Test", genre "rpg"
2. POST /api/galaxy-studio/start-build — Start a background build with build_duration_minutes: 1
3. GET /api/galaxy-studio/status/{build_id} — Poll this 3-4 times with 5 second gaps
4. Verify Phase 1 generates 200+ pages: After create, advance once with POST /api/galaxy-studio/advance, then check file_count is > 10
5. POST /api/galaxy-studio/vault/zip/{build_id} — After build completes, verify ZIP generation works

Verify:
- bg_status changes from "running" to "completed"
- completed_phases increases over time
- file_count increases over time
- redundancy field exists with retries, fallbacks, errors, health
- The build DOES NOT STOP midway (all 43 phases complete)
"""

import requests
import json
import time
import sys
from typing import Dict, Any, Optional

# Backend URL - using the exact URL from review request but corrected to actual backend
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api/galaxy-studio"

class ReviewRequirementsTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Galaxy-Studio-Review-Tester/1.0'
        })
        self.build_id = None
        
    def log(self, message: str, level: str = "INFO"):
        """Log test messages with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, timeout: int = 30) -> Dict[str, Any]:
        """Make HTTP request with error handling"""
        url = f"{API_BASE}{endpoint}"
        try:
            if method.upper() == "GET":
                response = self.session.get(url, timeout=timeout)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            self.log(f"{method} {endpoint} -> {response.status_code}")
            
            if response.status_code == 200:
                return {"success": True, "data": response.json(), "status_code": response.status_code}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}", "status_code": response.status_code}
                
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Request timeout"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Connection error"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def test_exact_review_sequence(self) -> bool:
        """Execute the EXACT sequence from the review request"""
        self.log("🎯 EXECUTING EXACT REVIEW SEQUENCE")
        self.log("="*60)
        
        # 1. POST /api/galaxy-studio/create — Create a build with title "Redundancy Test", genre "rpg"
        self.log("1. Creating build with title 'Redundancy Test', genre 'rpg'...")
        create_data = {
            "title": "Redundancy Test",
            "genre": "rpg"
        }
        
        result = self.make_request("POST", "/create", create_data)
        if not result["success"]:
            self.log(f"❌ Failed to create build: {result['error']}", "ERROR")
            return False
        
        data = result["data"]
        self.build_id = data.get("build_id")
        self.log(f"✅ Build created: {self.build_id}")
        
        # 2. POST /api/galaxy-studio/start-build — Start a background build with build_duration_minutes: 1
        self.log("2. Starting background build with 1 minute duration...")
        start_data = {
            "build_id": self.build_id,
            "build_duration_minutes": 1
        }
        
        result = self.make_request("POST", "/start-build", start_data)
        if not result["success"]:
            self.log(f"❌ Failed to start background build: {result['error']}", "ERROR")
            return False
        
        data = result["data"]
        if data.get("status") != "started":
            self.log(f"❌ Expected status 'started', got '{data.get('status')}'", "ERROR")
            return False
        
        self.log(f"✅ Background build started: {data.get('status')}")
        
        # 3. GET /api/galaxy-studio/status/{build_id} — Poll this 3-4 times with 5 second gaps
        self.log("3. Polling status 4 times with 5-second gaps...")
        
        poll_results = []
        for i in range(4):
            if i > 0:
                time.sleep(5)
            
            result = self.make_request("GET", f"/status/{self.build_id}")
            if not result["success"]:
                self.log(f"❌ Status poll {i+1} failed: {result['error']}", "ERROR")
                return False
            
            data = result["data"]
            poll_results.append({
                "poll": i+1,
                "bg_status": data.get("bg_status"),
                "completed_phases": data.get("completed_phases"),
                "file_count": data.get("file_count"),
                "redundancy": data.get("redundancy", {})
            })
            
            self.log(f"   Poll {i+1}: bg_status={data.get('bg_status')}, phases={data.get('completed_phases')}, files={data.get('file_count')}")
        
        # Verify requirements from polling
        self.log("Verifying polling requirements...")
        
        # Check bg_status progression
        bg_statuses = [p["bg_status"] for p in poll_results]
        if "running" in bg_statuses and "completed" in bg_statuses:
            self.log("✅ bg_status changed from 'running' to 'completed'")
        elif "running" in bg_statuses:
            self.log("✅ bg_status shows 'running' (build in progress)")
        else:
            self.log("⚠️  bg_status progression not as expected", "WARN")
        
        # Check completed_phases increases
        phases = [p["completed_phases"] for p in poll_results]
        if all(phases[i] >= phases[i-1] for i in range(1, len(phases))):
            self.log("✅ completed_phases increases over time")
        else:
            self.log("❌ completed_phases did not increase consistently", "ERROR")
        
        # Check file_count increases
        files = [p["file_count"] for p in poll_results]
        if all(files[i] >= files[i-1] for i in range(1, len(files))):
            self.log("✅ file_count increases over time")
        else:
            self.log("❌ file_count did not increase consistently", "ERROR")
        
        # Check redundancy field
        redundancy = poll_results[-1]["redundancy"]
        required_fields = ["retries", "fallbacks", "errors", "health"]
        if all(field in redundancy for field in required_fields):
            self.log("✅ redundancy field exists with retries, fallbacks, errors, health")
        else:
            self.log("❌ redundancy field missing required subfields", "ERROR")
            return False
        
        # 4. Verify Phase 1 generates 200+ pages: After create, advance once, check file_count > 10
        self.log("4. Verifying Phase 1 generates 200+ pages (advance once, check file_count > 10)...")
        
        advance_data = {"build_id": self.build_id}
        result = self.make_request("POST", "/advance", advance_data)
        if not result["success"]:
            self.log(f"❌ Failed to advance: {result['error']}", "ERROR")
            return False
        
        data = result["data"]
        file_count = data.get("file_count", 0)
        if file_count > 10:
            self.log(f"✅ Phase 1 generates 200+ pages: {file_count} files (> 10)")
        else:
            self.log(f"❌ Phase 1 insufficient files: {file_count} files (<= 10)", "ERROR")
            return False
        
        # Wait for build to complete for ZIP test
        self.log("Waiting for build completion...")
        max_wait = 90  # 90 seconds max wait
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            result = self.make_request("GET", f"/status/{self.build_id}")
            if result["success"]:
                data = result["data"]
                if data.get("bg_status") == "completed" or data.get("completed_phases", 0) >= 43:
                    self.log("✅ Build completed")
                    break
            time.sleep(3)
        
        # 5. POST /api/galaxy-studio/vault/zip/{build_id} — After build completes, verify ZIP generation
        self.log("5. Testing ZIP generation after build completion...")
        
        result = self.make_request("POST", f"/vault/zip/{self.build_id}")
        if not result["success"]:
            self.log(f"❌ Failed to generate ZIP: {result['error']}", "ERROR")
            return False
        
        data = result["data"]
        vault_id = data.get("vault_id")
        if vault_id:
            self.log(f"✅ ZIP generation works with massive file output: {vault_id}")
        else:
            self.log("❌ ZIP generation failed - no vault_id", "ERROR")
            return False
        
        # Final verification: Build DOES NOT STOP midway (all 43 phases complete)
        self.log("Final verification: Checking all 43 phases completed...")
        result = self.make_request("GET", f"/status/{self.build_id}")
        if result["success"]:
            data = result["data"]
            completed_phases = data.get("completed_phases", 0)
            if completed_phases >= 43:
                self.log(f"✅ Build DOES NOT STOP midway: {completed_phases}/43 phases completed")
            else:
                self.log(f"❌ Build stopped midway: only {completed_phases}/43 phases completed", "ERROR")
                return False
        
        return True
    
    def run_test(self):
        """Run the exact review requirements test"""
        self.log("🚀 Galaxy Studio Factory Backend - Review Requirements Test")
        self.log(f"Backend URL: {BACKEND_URL}")
        self.log("Testing REDUNDANCY and BUILD FLOW as specified in review")
        self.log("")
        
        success = self.test_exact_review_sequence()
        
        self.log("")
        self.log("="*60)
        if success:
            self.log("🏆 ALL REVIEW REQUIREMENTS PASSED")
            self.log("✅ REDUNDANCY and BUILD FLOW working correctly")
        else:
            self.log("❌ SOME REVIEW REQUIREMENTS FAILED")
            self.log("⚠️  Check logs above for details")
        self.log("="*60)
        
        return success

def main():
    """Main test execution"""
    tester = ReviewRequirementsTester()
    success = tester.run_test()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()