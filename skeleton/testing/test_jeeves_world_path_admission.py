"""Descriptor-anchored world custody must validate IDs before any path IO."""
from __future__ import annotations

import os

import pytest

from skeleton.jeeves.worlds.bundle import PlayableBundleStore, _source_triplet
from skeleton.jeeves.worlds.cast import CastStore
from skeleton.jeeves.worlds.counterfactual import CounterfactualStore
from skeleton.jeeves.worlds.experience import ExperienceStore
from skeleton.jeeves.worlds.lore import LoreStore
from skeleton.jeeves.worlds.plan import PlanStore
from skeleton.jeeves.worlds.quest import QuestStore
from skeleton.jeeves.worlds.route import RouteStore
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, propose,
)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(propose(
        world_id="marsh", premise="Original marsh story",
        protagonist="Iris", region="Marsh", goal="Deliver letter",
    ), create=True)
    return root


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd custody")
@pytest.mark.parametrize("invalid", [
    "../escape", "../../escape", "marsh/../escape", "/tmp/escape",
    "marsh\\..\\escape", "", "Uppercase", ".hidden", "marsh.json",
])
def test_all_read_entrypoints_reject_noncanonical_world_ids(root, invalid):
    stores = [
        lambda: SessionStore(root).read(invalid, "save"),
        lambda: QuestStore(root).read(invalid),
        lambda: RouteStore(root).read(invalid),
        lambda: CastStore(root).read(invalid),
        lambda: LoreStore(root).read(invalid),
        lambda: CounterfactualStore(root).read(invalid, "save"),
        lambda: PlanStore(root).read(invalid),
        lambda: PlayableBundleStore(root).verify(invalid),
        lambda: ExperienceStore(root).verify(invalid),
    ]
    for action in stores:
        with pytest.raises(CanonError, match="invalid_identifier"):
            action()


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd custody")
def test_lock_helpers_refuse_parent_escape_before_creation(root):
    fd = WorldStore(root)._directory()
    try:
        stores = [
            lambda: SessionStore(root)._lock(fd, "../escape"),
            lambda: QuestStore(root)._lock(fd, "../escape"),
            lambda: RouteStore(root)._locked(fd, "../escape"),
            lambda: CastStore(root)._lock(fd, "../escape"),
            lambda: LoreStore(root)._lock(fd, "../escape"),
            lambda: CounterfactualStore(root)._lock(fd, "../escape"),
            lambda: ExperienceStore(root)._lock(fd, "../escape"),
        ]
        for action in stores:
            with pytest.raises(CanonError, match="invalid_identifier"):
                action()
        with pytest.raises(CanonError, match="invalid_identifier"):
            _source_triplet(fd, WorldStore(root), "../escape")
    finally:
        os.close(fd)
    assert not (root.parent / "escape.lock").exists()
    assert not (root.parent / "escape.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd custody")
def test_valid_ids_still_use_normal_canonical_world(root):
    assert WorldStore(root).read("marsh")["id"] == "marsh"
    fd = WorldStore(root)._directory()
    try:
        assert SessionStore(root)._world(fd, "marsh")["id"] == "marsh"
        assert QuestStore(root)._world(fd, "marsh")["id"] == "marsh"
        assert CastStore(root)._world(fd, "marsh")["id"] == "marsh"
        assert RouteStore(root)._source(fd, "marsh")["id"] == "marsh"
        assert LoreStore(root)._world(fd, "marsh")["id"] == "marsh"
    finally:
        os.close(fd)
