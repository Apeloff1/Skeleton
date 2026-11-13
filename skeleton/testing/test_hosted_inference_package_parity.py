"""Packaging parity for the optional hosted inference SDK.

The optional extra remains on the backend-compatible 2.x line until the
provider stack and its regression tests qualify a 3.x migration.
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


def test_hosted_sdk_floor_matches_current_backend_compatible_major() -> None:
    """Do not advertise a v3 upgrade before the backend provider graph migrates."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = _sdk_requirement(pyproject["project"]["optional-dependencies"][EXTRA])
    assert requirement == "openai>=2.54.0,<3", requirement
    backend = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8").splitlines()
    pinned = [line.strip() for line in backend if line.strip().startswith("openai==")]
    assert pinned == ["openai==2.54.0"], pinned
