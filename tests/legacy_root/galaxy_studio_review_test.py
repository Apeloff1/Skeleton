#!/usr/bin/env python3
"""
Galaxy Studio Factory FULL Pipeline Testing - Review Request
Testing ALL new endpoints as specified in the review request
"""
import requests
import json
import time
from typing import Dict, Any

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com/api/galaxy-studio"

class GalaxyStudioReviewTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Galaxy-Studio-Review-Tester/1.0'
        })
        self.build_id = None
        self.vault_id = None
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
        
    def test_1_manifest(self):
        """Test 1: GET /api/galaxy-studio/manifest — Verify version "3.0 — UNLIMITED", capabilities.scale_parsing=true, capabilities.file_limit contains "NONE" """
        try:
            response = self.session.get(f"{BACKEND_URL}/manifest")
            if response.status_code != 200:
                self.log_result("1. Manifest Endpoint", False, f"HTTP {response.status_code}")
                return False
                
            data = response.json()
            
            # Verify version
            version = data.get("version", "")
            if "3.0" not in version or "UNLIMITED" not in version:
                self.log_result("1. Manifest Version", False, f"Expected version '3.0 — UNLIMITED', got '{version}'")
                return False
                
            # Verify capabilities
            capabilities = data.get("capabilities", {})
            if not capabilities.get("scale_parsing"):
                self.log_result("1. Manifest Scale Parsing", False, f"Expected scale_parsing=true, got {capabilities.get('scale_parsing')}")
                return False
                
            file_limit = capabilities.get("file_limit", "")
            if "NONE" not in file_limit:
                self.log_result("1. Manifest File Limit", False, f"Expected file_limit to contain 'NONE', got '{file_limit}'")
                return False
                
            self.log_result("1. Manifest Endpoint", True, f"✅ Version: {version}, scale_parsing: {capabilities.get('scale_parsing')}, file_limit: {file_limit}")
            return True
            
        except Exception as e:
            self.log_result("1. Manifest Endpoint", False, f"Exception: {str(e)}")
            return False
            
    def test_2_create_titan_build(self):
        """Test 2: POST /api/galaxy-studio/create — Body: {"title":"TestRPG","genre":"rpg","scale":"1 million assets 100gb game","game_vision":"dark fantasy"} — Verify scale.label is "TITAN", scale.target_files=1000000, scale.target_size_gb=100"""
        try:
            payload = {
                "title": "TestRPG",
                "genre": "rpg", 
                "scale": "1 million assets 100gb game",
                "game_vision": "dark fantasy"
            }
            
            response = self.session.post(f"{BACKEND_URL}/create", json=payload)
            if response.status_code != 200:
                self.log_result("2. Create TITAN Build", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            self.build_id = data.get("build_id")
            
            if not self.build_id:
                self.log_result("2. Create TITAN Build", False, "No build_id returned")
                return False
                
            # Verify scale parsing
            scale = data.get("scale", {})
            if scale.get("label") != "TITAN":
                self.log_result("2. Scale Label", False, f"Expected scale.label='TITAN', got '{scale.get('label')}'")
                return False
                
            if scale.get("target_files") != 1000000:
                self.log_result("2. Target Files", False, f"Expected scale.target_files=1000000, got {scale.get('target_files')}")
                return False
                
            if scale.get("target_size_gb") != 100:
                self.log_result("2. Target Size GB", False, f"Expected scale.target_size_gb=100, got {scale.get('target_size_gb')}")
                return False
                
            self.log_result("2. Create TITAN Build", True, f"✅ Build ID: {self.build_id}, Scale: {scale.get('label')}, Files: {scale.get('target_files')}, Size: {scale.get('target_size_gb')}GB")
            return True
            
        except Exception as e:
            self.log_result("2. Create TITAN Build", False, f"Exception: {str(e)}")
            return False
            
    def test_3_advance_12_phases(self):
        """Test 3: POST /api/galaxy-studio/advance — Advance the build through all 12 phases (loop 12 times). Verify final status is "completed", file_count > 500"""
        if not self.build_id:
            self.log_result("3. Advance 12 Phases", False, "No build_id available")
            return False
            
        try:
            final_status = None
            final_file_count = 0
            
            for phase_num in range(12):
                payload = {"build_id": self.build_id}
                response = self.session.post(f"{BACKEND_URL}/advance", json=payload)
                
                if response.status_code != 200:
                    self.log_result("3. Advance 12 Phases", False, f"Phase {phase_num + 1} failed: HTTP {response.status_code}")
                    return False
                    
                data = response.json()
                final_status = data.get("status")
                final_file_count = data.get("file_count", 0)
                progress_pct = data.get("progress_pct", 0)
                
                print(f"  Phase {phase_num + 1}/12 - Status: {final_status}, Progress: {progress_pct}%, Files: {final_file_count}")
                
                # Small delay between phases
                time.sleep(0.1)
                
            # Verify final status is "completed"
            if final_status != "completed":
                self.log_result("3. Final Status", False, f"Expected final status='completed', got '{final_status}'")
                return False
                
            # Verify file_count > 500
            if final_file_count <= 500:
                self.log_result("3. File Count", False, f"Expected file_count > 500, got {final_file_count}")
                return False
                
            self.log_result("3. Advance 12 Phases", True, f"✅ All 12 phases completed, Status: {final_status}, Files: {final_file_count}")
            return True
            
        except Exception as e:
            self.log_result("3. Advance 12 Phases", False, f"Exception: {str(e)}")
            return False
            
    def test_4_pipeline_batch_0(self):
        """Test 4: GET /api/galaxy-studio/pipeline/{build_id}?batch=0&batch_size=5000 — Verify files_in_batch > 500, total_files = 1000000, total_batches > 1"""
        if not self.build_id:
            self.log_result("4. Pipeline Batch 0", False, "No build_id available")
            return False
            
        try:
            response = self.session.get(f"{BACKEND_URL}/pipeline/{self.build_id}?batch=0&batch_size=5000")
            if response.status_code != 200:
                self.log_result("4. Pipeline Batch 0", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            
            files_in_batch = data.get("files_in_batch", 0)
            total_files = data.get("total_files", 0)
            total_batches = data.get("total_batches", 0)
            
            # Verify files_in_batch > 500
            if files_in_batch <= 500:
                self.log_result("4. Files in Batch", False, f"Expected files_in_batch > 500, got {files_in_batch}")
                return False
                
            # Verify total_files = 1000000
            if total_files != 1000000:
                self.log_result("4. Total Files", False, f"Expected total_files = 1000000, got {total_files}")
                return False
                
            # Verify total_batches > 1
            if total_batches <= 1:
                self.log_result("4. Total Batches", False, f"Expected total_batches > 1, got {total_batches}")
                return False
                
            self.log_result("4. Pipeline Batch 0", True, f"✅ Files in batch: {files_in_batch}, Total files: {total_files}, Total batches: {total_batches}")
            return True
            
        except Exception as e:
            self.log_result("4. Pipeline Batch 0", False, f"Exception: {str(e)}")
            return False
            
    def test_5_pipeline_batch_1(self):
        """Test 5: GET /api/galaxy-studio/pipeline/{build_id}?batch=1&batch_size=5000 — Verify files_in_batch = 5000 (procedural batch), has_more = true"""
        if not self.build_id:
            self.log_result("5. Pipeline Batch 1", False, "No build_id available")
            return False
            
        try:
            response = self.session.get(f"{BACKEND_URL}/pipeline/{self.build_id}?batch=1&batch_size=5000")
            if response.status_code != 200:
                self.log_result("5. Pipeline Batch 1", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            
            files_in_batch = data.get("files_in_batch", 0)
            has_more = data.get("has_more", False)
            
            # Verify files_in_batch = 5000 (procedural batch)
            if files_in_batch != 5000:
                self.log_result("5. Files in Batch", False, f"Expected files_in_batch = 5000, got {files_in_batch}")
                return False
                
            # Verify has_more = true
            if not has_more:
                self.log_result("5. Has More", False, f"Expected has_more = true, got {has_more}")
                return False
                
            self.log_result("5. Pipeline Batch 1", True, f"✅ Files in batch: {files_in_batch}, Has more: {has_more}")
            return True
            
        except Exception as e:
            self.log_result("5. Pipeline Batch 1", False, f"Exception: {str(e)}")
            return False
            
    def test_6_vault_zip_create(self):
        """Test 6: POST /api/galaxy-studio/vault/zip/{build_id} — Verify creates ZIP, returns vault_id, size, download_url"""
        if not self.build_id:
            self.log_result("6. Vault ZIP Create", False, "No build_id available")
            return False
            
        try:
            response = self.session.post(f"{BACKEND_URL}/vault/zip/{self.build_id}")
            if response.status_code != 200:
                self.log_result("6. Vault ZIP Create", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            
            # Verify required fields
            vault_id = data.get("vault_id")
            size = data.get("size")
            size_bytes = data.get("size_bytes", 0)
            download_url = data.get("download_url")
            
            if not vault_id:
                self.log_result("6. Vault ID", False, "No vault_id returned")
                return False
                
            if not size or size_bytes <= 0:
                self.log_result("6. ZIP Size", False, f"Invalid size: {size} ({size_bytes} bytes)")
                return False
                
            if not download_url:
                self.log_result("6. Download URL", False, "No download_url returned")
                return False
                
            self.vault_id = vault_id
            self.log_result("6. Vault ZIP Create", True, f"✅ Vault ID: {vault_id}, Size: {size} bytes, Download URL: {download_url}")
            return True
            
        except Exception as e:
            self.log_result("6. Vault ZIP Create", False, f"Exception: {str(e)}")
            return False
            
    def test_7_vault_list(self):
        """Test 7: GET /api/galaxy-studio/vault — Verify lists at least 1 zip entry with download_url"""
        try:
            response = self.session.get(f"{BACKEND_URL}/vault")
            if response.status_code != 200:
                self.log_result("7. Vault List", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            
            # Verify vault entries
            vault_entries = data.get("zips", [])
            if len(vault_entries) < 1:
                self.log_result("7. Vault Entries", False, f"Expected at least 1 vault entry, got {len(vault_entries)}")
                return False
                
            # Verify at least one entry has download_url
            has_download_url = False
            for entry in vault_entries:
                if entry.get("download_url"):
                    has_download_url = True
                    break
                    
            if not has_download_url:
                self.log_result("7. Download URL", False, "No vault entry has download_url")
                return False
                
            self.log_result("7. Vault List", True, f"✅ Found {len(vault_entries)} vault entries with download URLs")
            return True
            
        except Exception as e:
            self.log_result("7. Vault List", False, f"Exception: {str(e)}")
            return False
            
    def test_8_vault_download(self):
        """Test 8: GET /api/galaxy-studio/vault/download/{vault_id} — Verify returns binary ZIP file (check content-type or first bytes)"""
        if not self.vault_id:
            self.log_result("8. Vault Download", False, "No vault_id available")
            return False
            
        try:
            response = self.session.get(f"{BACKEND_URL}/vault/download/{self.vault_id}")
            if response.status_code != 200:
                self.log_result("8. Vault Download", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            # Check content-type
            content_type = response.headers.get("content-type", "")
            if "application/zip" not in content_type and "application/octet-stream" not in content_type:
                # Check first bytes for ZIP signature
                content = response.content
                if len(content) < 4 or content[:4] != b'PK\x03\x04':
                    self.log_result("8. ZIP Format", False, f"Not a ZIP file. Content-type: {content_type}, First bytes: {content[:10]}")
                    return False
                    
            content_length = len(response.content)
            if content_length < 1000:  # Should be substantial
                self.log_result("8. ZIP Size", False, f"ZIP file too small: {content_length} bytes")
                return False
                
            self.log_result("8. Vault Download", True, f"✅ ZIP download successful: {content_length} bytes, content-type: {content_type}")
            return True
            
        except Exception as e:
            self.log_result("8. Vault Download", False, f"Exception: {str(e)}")
            return False
            
    def test_9_expand_build(self):
        """Test 9: POST /api/galaxy-studio/expand — Body: {"build_id":"<id>","expansion_type":"all","scale":"large","description":"Dark Abyss DLC"} — Verify files_added > 0, total_files increased"""
        if not self.build_id:
            self.log_result("9. Expand Build", False, "No build_id available")
            return False
            
        try:
            # First get current file count
            status_response = self.session.get(f"{BACKEND_URL}/status/{self.build_id}")
            if status_response.status_code != 200:
                self.log_result("9. Get Current Status", False, f"HTTP {status_response.status_code}")
                return False
                
            current_data = status_response.json()
            current_files = current_data.get("file_count", 0)
            
            # Now expand the build
            payload = {
                "build_id": self.build_id,
                "expansion_type": "all",
                "scale": "large", 
                "description": "Dark Abyss DLC"
            }
            
            response = self.session.post(f"{BACKEND_URL}/expand", json=payload)
            if response.status_code != 200:
                self.log_result("9. Expand Build", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            
            files_added = data.get("files_added", 0)
            total_files = data.get("total_files", 0)
            
            # Verify files_added > 0
            if files_added <= 0:
                self.log_result("9. Files Added", False, f"Expected files_added > 0, got {files_added}")
                return False
                
            # Verify total_files increased
            if total_files <= current_files:
                self.log_result("9. Total Files Increased", False, f"Expected total_files to increase from {current_files}, got {total_files}")
                return False
                
            self.log_result("9. Expand Build", True, f"✅ Files added: {files_added}, Total files: {total_files} (increased from {current_files})")
            return True
            
        except Exception as e:
            self.log_result("9. Expand Build", False, f"Exception: {str(e)}")
            return False
            
    def test_10_zip_to_apk_error(self):
        """Test 10: POST /api/galaxy-studio/vault/zip-to-apk/{build_id} — Body: {"build_id":"<id>","expo_token":""} — Should return error about missing token (that's expected), verify it doesn't crash"""
        if not self.build_id:
            self.log_result("10. ZIP to APK Error", False, "No build_id available")
            return False
            
        try:
            payload = {
                "build_id": self.build_id,
                "expo_token": ""
            }
            
            response = self.session.post(f"{BACKEND_URL}/vault/zip-to-apk/{self.build_id}", json=payload)
            
            # Should not crash (500)
            if response.status_code == 500:
                self.log_result("10. ZIP to APK Error", False, f"Endpoint crashed with HTTP 500: {response.text}")
                return False
                
            # Check if it returns success (200) or error (400/401/422)
            if response.status_code == 200:
                data = response.json()
                # If it succeeds, it should have build info
                if "eas_build_id" in data or "status" in data:
                    self.log_result("10. ZIP to APK Error", True, f"✅ Endpoint works correctly: HTTP {response.status_code}, Status: {data.get('status', 'N/A')}")
                    return True
                else:
                    self.log_result("10. ZIP to APK Error", False, f"Unexpected success response: {data}")
                    return False
            elif response.status_code in [400, 401, 422]:
                data = response.json()
                error_message = data.get("error", "").lower()
                if "token" in error_message or "missing" in error_message or "required" in error_message:
                    self.log_result("10. ZIP to APK Error", True, f"✅ Expected error about missing token: HTTP {response.status_code}, {data.get('error', 'No error message')}")
                    return True
                else:
                    self.log_result("10. ZIP to APK Error", False, f"Unexpected error message: {data.get('error', 'No error message')}")
                    return False
            else:
                self.log_result("10. ZIP to APK Error", False, f"Unexpected status code: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("10. ZIP to APK Error", False, f"Exception: {str(e)}")
            return False
            
    def run_full_review_test(self):
        """Run the complete Galaxy Studio Factory review test sequence"""
        print("🚀 Starting Galaxy Studio Factory FULL Pipeline Review Testing")
        print("=" * 80)
        
        tests = [
            ("1. Manifest (version 3.0 UNLIMITED, scale_parsing, file_limit NONE)", self.test_1_manifest),
            ("2. Create TITAN Build (1M assets, 100GB, dark fantasy RPG)", self.test_2_create_titan_build),
            ("3. Advance 12 Phases (status completed, file_count > 500)", self.test_3_advance_12_phases),
            ("4. Pipeline Batch 0 (files_in_batch > 500, total_files = 1M, batches > 1)", self.test_4_pipeline_batch_0),
            ("5. Pipeline Batch 1 (files_in_batch = 5000, has_more = true)", self.test_5_pipeline_batch_1),
            ("6. Vault ZIP Create (vault_id, size, download_url)", self.test_6_vault_zip_create),
            ("7. Vault List (at least 1 entry with download_url)", self.test_7_vault_list),
            ("8. Vault Download (binary ZIP file)", self.test_8_vault_download),
            ("9. Expand Build (files_added > 0, total_files increased)", self.test_9_expand_build),
            ("10. ZIP to APK Error (missing token error, no crash)", self.test_10_zip_to_apk_error),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n🧪 Testing: {test_name}")
            if test_func():
                passed += 1
            else:
                print(f"   ❌ {test_name} FAILED")
                
        print("\n" + "=" * 80)
        print(f"🎯 GALAXY STUDIO FACTORY REVIEW TEST RESULTS: {passed}/{total} PASSED ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 ALL REVIEW TESTS PASSED! Galaxy Studio Factory FULL pipeline is operational.")
        else:
            print(f"⚠️  {total - passed} tests failed. Review the issues above.")
            
        return passed == total

def main():
    """Main test runner"""
    tester = GalaxyStudioReviewTester()
    success = tester.run_full_review_test()
    
    if success:
        print("\n✅ REVIEW REQUIREMENTS CONFIRMED:")
        print("   • Manifest shows version 3.0 UNLIMITED with scale_parsing and NONE file_limit")
        print("   • Create TITAN build with 1M assets, 100GB scale parsing")
        print("   • All 12 phases advance successfully with file_count > 500")
        print("   • Pipeline batching works with 1M total files")
        print("   • Vault system creates, lists, and downloads ZIP files")
        print("   • Expand functionality adds files and increases total count")
        print("   • ZIP-to-APK properly handles missing token without crashing")
    
    return success

if __name__ == "__main__":
    main()