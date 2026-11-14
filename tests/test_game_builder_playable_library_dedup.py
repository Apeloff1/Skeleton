"""The guarded Jeeves builder and the eight authored mini-games stay disjoint.

#5285's builder emits the maintained interactive runtime
(``skeleton.forge.playable_runtime``) for its committed genres. The GameForge
playable library (``skeleton.forge.archetype_content``) owns the eight
authored mini-games. Neither may claim the other's genre, so every playable
name has exactly one maintained source.
"""
from __future__ import annotations

import re

from skeleton.forge import playable_runtime
from skeleton.forge.archetype_content import content_archetypes


def _runtime_genres() -> set[str]:
    source = playable_runtime.__loader__.get_source(playable_runtime.__name__)
    match = re.search(r'spec\.get\("genre"\) not in \{([^}]*)\}', source)
    assert match, "runtime genre admission set moved; update this contract"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def test_builder_runtime_genres_are_known_and_bounded():
    assert _runtime_genres() == {"top_down_shooter", "platformer", "rpg_roguelike"}


def test_one_maintained_source_per_playable_name():
    assert _runtime_genres().isdisjoint(content_archetypes())


def test_builder_never_attaches_authored_archetype_paths():
    import inspect
    from skeleton.app import offline_game_builder
    source = inspect.getsource(offline_game_builder)
    assert "archetype_content" not in source
    assert "scenes/archetypes/" not in source
