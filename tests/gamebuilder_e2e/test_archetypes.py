"""Archetype selection (library + composed)."""
from __future__ import annotations

import pytest

from skeleton.forge.archetypes import default_library
from tests.gamebuilder_e2e.conftest import build, golden

ARCHETYPES = tuple(default_library().names()) + ("auto", "vision")


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_archetype_builds(archetype, genre):
    result = build(golden(genre), archetype=archetype)
    assert result["ok"] is True, result.get("error")
    assert result["core_loop"]["passed"] is True
