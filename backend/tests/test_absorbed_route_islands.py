from pathlib import Path


def test_absorbed_duplicate_route_modules_stay_retired():
    routes_dir = Path(__file__).resolve().parents[1] / "routes"
    retired = {
        "academy.py": "academy v2 was absorbed by academy_v3 + legacy compat",
        "quality_polish_api.py": "polish transport was absorbed by quality_control",
    }
    present = {name: reason for name, reason in retired.items() if (routes_dir / name).exists()}
    assert present == {}, f"absorbed route islands reintroduced: {present}"
