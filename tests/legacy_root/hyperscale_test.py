#!/usr/bin/env python3
"""
Backend API Testing for v25.0 Hyperscale Domains
Testing all hyperscale endpoints as requested
"""

import requests
import json
import time
from typing import Dict, Any, Optional

# Backend URL from frontend/.env
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com/api"

class HyperscaleTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'HyperscaleTester/1.0'
        })
        self.results = []
        
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
                if expected_status == 404:
                    self.log_result(test_name, True, f"Correctly returned 404 as expected")
                    return {"success": True, "data": "404_as_expected"}
                    
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
                self.log_result(test_name, False, f"HTTP {response.status_code}: {response.text}")
                return {"success": False, "data": response.text}
                
        except requests.exceptions.Timeout:
            self.log_result(test_name, False, "Request timeout (30s)")
            return {"success": False, "data": "timeout"}
        except requests.exceptions.RequestException as e:
            self.log_result(test_name, False, f"Request error: {str(e)}")
            return {"success": False, "data": str(e)}
    
    def test_hyperscale_status(self):
        """Test 1: GET /api/hyperscale/status"""
        result = self.test_endpoint(
            "GET", "/hyperscale/status",
            expected_fields=["total_domains", "total_specialists", "total_expertise_points", "total_synergy_connections", "categories"],
            test_name="Hyperscale - Get Status"
        )
        
        if result["success"]:
            data = result["data"]
            domains = data.get("total_domains", 0)
            specialists = data.get("total_specialists", 0)
            expertise = data.get("total_expertise_points", 0)
            connections = data.get("total_synergy_connections", 0)
            categories = data.get("categories", {})
            
            # Verify expected counts
            if domains == 300:
                self.log_result("Hyperscale - Domain Count", True, f"Found {domains} domains (expected 300)")
            else:
                self.log_result("Hyperscale - Domain Count", False, f"Expected 300 domains, got {domains}")
                
            if specialists == 2400:
                self.log_result("Hyperscale - Specialist Count", True, f"Found {specialists} specialists (expected 2400)")
            else:
                self.log_result("Hyperscale - Specialist Count", False, f"Expected 2400 specialists, got {specialists}")
                
            if expertise == 19200:
                self.log_result("Hyperscale - Expertise Points", True, f"Found {expertise} expertise points (expected 19200)")
            else:
                self.log_result("Hyperscale - Expertise Points", False, f"Expected 19200 expertise points, got {expertise}")
                
            if connections == 635:
                self.log_result("Hyperscale - Synergy Connections", True, f"Found {connections} synergy connections (expected 635)")
            else:
                self.log_result("Hyperscale - Synergy Connections", False, f"Expected 635 synergy connections, got {connections}")
                
            if len(categories) == 10:
                self.log_result("Hyperscale - Categories Count", True, f"Found {len(categories)} categories (expected 10)")
                
                # Check if each category has 30 domains
                all_have_30 = all(len(cat_data.get("domains", [])) == 30 for cat_data in categories.values())
                if all_have_30:
                    self.log_result("Hyperscale - Domains per Category", True, "All 10 categories have 30 domains each")
                else:
                    domain_counts = {cat: len(cat_data.get("domains", [])) for cat, cat_data in categories.items()}
                    self.log_result("Hyperscale - Domains per Category", False, f"Not all categories have 30 domains: {domain_counts}")
            else:
                self.log_result("Hyperscale - Categories Count", False, f"Expected 10 categories, got {len(categories)}")
        
        return result
    
    def test_hyperscale_core_design_category(self):
        """Test 2: GET /api/hyperscale/category/core_design"""
        result = self.test_endpoint(
            "GET", "/hyperscale/category/core_design",
            expected_fields=["category", "domains"],
            test_name="Hyperscale - Get Core Design Category"
        )
        
        if result["success"]:
            data = result["data"]
            domains = data.get("domains", [])
            
            if len(domains) == 30:
                self.log_result("Hyperscale - Core Design Domains", True, f"Found {len(domains)} domains (expected 30)")
                
                # Check if domains have specialist_names
                has_specialist_names = all("specialist_names" in domain for domain in domains)
                if has_specialist_names:
                    self.log_result("Hyperscale - Specialist Names", True, "All domains have specialist_names")
                else:
                    self.log_result("Hyperscale - Specialist Names", False, "Some domains missing specialist_names")
            else:
                self.log_result("Hyperscale - Core Design Domains", False, f"Expected 30 domains, got {len(domains)}")
        
        return result
    
    def test_hyperscale_art_visual_category(self):
        """Test 3: GET /api/hyperscale/category/art_visual"""
        result = self.test_endpoint(
            "GET", "/hyperscale/category/art_visual",
            expected_fields=["category", "domains"],
            test_name="Hyperscale - Get Art Visual Category"
        )
        
        if result["success"]:
            data = result["data"]
            domains = data.get("domains", [])
            
            if len(domains) == 30:
                self.log_result("Hyperscale - Art Visual Domains", True, f"Found {len(domains)} domains (expected 30)")
            else:
                self.log_result("Hyperscale - Art Visual Domains", False, f"Expected 30 domains, got {len(domains)}")
        
        return result
    
    def test_hyperscale_game_feel_domain(self):
        """Test 4: GET /api/hyperscale/domain/game_feel (hand-crafted domain)"""
        result = self.test_endpoint(
            "GET", "/hyperscale/domain/game_feel",
            expected_fields=["domain", "specialists"],
            test_name="Hyperscale - Get Game Feel Domain"
        )
        
        if result["success"]:
            data = result["data"]
            specialists = data.get("specialists", {})
            
            if len(specialists) == 8:
                self.log_result("Hyperscale - Game Feel Specialists", True, f"Found {len(specialists)} specialists (expected 8)")
                
                # Check if specialists have expertise arrays
                first_specialist = next(iter(specialists.values())) if specialists else {}
                has_expertise = "expertise" in first_specialist and isinstance(first_specialist["expertise"], list)
                
                if has_expertise:
                    self.log_result("Hyperscale - Expertise Arrays", True, "Specialists have expertise arrays")
                else:
                    self.log_result("Hyperscale - Expertise Arrays", False, "Specialists missing expertise arrays")
            else:
                self.log_result("Hyperscale - Game Feel Specialists", False, f"Expected 8 specialists, got {len(specialists)}")
        
        return result
    
    def test_hyperscale_tutorial_architect_domain(self):
        """Test 5: GET /api/hyperscale/domain/tutorial_architect (auto-generated domain)"""
        result = self.test_endpoint(
            "GET", "/hyperscale/domain/tutorial_architect",
            expected_fields=["domain", "specialists"],
            test_name="Hyperscale - Get Tutorial Architect Domain"
        )
        
        if result["success"]:
            data = result["data"]
            specialists = data.get("specialists", {})
            
            if len(specialists) == 8:
                self.log_result("Hyperscale - Tutorial Architect Specialists", True, f"Found {len(specialists)} specialists (expected 8)")
            else:
                self.log_result("Hyperscale - Tutorial Architect Specialists", False, f"Expected 8 specialists, got {len(specialists)}")
        
        return result
    
    def test_hyperscale_synergy_web(self):
        """Test 6: GET /api/hyperscale/synergy-web"""
        result = self.test_endpoint(
            "GET", "/hyperscale/synergy-web",
            expected_fields=["web", "total_connections"],
            test_name="Hyperscale - Get Synergy Web"
        )
        
        if result["success"]:
            data = result["data"]
            web = data.get("web", {})
            total_connections = data.get("total_connections", 0)
            
            if len(web) == 300:
                self.log_result("Hyperscale - Web Domains", True, f"Found {len(web)} domains in web (expected 300)")
            else:
                self.log_result("Hyperscale - Web Domains", False, f"Expected 300 domains in web, got {len(web)}")
                
            if total_connections == 635:
                self.log_result("Hyperscale - Total Connections", True, f"Found {total_connections} total connections (expected 635)")
            else:
                self.log_result("Hyperscale - Total Connections", False, f"Expected 635 total connections, got {total_connections}")
        
        return result
    
    def test_hyperscale_jeeves_synergy(self):
        """Test 7: GET /api/hyperscale/jeeves-synergy"""
        result = self.test_endpoint(
            "GET", "/hyperscale/jeeves-synergy",
            expected_fields=["jeeves", "total_domains", "total_specialists"],
            test_name="Hyperscale - Get Jeeves Synergy"
        )
        
        if result["success"]:
            data = result["data"]
            total_domains = data.get("total_domains", 0)
            total_specialists = data.get("total_specialists", 0)
            jeeves = data.get("jeeves", {})
            
            if total_domains == 300:
                self.log_result("Hyperscale - Jeeves Domains", True, f"Jeeves orchestrating {total_domains} domains (expected 300)")
            else:
                self.log_result("Hyperscale - Jeeves Domains", False, f"Expected Jeeves orchestrating 300 domains, got {total_domains}")
                
            if total_specialists == 2400:
                self.log_result("Hyperscale - Jeeves Specialists", True, f"Jeeves orchestrating {total_specialists} specialists (expected 2400)")
            else:
                self.log_result("Hyperscale - Jeeves Specialists", False, f"Expected Jeeves orchestrating 2400 specialists, got {total_specialists}")
                
            if jeeves:
                self.log_result("Hyperscale - Jeeves Data", True, "Jeeves orchestration data present")
            else:
                self.log_result("Hyperscale - Jeeves Data", False, "Missing Jeeves orchestration data")
        
        return result
    
    def test_hyperscale_invalid_domain(self):
        """Test 8: GET /api/hyperscale/domain/invalid_domain_xyz (should return 404)"""
        result = self.test_endpoint(
            "GET", "/hyperscale/domain/invalid_domain_xyz",
            test_name="Hyperscale - Invalid Domain (404 test)",
            expected_status=404
        )
        
        return result
    
    def test_regression_health(self):
        """Test 9: GET /api/health (regression test)"""
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
    
    def test_regression_quantum_factory(self):
        """Test 10: GET /api/quantum-factory/status (regression test)"""
        result = self.test_endpoint(
            "GET", "/quantum-factory/status",
            expected_fields=["domains", "total_specialists"],
            test_name="Regression - Quantum Factory Status"
        )
        
        if result["success"]:
            data = result["data"]
            domains = data.get("domains", 0)
            specialists = data.get("total_specialists", 0)
            
            if domains == 7:
                self.log_result("Regression - Quantum Factory Domains", True, f"Found {domains} domains (expected 7)")
            else:
                self.log_result("Regression - Quantum Factory Domains", False, f"Expected 7 domains, got {domains}")
                
            if specialists == 56:
                self.log_result("Regression - Quantum Factory Specialists", True, f"Found {specialists} specialists (expected 56)")
            else:
                self.log_result("Regression - Quantum Factory Specialists", False, f"Expected 56 specialists, got {specialists}")
        
        return result
    
    def run_all_tests(self):
        """Run all hyperscale tests in sequence"""
        print("🚀 Starting v25.0 Hyperscale Domains Backend Testing")
        print("=" * 60)
        
        # Hyperscale Tests
        print("\n🌐 HYPERSCALE DOMAINS TESTS")
        print("-" * 30)
        self.test_hyperscale_status()
        self.test_hyperscale_core_design_category()
        self.test_hyperscale_art_visual_category()
        self.test_hyperscale_game_feel_domain()
        self.test_hyperscale_tutorial_architect_domain()
        self.test_hyperscale_synergy_web()
        self.test_hyperscale_jeeves_synergy()
        self.test_hyperscale_invalid_domain()
        
        # Regression Tests
        print("\n🔄 REGRESSION TESTS")
        print("-" * 30)
        self.test_regression_health()
        self.test_regression_quantum_factory()
        
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
        
        print(f"\n🎯 v25.0 Hyperscale Domains Testing Complete!")
        return {
            'total': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'success_rate': success_rate,
            'results': self.results
        }

if __name__ == "__main__":
    tester = HyperscaleTester()
    summary = tester.run_all_tests()