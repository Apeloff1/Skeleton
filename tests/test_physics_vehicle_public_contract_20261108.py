"""Deterministic vehicle public exports and mirrored-source custody."""
from pathlib import Path

def test_vehicle_types_are_exported_at_physics_boundary():
    from skeleton.simulation import physics
    from skeleton.simulation.physics import vehicle
    for name in ("RaycastVehicle", "VehicleSettings", "WheelSettings",
                 "VehicleControl", "VehicleState", "VehicleUpdateResult",
                 "WheelContact", "step_vehicles", "MAX_VEHICLE_WHEELS"):
        assert getattr(physics, name) is getattr(vehicle, name), name

def test_ai_mirror_retains_exact_canonical_public_surface():
    root = Path(__file__).resolve().parents[1]
    canonical = root / "skeleton/simulation/physics/__init__.py"
    mirror = root / "skeleton/ai/simulation/physics/__init__.py"
    assert canonical.read_bytes() == mirror.read_bytes()
