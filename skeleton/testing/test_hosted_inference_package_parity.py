"""Packaging parity for the optional hosted inference SDK.

This test does not imply that OpenAI SDK v3 is runtime-compatible; it prevents
the two supported packaging metadata sources from declaring conflicting
major-version guarantees.
"""
from __future__ import annotations

import configparser
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXTRA = "hosted-inference"


def _sdk_requirement(items: list[str]) -> str:
    matches = [x.strip() for x in items if x.strip().lower().startswith("openai>=")]
    assert len(matches) == 1, f"expected exactly one OpenAI requirement, found {matches!r}"
    return matches[0]


def test_hosted_inference_sdk_requirements_match() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    cfg = configparser.ConfigParser(interpolation=None)
    assert cfg.read(ROOT / "setup.cfg", encoding="utf-8")
    pyreqs = pyproject["project"]["optional-dependencies"][EXTRA]
    cfgreqs = cfg["options.extras_require"][EXTRA].splitlines()
    assert _sdk_requirement(pyreqs) == _sdk_requirement(cfgreqs)


def test_hosted_sdk_major_upgrade_uses_one_consistent_v3_floor() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = _sdk_requirement(pyproject["project"]["optional-dependencies"][EXTRA])
    assert requirement == "openai>=3.37.0,<4", requirement
