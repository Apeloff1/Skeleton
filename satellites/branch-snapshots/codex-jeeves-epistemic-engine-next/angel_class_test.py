#!/usr/bin/env python3
"""
Angel Class Layer Testing for Tutolage Game Factory
Testing all Angel Class endpoints and regression tests
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Backend URL from environment
BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com/api"

class AngelClassTester:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
        
    def log_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append(f"{status} - {test_name}: {details}")
        if passed:
            self.passed += 1
        else:
            self.failed += 1
            
    def test_endpoint(self, endpoint: str, expected_status: int = 200) -> Dict[Any, Any]:
        """Test an endpoint and return response data"""
        try:
            url = f"{BACKEND_URL}{endpoint}"
            print(f"Testing: {url}")
            response = requests.get(url, timeout=30)
            
            if response.status_code != expected_status:
                self.log_result(f"GET {endpoint}", False, f"Status {response.status_code}, expected {expected_status}")
                return {}
                
            data = response.json()
            self.log_result(f"GET {endpoint}", True, f"Status {response.status_code}")
            return data
            
        except requests.exceptions.RequestException as e:
            self.log_result(f"GET {endpoint}", False, f"Request failed: {str(e)}")
            return {}
        except json.JSONDecodeError as e:
            self.log_result(f"GET {endpoint}", False, f"JSON decode failed: {str(e)}")
            return {}

    def test_angel_class_info(self):
        """Test GET /api/game-factory/angel-class"""
        print("\n1. Testing angel-class endpoint...")
        angel_data = self.test_endpoint("/game-factory/angel-class")
        
        if angel_data:
            # Check total angels
            total_angels = angel_data.get('total_angels', 0)
            print(f"   Total angels: {total_angels} (expected: ~4326)")
            
            if 4300 <= total_angels <= 4350:
                self.log_result("Total angels count", True, f"Correct: {total_angels}")
            else:
                self.log_result("Total angels count", False, f"Got {total_angels}, expected ~4326")
            
            # Check by_layer structure
            by_layer = angel_data.get('by_layer', {})
            if by_layer:
                print(f"   By layer structure: {by_layer}")
                
                # Check each layer
                expected_layers = ['original', 'shadow', 'ghost']
                for layer in expected_layers:
                    if layer in by_layer:
                        count = by_layer[layer]
                        print(f"   {layer} angels: {count} (expected: ~1442)")
                        if 1400 <= count <= 1500:
                            self.log_result(f"Angel {layer} layer count", True, f"Correct: {count}")
                        else:
                            self.log_result(f"Angel {layer} layer count", False, f"Got {count}, expected ~1442")
                    else:
                        self.log_result(f"Angel {layer} layer", False, f"Layer {layer} not found")
            else:
                self.log_result("By layer structure", False, "No by_layer found in response")
            
            # Check 7-step protocol
            protocol = angel_data.get('protocol', [])
            if protocol:
                # Handle both list and dict structures
                if isinstance(protocol, list):
                    steps = protocol
                else:
                    steps = protocol.get('steps', [])
                print(f"   Protocol steps: {len(steps)} (expected: 7)")
                if len(steps) == 7:
                    self.log_result("Protocol steps count", True, f"Correct: {len(steps)}")
                else:
                    self.log_result("Protocol steps count", False, f"Got {len(steps)}, expected 7")
            else:
                self.log_result("Protocol structure", False, "No protocol found in response")
            
            # Check 20 complexity focuses
            complexity_focuses = angel_data.get('complexity_focuses', [])
            print(f"   Complexity focuses: {len(complexity_focuses)} (expected: 20)")
            if len(complexity_focuses) == 20:
                self.log_result("Complexity focuses count", True, f"Correct: {len(complexity_focuses)}")
            else:
                self.log_result("Complexity focuses count", False, f"Got {len(complexity_focuses)}, expected 20")

    def test_angel_agents_list(self):
        """Test GET /api/game-factory/angel-agents?limit=5"""
        print("\n2. Testing angel-agents endpoint (limit=5)...")
        agents_data = self.test_endpoint("/game-factory/angel-agents?limit=5")
        
        if agents_data:
            agents = agents_data.get('angels', [])  # Changed from 'agents' to 'angels'
            print(f"   Agents returned: {len(agents)} (expected: 5)")
            
            if len(agents) == 5:
                self.log_result("Angel agents limit", True, f"Correct: {len(agents)}")
                
                # Check each agent has required fields
                for i, agent in enumerate(agents):
                    agent_name = agent.get('name', f'Agent {i+1}')
                    
                    if 'complexity_focus' in agent:
                        self.log_result(f"Agent {agent_name} complexity_focus", True, f"Found: {agent['complexity_focus']}")
                    else:
                        self.log_result(f"Agent {agent_name} complexity_focus", False, "Missing complexity_focus field")
                    
                    if 'layer' in agent:
                        self.log_result(f"Agent {agent_name} layer", True, f"Found: {agent['layer']}")
                    else:
                        self.log_result(f"Agent {agent_name} layer", False, "Missing layer field")
            else:
                self.log_result("Angel agents limit", False, f"Got {len(agents)}, expected 5")

    def test_angel_agents_shadow_filter(self):
        """Test GET /api/game-factory/angel-agents?limit=5&layer=shadow"""
        print("\n3. Testing angel-agents endpoint (shadow layer filter)...")
        shadow_data = self.test_endpoint("/game-factory/angel-agents?limit=5&layer=shadow")
        
        if shadow_data:
            agents = shadow_data.get('angels', [])  # Changed from 'agents' to 'angels'
            print(f"   Shadow agents returned: {len(agents)} (expected: 5)")
            
            if len(agents) == 5:
                self.log_result("Shadow angel agents limit", True, f"Correct: {len(agents)}")
                
                # Check all agents are shadow layer
                all_shadow = True
                for agent in agents:
                    layer = agent.get('layer', '')
                    if layer != 'shadow':
                        all_shadow = False
                        break
                
                if all_shadow:
                    self.log_result("Shadow layer filter", True, "All agents are shadow layer")
                else:
                    self.log_result("Shadow layer filter", False, "Not all agents are shadow layer")
            else:
                self.log_result("Shadow angel agents limit", False, f"Got {len(agents)}, expected 5")

    def test_angel_for_emperor(self):
        """Test GET /api/game-factory/angel-for/emperor"""
        print("\n4. Testing angel-for/emperor endpoint...")
        emperor_data = self.test_endpoint("/game-factory/angel-for/emperor")
        
        if emperor_data:
            # Handle nested structure - angel is inside the response
            angel = emperor_data.get('angel', {})
            name = angel.get('name', '') if angel else emperor_data.get('name', '')
            print(f"   Angel name: {name} (expected: Angel-Emperor)")
            
            if 'Angel-Emperor' in name or 'angel-emperor' in name.lower():
                self.log_result("Angel-Emperor name", True, f"Correct: {name}")
            else:
                self.log_result("Angel-Emperor name", False, f"Got {name}, expected Angel-Emperor")
            
            # Check complexity_focus field
            complexity_focus_source = angel if angel else emperor_data
            if 'complexity_focus' in complexity_focus_source:
                complexity_focus = complexity_focus_source['complexity_focus']
                self.log_result("Angel-Emperor complexity_focus", True, f"Found: {complexity_focus}")
            else:
                self.log_result("Angel-Emperor complexity_focus", False, "Missing complexity_focus field")

    def test_quad_layer_emperor(self):
        """Test GET /api/game-factory/quad-layer/emperor"""
        print("\n5. Testing quad-layer/emperor endpoint...")
        quad_data = self.test_endpoint("/game-factory/quad-layer/emperor")
        
        if quad_data:
            # Check quad_layer_complete flag
            quad_complete = quad_data.get('quad_layer_complete', False)
            print(f"   Quad layer complete: {quad_complete} (expected: true)")
            
            if quad_complete:
                self.log_result("Quad layer complete", True, f"Correct: {quad_complete}")
            else:
                self.log_result("Quad layer complete", False, f"Got {quad_complete}, expected true")
            
            # Check all 4 layers
            layers = quad_data.get('layers', {})
            expected_layers = ['original', 'shadow', 'ghost']  # angels is handled separately
            
            print(f"   Layers found: {list(layers.keys())}")
            
            for layer in expected_layers:
                if layer in layers:
                    layer_data = layers[layer]
                    layer_name = layer_data.get('name', 'N/A') if isinstance(layer_data, dict) else str(layer_data)
                    self.log_result(f"Quad layer {layer}", True, f"Found: {layer_name}")
                else:
                    self.log_result(f"Quad layer {layer}", False, f"Layer {layer} not found")
            
            # Check angels array (special case)
            angels = layers.get('angels', [])
            if angels and len(angels) >= 3:  # Should have 3 angels (for original, shadow, ghost)
                self.log_result("Quad layer angels", True, f"Found: {len(angels)} angels")
            else:
                self.log_result("Quad layer angels", False, f"Expected 3 angels, got {len(angels) if angels else 0}")

    def test_all_agents_summary_angels(self):
        """Test GET /api/game-factory/all-agents-summary for angel data"""
        print("\n6. Testing all-agents-summary endpoint (angel focus)...")
        summary_data = self.test_endpoint("/game-factory/all-agents-summary")
        
        if summary_data:
            # Check grand_total_with_all_layers
            grand_total_all = summary_data.get('grand_total_with_all_layers', 0)
            print(f"   Grand total with all layers: {grand_total_all} (expected: ~8690)")
            
            if 8600 <= grand_total_all <= 8800:
                self.log_result("Grand total with all layers", True, f"Correct: {grand_total_all}")
            else:
                self.log_result("Grand total with all layers", False, f"Got {grand_total_all}, expected ~8690")
            
            # Check breakdown for angel_agents
            breakdown = summary_data.get('breakdown', {})
            if breakdown:
                angel_agents = breakdown.get('angel_agents', 0)
                print(f"   Angel agents in breakdown: {angel_agents} (expected: ~4326)")
                
                if 4300 <= angel_agents <= 4350:
                    self.log_result("Breakdown angel agents", True, f"Correct: {angel_agents}")
                else:
                    self.log_result("Breakdown angel agents", False, f"Got {angel_agents}, expected ~4326")
            else:
                self.log_result("Breakdown structure", False, "No breakdown found in response")
            
            # Check quality_layers has 4 entries (originals, shadows, ghosts, angels)
            quality_layers = summary_data.get('quality_layers', {})
            if quality_layers:
                layer_count = len(quality_layers)
                print(f"   Quality layers count: {layer_count} (expected: 4)")
                
                if layer_count == 4:
                    self.log_result("Quality layers count", True, f"Correct: {layer_count}")
                    
                    # Check for angels layer specifically
                    if 'angels' in quality_layers:
                        angels_count = quality_layers['angels']
                        self.log_result("Angels quality layer", True, f"Found: {angels_count}")
                    else:
                        self.log_result("Angels quality layer", False, "Angels layer not found in quality_layers")
                else:
                    self.log_result("Quality layers count", False, f"Got {layer_count}, expected 4")
            else:
                self.log_result("Quality layers structure", False, "No quality_layers found in response")

    def test_regression_endpoints(self):
        """Test regression endpoints"""
        print("\n🔄 TESTING REGRESSION ENDPOINTS")
        print("=" * 50)
        
        # 7. Test pipeline endpoint
        print("\n7. Testing pipeline endpoint...")
        pipeline_data = self.test_endpoint("/game-factory/pipeline")
        
        if pipeline_data:
            steps = pipeline_data.get('total_steps', 0)
            print(f"   Pipeline steps: {steps} (expected: 200)")
            
            if steps == 200:
                self.log_result("Pipeline steps count", True, f"Correct: {steps}")
            else:
                self.log_result("Pipeline steps count", False, f"Got {steps}, expected 200")

        # 8. Test genres endpoint
        print("\n8. Testing genres endpoint...")
        genres_data = self.test_endpoint("/game-factory/genres")
        
        if genres_data:
            genre_count = len(genres_data.get('genres', []))
            print(f"   Genres count: {genre_count} (expected: 52)")
            
            if genre_count == 52:
                self.log_result("Genres count", True, f"Correct: {genre_count}")
            else:
                self.log_result("Genres count", False, f"Got {genre_count}, expected 52")

        # 9. Test parallel-society endpoint
        print("\n9. Testing parallel-society endpoint...")
        parallel_data = self.test_endpoint("/game-factory/parallel-society")
        
        if parallel_data:
            shadow_count = parallel_data.get('shadow_agents', 0)
            print(f"   Shadow agents: {shadow_count} (expected: ~1442)")
            
            if 1400 <= shadow_count <= 1500:
                self.log_result("Parallel society shadow count", True, f"Correct: {shadow_count}")
            else:
                self.log_result("Parallel society shadow count", False, f"Got {shadow_count}, expected ~1442")

        # 10. Test ghost-society endpoint
        print("\n10. Testing ghost-society endpoint...")
        ghost_data = self.test_endpoint("/game-factory/ghost-society")
        
        if ghost_data:
            ghost_count = ghost_data.get('ghost_agents', 0)
            print(f"   Ghost agents: {ghost_count} (expected: ~1442)")
            
            if 1400 <= ghost_count <= 1500:
                self.log_result("Ghost society ghost count", True, f"Correct: {ghost_count}")
            else:
                self.log_result("Ghost society ghost count", False, f"Got {ghost_count}, expected ~1442")

    def run_all_tests(self):
        """Run all Angel Class tests"""
        print("🎯 ANGEL CLASS LAYER BACKEND API TESTING")
        print("=" * 60)
        print(f"Backend URL: {BACKEND_URL}")
        print("=" * 60)
        
        # Test Angel Class endpoints
        print("\n👼 TESTING ANGEL CLASS ENDPOINTS")
        print("=" * 50)
        
        self.test_angel_class_info()
        self.test_angel_agents_list()
        self.test_angel_agents_shadow_filter()
        self.test_angel_for_emperor()
        self.test_quad_layer_emperor()
        self.test_all_agents_summary_angels()
        
        # Test regression endpoints
        self.test_regression_endpoints()
        
        # Print summary
        print("\n" + "=" * 60)
        print("🎯 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        for result in self.results:
            print(result)
            
        print(f"\n📊 FINAL RESULTS: {self.passed}/{self.passed + self.failed} tests passed ({(self.passed/(self.passed + self.failed)*100):.1f}% success rate)")
        
        if self.failed > 0:
            print(f"❌ {self.failed} tests failed")
            return False
        else:
            print("✅ All tests passed!")
            return True

if __name__ == "__main__":
    tester = AngelClassTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)