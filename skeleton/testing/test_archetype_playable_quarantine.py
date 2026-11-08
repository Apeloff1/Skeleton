"""Quarantine playable archetype boundary and opt-in source custody."""
from __future__ import annotations
import pytest
from skeleton.forge.archetype_content import archetype_files, attach_archetype_content, content_archetypes
from skeleton.context.pipeline import GameForgeRun


def test_playable_content_optin_required_and_strict_bool():
    with pytest.raises(ValueError):
        GameForgeRun().execute("test",playable_content="yes")
    with pytest.raises(ValueError):
        GameForgeRun().execute("test",target="json",playable_content=True)


def test_source_collisions_fail_closed_no_silent_clobber():
    source=archetype_files("extraction")
    key=next(iter(source))
    tampered={key:"extends Node\n# malicious shadowed content"}
    with pytest.raises(ValueError,match="collides"):
        attach_archetype_content(tampered,"extraction")
    assert tampered[key]!="".join(source.values())


def test_unknown_archetype_cannot_be_rendered_as_unbounded_path():
    for name in ("../evil", "/tmp/evil", "extraction/../../etc/passwd", ""):
        with pytest.raises(KeyError):
            archetype_files(name)
    assert "scenes/archetypes/extraction/main.tscn" in attach_archetype_content({},"vision")


def test_all_trusted_archetypes_emit_three_bounded_unique_sources():
    for archetype in content_archetypes():
        files=archetype_files(archetype)
        assert len(files)==3
        assert all(len(body)<16384 for body in files.values())
        assert all(not path.startswith("/") and ".." not in path.split("/") for path in files)
        assert any("ARCHETYPE_LOOP_FAILED" in s for s in files.values())
        assert any("ARCHETYPE_LOOP_COMPLETE" in s for s in files.values())


def test_non_godot_optin_does_not_hide_source_contract():
    runner=GameForgeRun()
    with pytest.raises(ValueError):
        runner.execute("a game",target="json",playable_content=True)
