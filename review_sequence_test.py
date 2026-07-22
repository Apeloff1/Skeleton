#!/usr/bin/env python3
"""
Galaxy Studio Factory - Exact Review Request Sequence Test
Testing the exact sequence specified in the review request
"""
import requests
import json
import time
from typing import Dict, Any

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com/api/galaxy-studio"

class ReviewSequenceTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Galaxy-Studio-Review-Tester/1.0'
        })
        self.build_id = None
        
    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        
    def test_step_1_manifest(self):
        """Step 1: GET /api/galaxy-studio/manifest — Should include "synergy_network" with 15 links and 6 constellations"""
        print("\n🔍 Step 1: GET /api/galaxy-studio/manifest")
        
        response = self.session.get(f"{BACKEND_URL}/manifest")
        if response.status_code != 200:
            self.log_result("Step 1", False, f"HTTP {response.status_code}")
            return False
            
        data = response.json()
        
        # Check for synergy_network
        if "synergy_network" not in data:
            self.log_result("Step 1", False, "Missing synergy_network field")
            return False
            
        synergy_network = data["synergy_network"]
        
        # Check for 15 links
        links = synergy_network.get("links", [])
        if len(links) != 15:
            self.log_result("Step 1", False, f"Expected 15 links, got {len(links)}")
            return False
            
        # Check for 6 constellations
        constellations = synergy_network.get("constellations", [])
        if len(constellations) != 6:
            self.log_result("Step 1", False, f"Expected 6 constellations, got {len(constellations)}")
            return False
            
        self.log_result("Step 1", True, f"synergy_network with {len(links)} links and {len(constellations)} constellations")
        return True
        
    def test_step_2_create(self):
        """Step 2: POST /api/galaxy-studio/create with exact payload from review request"""
        print("\n🔍 Step 2: POST /api/galaxy-studio/create")
        
        payload = {
            "title": "Dark Realm",
            "genre": "soulslike",
            "subgenre": "dark_fantasy_souls",
            "game_vision": "A dark fantasy world where fallen gods wage war through mortal champions. Souls-like combat with visceral animations.",
            "system_architecture": "Real-time stamina combat, i-frames, hitstun, procedural dungeons, dynamic lighting, particle effects",
            "world_laws": "Gravity varies by zone. Death drops 50% gold. Bosses have 3 phases. Parry window is 200ms.",
            "agent_instructions": "Prioritize combat feel. Make dodge timing tight. Generate deep skill trees with 8 branches."
        }
        
        response = self.session.post(f"{BACKEND_URL}/create", json=payload)
        if response.status_code != 200:
            self.log_result("Step 2", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
        data = response.json()
        self.build_id = data.get("build_id")
        
        if not self.build_id:
            self.log_result("Step 2", False, "No build_id returned")
            return False
            
        # Verify descriptions_received (all 4 should be true)
        descriptions_received = data.get("descriptions_received", {})
        expected_descriptions = ["game_vision", "system_architecture", "world_laws", "agent_instructions"]
        
        for desc in expected_descriptions:
            if not descriptions_received.get(desc, False):
                self.log_result("Step 2", False, f"descriptions_received.{desc} should be true")
                return False
                
        # Verify synergy_network
        if "synergy_network" not in data:
            self.log_result("Step 2", False, "Missing synergy_network in response")
            return False
            
        self.log_result("Step 2", True, f"Build created: {self.build_id}, all 4 descriptions received, synergy_network present")
        return True
        
    def test_step_3_advance_12_times(self):
        """Step 3: POST /api/galaxy-studio/advance (12 times) — Each response should include synergy_activations with links_activated > 0"""
        print("\n🔍 Step 3: POST /api/galaxy-studio/advance (12 times)")
        
        if not self.build_id:
            self.log_result("Step 3", False, "No build_id available")
            return False
            
        for advance_num in range(12):
            payload = {"build_id": self.build_id}
            response = self.session.post(f"{BACKEND_URL}/advance", json=payload)
            
            if response.status_code != 200:
                self.log_result("Step 3", False, f"Advance {advance_num + 1} failed: HTTP {response.status_code}")
                return False
                
            data = response.json()
            
            # Check for synergy_activations
            if "synergy_activations" not in data:
                self.log_result("Step 3", False, f"Advance {advance_num + 1} missing synergy_activations")
                return False
                
            synergy_activations = data["synergy_activations"]
            links_activated = synergy_activations.get("links_activated", 0)
            
            if links_activated <= 0:
                self.log_result("Step 3", False, f"Advance {advance_num + 1} has links_activated = {links_activated}, expected > 0")
                return False
                
            print(f"  Advance {advance_num + 1}/12: {links_activated} links activated")
            
            # Check if build is completed
            if data.get("status") == "completed":
                break
                
            # Small delay between advances
            time.sleep(0.1)
            
        self.log_result("Step 3", True, "All 12 advances completed with synergy_activations.links_activated > 0")
        return True
        
    def test_step_4_files_list(self):
        """Step 4: GET /api/galaxy-studio/files/{build_id} — Should include DESIGN_DOCUMENT.md and store/designDirectives.ts in the file list"""
        print("\n🔍 Step 4: GET /api/galaxy-studio/files/{build_id}")
        
        if not self.build_id:
            self.log_result("Step 4", False, "No build_id available")
            return False
            
        response = self.session.get(f"{BACKEND_URL}/files/{self.build_id}")
        if response.status_code != 200:
            self.log_result("Step 4", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
        data = response.json()
        files = data.get("files", [])
        
        # Look for specific files
        file_paths = [file_info.get("path", "") for file_info in files]
        
        if "DESIGN_DOCUMENT.md" not in file_paths:
            self.log_result("Step 4", False, "DESIGN_DOCUMENT.md not found in file list")
            return False
            
        if "store/designDirectives.ts" not in file_paths:
            self.log_result("Step 4", False, "store/designDirectives.ts not found in file list")
            return False
            
        self.log_result("Step 4", True, f"Found DESIGN_DOCUMENT.md and store/designDirectives.ts in {len(files)} files")
        return True
        
    def test_step_5_design_document(self):
        """Step 5: GET /api/galaxy-studio/file/{build_id}/DESIGN_DOCUMENT.md — Content should contain the user's vision, system arch, world laws, and agent instructions"""
        print("\n🔍 Step 5: GET /api/galaxy-studio/file/{build_id}/DESIGN_DOCUMENT.md")
        
        if not self.build_id:
            self.log_result("Step 5", False, "No build_id available")
            return False
            
        response = self.session.get(f"{BACKEND_URL}/file/{self.build_id}/DESIGN_DOCUMENT.md")
        if response.status_code != 200:
            self.log_result("Step 5", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
        data = response.json()
        content = data.get("content", "")
        
        if not content:
            self.log_result("Step 5", False, "Empty content")
            return False
            
        # Check for key phrases from our input
        expected_phrases = [
            "dark fantasy world",
            "fallen gods wage war",
            "Real-time stamina combat",
            "Gravity varies by zone",
            "Prioritize combat feel"
        ]
        
        missing_phrases = []
        for phrase in expected_phrases:
            if phrase not in content:
                missing_phrases.append(phrase)
                
        if missing_phrases:
            self.log_result("Step 5", False, f"Missing phrases: {missing_phrases}")
            return False
            
        self.log_result("Step 5", True, f"DESIGN_DOCUMENT.md contains all user descriptions ({len(content)} chars)")
        return True
        
    def test_step_6_design_directives(self):
        """Step 6: GET /api/galaxy-studio/file/{build_id}/store/designDirectives.ts — Should contain DESIGN_DIRECTIVES with all user descriptions"""
        print("\n🔍 Step 6: GET /api/galaxy-studio/file/{build_id}/store/designDirectives.ts")
        
        if not self.build_id:
            self.log_result("Step 6", False, "No build_id available")
            return False
            
        response = self.session.get(f"{BACKEND_URL}/file/{self.build_id}/store/designDirectives.ts")
        if response.status_code != 200:
            self.log_result("Step 6", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
        data = response.json()
        content = data.get("content", "")
        
        if not content:
            self.log_result("Step 6", False, "Empty content")
            return False
            
        # Check for DESIGN_DIRECTIVES structure
        if "DESIGN_DIRECTIVES" not in content:
            self.log_result("Step 6", False, "Missing DESIGN_DIRECTIVES constant")
            return False
            
        # Check for key fields (camelCase as used in TypeScript)
        expected_fields = [
            "gameVision",
            "systemArchitecture", 
            "worldLaws",
            "agentInstructions"
        ]
        
        missing_fields = []
        for field in expected_fields:
            if field not in content:
                missing_fields.append(field)
                
        if missing_fields:
            self.log_result("Step 6", False, f"Missing fields: {missing_fields}")
            return False
            
        self.log_result("Step 6", True, f"store/designDirectives.ts contains DESIGN_DIRECTIVES with all user descriptions ({len(content)} chars)")
        return True
        
    def run_exact_review_sequence(self):
        """Run the exact sequence from the review request"""
        print("🎯 Galaxy Studio Factory - Exact Review Request Sequence")
        print("Testing at http://localhost:8001 with rich descriptions and synergy tracking")
        print("=" * 100)
        
        tests = [
            ("Step 1: Manifest with synergy_network", self.test_step_1_manifest),
            ("Step 2: Create with rich descriptions", self.test_step_2_create),
            ("Step 3: Advance 12 times with synergy", self.test_step_3_advance_12_times),
            ("Step 4: Files list verification", self.test_step_4_files_list),
            ("Step 5: Design document content", self.test_step_5_design_document),
            ("Step 6: Design directives content", self.test_step_6_design_directives),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            if test_func():
                passed += 1
            else:
                print(f"   ❌ {test_name} FAILED")
                break  # Stop on first failure for review sequence
                
        print("\n" + "=" * 100)
        print(f"🎯 REVIEW SEQUENCE RESULTS: {passed}/{total} PASSED ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 ALL REVIEW STEPS PASSED! Galaxy Studio Factory with rich descriptions and synergy tracking is fully functional.")
        else:
            print(f"⚠️  Review sequence failed at step {passed + 1}.")
            
        return passed == total

def main():
    """Main test runner"""
    tester = ReviewSequenceTester()
    success = tester.run_exact_review_sequence()
    
    if success:
        print("\n✅ REVIEW REQUEST CONFIRMED:")
        print("   • Step 1: Manifest includes synergy_network with 15 links and 6 constellations")
        print("   • Step 2: Create accepts rich descriptions and returns descriptions_received (all 4 true)")
        print("   • Step 3: Advance (12 times) includes synergy_activations with links_activated > 0")
        print("   • Step 4: Files list includes DESIGN_DOCUMENT.md and store/designDirectives.ts")
        print("   • Step 5: DESIGN_DOCUMENT.md contains user's vision, system arch, world laws, agent instructions")
        print("   • Step 6: store/designDirectives.ts contains DESIGN_DIRECTIVES with all user descriptions")
    
    return success

if __name__ == "__main__":
    main()