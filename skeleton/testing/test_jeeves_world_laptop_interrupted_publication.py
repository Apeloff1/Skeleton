"""Fail-closed recovery of interrupted reviewed builder publication.

A failed artifact write must not make an old receipt certify a mixed build.
Recompiling the same approved source is the only recovery action exercised.
"""
from __future__ import annotations

import pytest

from skeleton.jeeves.worlds.world_canon import CanonError
from skeleton.testing.test_jeeves_world_laptop_flow import ready


@pytest.mark.parametrize("failed_suffix", [
    ".laptop.builder.json",
    ".laptop.playable.html",
    ".laptop.receipt.json",
])
def test_interrupted_compile_never_certifies_partial_handoff(
    tmp_path, monkeypatch, failed_suffix,
):
    flow, _, reviewed, receipt = ready(tmp_path)
    first = flow.create_session("lighthouse", "player")
    save = tmp_path / "lighthouse.player.session.json"
    saved = save.read_bytes()

    # A previous receipt exists, so publishing only some outputs must not
    # silently certify a different set of artifacts.
    original = flow.worlds._write
    def interrupted(fd, name, data):
        if name.endswith(failed_suffix):
            raise OSError("injected interrupted publication")
        return original(fd, name, data)

    # Make the old builder visibly invalid before exercising publication.
    builder = tmp_path / receipt["builder_file"]
    builder.write_bytes(b"interrupted old artifact")
    monkeypatch.setattr(flow.worlds, "_write", interrupted)
    with pytest.raises(OSError, match="injected interrupted publication"):
        flow.compile("lighthouse", reviewed["source_digest"])
    monkeypatch.setattr(flow.worlds, "_write", original)

    with pytest.raises(CanonError):
        flow.verify("lighthouse")
    with pytest.raises(CanonError):
        flow.choose("lighthouse", "player", "rescue", first["session_digest"])
    assert save.read_bytes() == saved
    assert not (tmp_path / "lighthouse.lock").exists()

    repaired = flow.compile("lighthouse", reviewed["source_digest"])
    assert repaired == receipt
    assert flow.verify("lighthouse") == receipt
    assert flow.inspect_session("lighthouse", "player")["session_digest"] == first["session_digest"]
    assert save.read_bytes() == saved


def test_rebuild_after_corrupted_html_preserves_existing_player_state(tmp_path):
    flow, _, reviewed, receipt = ready(tmp_path)
    initial = flow.create_session("lighthouse", "player")
    advanced = flow.choose("lighthouse", "player", "rescue", initial["session_digest"])
    save = tmp_path / "lighthouse.player.session.json"
    before = save.read_bytes()

    (tmp_path / receipt["html_file"]).write_bytes(b"corrupt")
    with pytest.raises(CanonError) as error:
        flow.export_session("lighthouse", "player")
    assert error.value.code == "laptop_html_mismatch"
    assert save.read_bytes() == before

    assert flow.compile("lighthouse", reviewed["source_digest"]) == receipt
    exported = flow.export_session("lighthouse", "player")
    assert exported["session"]["scene"] == "shelter"
    assert flow.inspect_session("lighthouse", "player")["session_digest"] == advanced["session_digest"]
    assert save.read_bytes() == before
