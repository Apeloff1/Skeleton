"""Upstream-tag-bound setup-uv CI identity; does not validate local uv binaries."""
from pathlib import Path

from scripts.check_toolchain_contract import pinned_action_count

ROOT = Path(__file__).resolve().parents[1]
PIN = "astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3"


def test_ci_uv_action_uses_verified_release_pin_exactly_three_times():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert ci.count(PIN) == 3
    assert ci.count("astral-sh/setup-uv@") == 3
    assert pinned_action_count(ci, "astral-sh/setup-uv", "v10.3.3") == 3


def test_old_uv_release_or_unverified_sha_cannot_qualify():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    altered = ci.replace(PIN, "astral-sh/setup-uv@" + "0" * 40 + " # v10.3.3", 1)
    assert altered.count(PIN) != 3
    assert altered.count("astral-sh/setup-uv@") == 3
    legacy = ci.replace(PIN, "astral-sh/setup-uv@07a047e608db84b3d8c06cd9a7c7dcc9c355c18e # v10.3.2")
    assert pinned_action_count(legacy, "astral-sh/setup-uv", "v10.3.3") == 0
