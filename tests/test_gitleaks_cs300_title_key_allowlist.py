"""The CS-300 TITLE_KEY allowlist in .gitleaks.toml must stay narrow.

Gitleaks' default generic-api-key rule flagged the CS-300 layer title
constants under skeleton/cs300/layers/ on main. The exception only covers
snake_case title constants in generated CS-300 layer modules; real
credentials elsewhere or with token-like values must still be reported.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ROOT / "skeleton" / "cs300" / "layers"
TITLE_ASSIGNMENT = "TITLE_" + "KEY"


def _cs300_allowlist() -> dict:
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    matches = [
        allow
        for rule in config.get("rules", [])
        if rule.get("id") == "generic-api-key"
        for allow in rule.get("allowlists", [])
        if any("cs300" in p for p in allow.get("paths", []))
    ]
    assert len(matches) == 1, matches
    return matches[0]


def test_allowlist_requires_both_path_and_line() -> None:
    allow = _cs300_allowlist()
    assert allow["condition"] == "AND"
    assert allow["regexTarget"] == "line"
    assert len(allow["regexes"]) == 1
    assert len(allow["paths"]) == 1


def test_allowlist_covers_every_layer_title_key() -> None:
    allow = _cs300_allowlist()
    line_re = re.compile(allow["regexes"][0])
    path_re = re.compile(allow["paths"][0])
    layer_files = sorted(LAYERS.glob("l[0-9][0-9][0-9].py"))
    assert layer_files
    for path in layer_files:
        rel = path.relative_to(ROOT).as_posix()
        assert path_re.search(rel), rel
        title_lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith(TITLE_ASSIGNMENT)
        ]
        assert len(title_lines) == 1, rel
        assert line_re.search(title_lines[0]), (rel, title_lines[0])


def test_allowlist_rejects_token_like_values_and_other_paths() -> None:
    allow = _cs300_allowlist()
    line_re = re.compile(allow["regexes"][0])
    path_re = re.compile(allow["paths"][0])
    assignment = TITLE_ASSIGNMENT
    snake = "cs_" + "300" + "_signed_finality"
    # A well-formed snake_case title assignment is exactly what the allowlist
    # permits; token-like values must still be rejected.
    assert line_re.search(f'{assignment} = "{snake}"')
    for value in (
        "AKIAQ3EGVZ7X9ExampleKeyValue0",
        "sk-live-4f9Qz2Lk8Pq7Rt6Yu5Io",
    ):
        assert not line_re.search(f'{assignment} = "{value}"'), value
    for rel in (
        "skeleton/cs300/l300.py",
        "skeleton/cs300/layers/sub/l300.py",
        "skeleton/cs300/layers/l3000.py",
        "backend/skeleton/cs300/layers/l300.py",
    ):
        assert not path_re.search(rel), rel
    assert not line_re.search(f'  {assignment} = "{snake}"')
    assert not line_re.search(f'{assignment} = "{snake}" ; API_KEY = "x"')
