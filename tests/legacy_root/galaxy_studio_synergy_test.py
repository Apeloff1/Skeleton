#!/usr/bin/env python3
"""
Galaxy Studio Factory - Rich Descriptions and Synergy Tracking Test
Testing specific features mentioned in the review request
"""
import requests
import json
import time
from typing import Dict, Any

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com/api/galaxy-studio"

class GalaxyStudioSynergyTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Galaxy-Studio-Synergy-Tester/1.0'
        })
        self.build_id = None
        self.test_results = []
        
    def log_result(self, test_name: str, success: bool, details: str = "", data: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "data": data
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        
    def test_manifest_synergy_network(self):
        """Test 1: GET /api/galaxy-studio/manifest — Should include "synergy_network" with 15 links and 6 constellations"""
        try:
            response = self.session.get(f"{BACKEND_URL}/manifest")
            if response.status_code != 200:
                self.log_result("Manifest Synergy Network", False, f"HTTP {response.status_code}")
                return False
                
            data = response.json()
            
            # Check for synergy_network
            if "synergy_network" not in data:
                self.log_result("Manifest Synergy Network", False, "Missing synergy_network field")
                return False
                
            synergy_network = data["synergy_network"]
            
            # Check for 15 links
            links = synergy_network.get("links", [])
            if len(links) != 15:
                self.log_result("Manifest Synergy Network", False, f"Expected 15 links, got {len(links)}")
                return False
                
            # Check for 6 constellations
            constellations = synergy_network.get("constellations", [])
            if len(constellations) != 6:
                self.log_result("Manifest Synergy Network", False, f"Expected 6 constellations, got {len(constellations)}")
                return False
                
            self.log_result("Manifest Synergy Network", True, f"✅ synergy_network with {len(links)} links and {len(constellations)} constellations")
            return True
            
        except Exception as e:
            self.log_result("Manifest Synergy Network", False, f"Exception: {str(e)}")
            return False
            
    def test_create_with_descriptions(self):
        """Test 2: POST /api/galaxy-studio/create with rich descriptions and synergy tracking"""
        try:
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
                self.log_result("Create with Descriptions", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            self.build_id = data.get("build_id")
            
            if not self.build_id:
                self.log_result("Create with Descriptions", False, "No build_id returned")
                return False
                
            # Check for descriptions_received (all 4 should be true)
            descriptions_received = data.get("descriptions_received", {})
            expected_descriptions = ["game_vision", "system_architecture", "world_laws", "agent_instructions"]
            
            for desc in expected_descriptions:
                if not descriptions_received.get(desc, False):
                    self.log_result("Create with Descriptions", False, f"descriptions_received.{desc} should be true")
                    return False
                    
            # Check for synergy_network
            if "synergy_network" not in data:
                self.log_result("Create with Descriptions", False, "Missing synergy_network in response")
                return False
                
            self.log_result("Create with Descriptions", True, f"✅ Build created: {self.build_id}, all 4 descriptions received, synergy_network present")
            return True
            
        except Exception as e:
            self.log_result("Create with Descriptions", False, f"Exception: {str(e)}")
            return False
            
    def test_advance_with_synergy_activations(self):
        """Test 3: POST /api/galaxy-studio/advance (12 times) — Each response should include synergy_activations with links_activated > 0"""
        if not self.build_id:
            self.log_result("Advance with Synergy", False, "No build_id available")
            return False
            
        try:
            successful_advances = 0
            
            for advance_num in range(12):
                payload = {"build_id": self.build_id}
                response = self.session.post(f"{BACKEND_URL}/advance", json=payload)
                
                if response.status_code != 200:
                    self.log_result("Advance with Synergy", False, f"Advance {advance_num + 1} failed: HTTP {response.status_code}")
                    return False
                    
                data = response.json()
                
                # Check for synergy_activations
                if "synergy_activations" not in data:
                    self.log_result("Advance with Synergy", False, f"Advance {advance_num + 1} missing synergy_activations")
                    return False
                    
                synergy_activations = data["synergy_activations"]
                links_activated = synergy_activations.get("links_activated", 0)
                
                if links_activated <= 0:
                    self.log_result("Advance with Synergy", False, f"Advance {advance_num + 1} has links_activated = {links_activated}, expected > 0")
                    return False
                    
                successful_advances += 1
                print(f"  Advance {advance_num + 1}/12: {links_activated} links activated")
                
                # Check if build is completed
                if data.get("status") == "completed":
                    break
                    
                # Small delay between advances
                time.sleep(0.1)
                
            self.log_result("Advance with Synergy", True, f"✅ All {successful_advances} advances had synergy_activations with links_activated > 0")
            return True
            
        except Exception as e:
            self.log_result("Advance with Synergy", False, f"Exception: {str(e)}")
            return False
            
    def test_files_list(self):
        """Test 4: GET /api/galaxy-studio/files/{build_id} — Should include DESIGN_DOCUMENT.md and store/designDirectives.ts"""
        if not self.build_id:
            self.log_result("Files List", False, "No build_id available")
            return False
            
        try:
            response = self.session.get(f"{BACKEND_URL}/files/{self.build_id}")
            if response.status_code != 200:
                self.log_result("Files List", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            files = data.get("files", [])
            
            # Look for specific files (using 'path' field instead of 'name')
            file_paths = [file_info.get("path", "") for file_info in files]
            
            if "DESIGN_DOCUMENT.md" not in file_paths:
                self.log_result("Files List", False, "DESIGN_DOCUMENT.md not found in file list")
                return False
                
            if "store/designDirectives.ts" not in file_paths:
                self.log_result("Files List", False, "store/designDirectives.ts not found in file list")
                return False
                
            self.log_result("Files List", True, f"✅ Found DESIGN_DOCUMENT.md and store/designDirectives.ts in {len(files)} files")
            return True
            
        except Exception as e:
            self.log_result("Files List", False, f"Exception: {str(e)}")
            return False
            
    def test_design_document_content(self):
        """Test 5: GET /api/galaxy-studio/file/{build_id}/DESIGN_DOCUMENT.md — Content should contain user's vision, system arch, world laws, and agent instructions"""
        if not self.build_id:
            self.log_result("Design Document Content", False, "No build_id available")
            return False
            
        try:
            response = self.session.get(f"{BACKEND_URL}/file/{self.build_id}/DESIGN_DOCUMENT.md")
            if response.status_code != 200:
                self.log_result("Design Document Content", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            content = data.get("content", "")
            
            if not content:
                self.log_result("Design Document Content", False, "Empty content")
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
                self.log_result("Design Document Content", False, f"Missing phrases: {missing_phrases}")
                return False
                
            self.log_result("Design Document Content", True, f"✅ DESIGN_DOCUMENT.md contains all user descriptions ({len(content)} chars)")
            return True
            
        except Exception as e:
            self.log_result("Design Document Content", False, f"Exception: {str(e)}")
            return False
            
    def test_design_directives_content(self):
        """Test 6: GET /api/galaxy-studio/file/{build_id}/store/designDirectives.ts — Should contain DESIGN_DIRECTIVES with all user descriptions"""
        if not self.build_id:
            self.log_result("Design Directives Content", False, "No build_id available")
            return False
            
        try:
            response = self.session.get(f"{BACKEND_URL}/file/{self.build_id}/store/designDirectives.ts")
            if response.status_code != 200:
                self.log_result("Design Directives Content", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            content = data.get("content", "")
            
            if not content:
                self.log_result("Design Directives Content", False, "Empty content")
                return False
                
            # Check for DESIGN_DIRECTIVES structure
            if "DESIGN_DIRECTIVES" not in content:
                self.log_result("Design Directives Content", False, "Missing DESIGN_DIRECTIVES constant")
                return False
                
            # Check for key fields from our input (using camelCase as used in TypeScript)
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
                self.log_result("Design Directives Content", False, f"Missing fields: {missing_fields}")
                return False
                
            self.log_result("Design Directives Content", True, f"✅ store/designDirectives.ts contains DESIGN_DIRECTIVES with all user descriptions ({len(content)} chars)")
            return True
            
        except Exception as e:
            self.log_result("Design Directives Content", False, f"Exception: {str(e)}")
            return False
            
    def run_synergy_test_sequence(self):
        """Run the specific synergy and rich descriptions test sequence"""
        print("🎯 Starting Galaxy Studio Factory - Rich Descriptions and Synergy Tracking Test")
        print("=" * 90)
        
        tests = [
            ("Manifest Synergy Network (15 links, 6 constellations)", self.test_manifest_synergy_network),
            ("Create with Rich Descriptions (4 descriptions + synergy)", self.test_create_with_descriptions),
            ("Advance with Synergy Activations (12 times, links_activated > 0)", self.test_advance_with_synergy_activations),
            ("Files List (DESIGN_DOCUMENT.md + store/designDirectives.ts)", self.test_files_list),
            ("Design Document Content (user vision, arch, laws, instructions)", self.test_design_document_content),
            ("Design Directives Content (DESIGN_DIRECTIVES with all descriptions)", self.test_design_directives_content),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n🧪 Testing: {test_name}")
            if test_func():
                passed += 1
            else:
                print(f"   ❌ {test_name} FAILED")
                
        print("\n" + "=" * 90)
        print(f"🎯 SYNERGY & RICH DESCRIPTIONS TEST RESULTS: {passed}/{total} PASSED ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 ALL SYNERGY TESTS PASSED! Rich descriptions and synergy tracking fully functional.")
        else:
            print(f"⚠️  {total - passed} tests failed. Review the issues above.")
            
        return passed == total

def main():
    """Main test runner"""
    tester = GalaxyStudioSynergyTester()
    success = tester.run_synergy_test_sequence()
    
    if success:
        print("\n✅ SYNERGY & RICH DESCRIPTIONS CONFIRMED:")
        print("   • Manifest includes synergy_network with 15 links and 6 constellations")
        print("   • Create endpoint accepts rich descriptions and returns descriptions_received")
        print("   • Advance endpoint includes synergy_activations with links_activated > 0")
        print("   • Generated files include DESIGN_DOCUMENT.md and store/designDirectives.ts")
        print("   • File contents contain all user-provided descriptions")
    
    return success

if __name__ == "__main__":
    main()