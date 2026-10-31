"""Ensure Dependabot does not bundle Expo-incompatible core jumps with navigation."""
from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / ".github" / "dependabot.yml"
COUPLED = (
    "react", "react-dom", "react-native", "@types/react",
    "react-native-reanimated", "react-native-worklets",
    "@react-native-community/netinfo",
    "@react-native-community/slider", "react-native-webview",
)
NAVIGATION = (
    "@react-navigation/native", "@react-navigation/native-stack",
    "@react-navigation/bottom-tabs", "@react-navigation/elements",
)


def _frontend_config() -> dict:
    document = yaml.safe_load(FRONTEND.read_text(encoding="utf-8"))
    frontend = [
        item for item in document["updates"]
        if item.get("package-ecosystem") == "npm"
        and item.get("directory") == "/frontend"
    ]
    assert len(frontend) == 1, "exactly one frontend update entry is required"
    return frontend[0]


def _matches(group: dict, name: str) -> bool:
    patterns = group.get("patterns", [])
    excluded = group.get("exclude-patterns", [])
    return any(fnmatchcase(name, rule) for rule in patterns) and not any(
        fnmatchcase(name, rule) for rule in excluded
    )


def test_native_runtime_and_navigation_group_assignments_do_not_overlap() -> None:
    config = _frontend_config()
    groups = config["groups"]
    assert all(key in groups for key in (
        "frontend-expo-platform",
        "frontend-react-core",
        "frontend-native-modules",
        "frontend-react-navigation",
        "frontend-runtime",
    ))
    specific = {key: value for key, value in groups.items()
                if key in ("frontend-react-core", "frontend-native-modules", "frontend-react-navigation")}
    for dependency in (*COUPLED, *NAVIGATION):
        matches = [name for name, group in specific.items() if _matches(group, dependency)]
        assert len(matches) == 1, (dependency, matches)
        expected = (
            "frontend-react-navigation" if dependency in NAVIGATION else
            "frontend-react-core" if dependency in ("react", "react-dom", "react-native", "@types/react")
            else "frontend-native-modules"
        )
        assert matches == [expected], (dependency, matches, expected)
        assert not _matches(groups["frontend-runtime"], dependency)


def test_core_group_includes_dev_react_types_and_updates_stay_bounded() -> None:
    config = _frontend_config()
    groups = config["groups"]
    assert "dependency-type" not in groups["frontend-react-core"]
    for name in ("frontend-react-core", "frontend-native-modules", "frontend-react-navigation"):
        group = groups[name]
        assert group["applies-to"] == "version-updates"
        assert set(group["update-types"]) == {"minor", "patch"}
    assert config["open-pull-requests-limit"] >= 3
    assert set(config["allow"][0]["update-types"]) == {
        "version-update:semver-minor", "version-update:semver-patch"
    }
