#!/usr/bin/env python3
"""
Role-Seat Assignment Engine
Assigns 100 specialized roles to agent seats in each room based on category.
Ensures high-competency role cycling with coder style cross-references for quality control.
"""

import json
import os
from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class RoleSeat:
    seat_id: int
    role_id: str
    category: str
    name: str
    coder_style_references: List[Dict]
    competency_level: str
    quality_criteria: List[str]
    prompt_template: str

class RoleSeatAssignmentEngine:
    def __init__(self, roles_directory: str):
        self.roles_directory = roles_directory
        self.seats: Dict[str, List[RoleSeat]] = {}  # category -> list of seats
        self.categories: List[str] = []
        
    def load_all_roles(self) -> Dict[str, List[Dict]]:
        """Load all role JSON files from the roles directory."""
        all_roles = {}
        for filename in os.listdir(self.roles_directory):
            if filename.endswith('.json'):
                filepath = os.path.join(self.roles_directory, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    category = data.get('room_category', 'unknown')
                    if category not in all_roles:
                        all_roles[category] = []
                    all_roles[category].extend(data.get('roles', []))
        return all_roles
    
    def assign_roles_to_seats(self, category: str, roles: List[Dict]) -> List[RoleSeat]:
        """Assign roles to 100 seats for a category."""
        seats = []
        # Take up to 100 roles (or cycle if fewer)
        role_count = len(roles)
        for i in range(100):
            role_index = i % role_count if role_count > 0 else 0
            role = roles[role_index]
            
            seat = RoleSeat(
                seat_id=i + 1,
                role_id=role.get('role_id', f'{category}_seat_{i+1}'),
                category=category,
                name=role.get('name', 'Unnamed Role'),
                coder_style_references=role.get('coder_style_references', []),
                competency_level=role.get('competency_level', 'expert'),
                quality_criteria=role.get('quality_criteria', []),
                prompt_template=role.get('prompt_template', '')
            )
            seats.append(seat)
        return seats
    
    def build_seat_system(self):
        """Build the complete seat assignment system for all categories."""
        print("Loading all role definitions...")
        all_roles = self.load_all_roles()
        self.categories = list(all_roles.keys())
        
        print(f"Found {len(self.categories)} categories. Assigning 100 seats per category...")
        
        for category in self.categories:
            roles = all_roles[category]
            seats = self.assign_roles_to_seats(category, roles)
            self.seats[category] = seats
            print(f"  - {category}: {len(seats)} seats assigned")
        
        print(f"\nSeat assignment complete. Total categories: {len(self.categories)}")
        print(f"Total seats across all categories: {sum(len(s) for s in self.seats.values())}")
    
    def get_seat_for_category(self, category: str, seat_number: int) -> RoleSeat:
        """Get a specific seat for a category."""
        if category not in self.seats:
            raise ValueError(f"Category {category} not found")
        return self.seats[category][seat_number - 1]
    
    def export_seat_manifest(self, output_path: str):
        """Export the complete seat assignment manifest."""
        manifest = {
            "total_categories": len(self.categories),
            "seats_per_category": 100,
            "categories": self.categories,
            "seat_assignments": {}
        }
        
        for category, seats in self.seats.items():
            manifest["seat_assignments"][category] = [
                {
                    "seat_id": seat.seat_id,
                    "role_id": seat.role_id,
                    "name": seat.name,
                    "coder_style_references": seat.coder_style_references,
                    "competency_level": seat.competency_level,
                    "quality_criteria": seat.quality_criteria
                }
                for seat in seats
            ]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        print(f"Seat manifest exported to {output_path}")

if __name__ == "__main__":
    engine = RoleSeatAssignmentEngine(
        roles_directory="/home/workdir/artifacts/gameforge_v1/gameforge/roles/role_sets"
    )
    engine.build_seat_system()
    engine.export_seat_manifest(
        "/home/workdir/artifacts/gameforge_v1/gameforge/roles/seat_assignment_system/role_seat_manifest.json"
    )
    print("\nRole-Seat Assignment Engine initialized successfully.")