"""Transactional authored-world editing, tamper rejection and CLI acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_authoring import (
    author_revision, verify_revision,
)

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def world():
    return load_source(WORLD)


def revision():
    source = world()
    return author_revision(
        source,
        [{"op": "merchant_price", "price": 1}, {"op": "stock", "id": "wood", "quantity": 3}],
        expected_source_digest=digest(source),
    )


def test_editor_changes_real_gameplay_and_preserves_parent_source():
    source = world()
    before = deepcopy(source)
    edited = revision()
    assert source == before
    assert edited["source"]["npc"]["price"] == 1
    assert edited["source"]["resources"][0]["quantity"] == 3
    assert verify_revision(decode(canonical(edited))) == edited["source"]
    assert export_bundle(edited["source"], demo_actions(), require_win=True)["state"]["ending"] == "beacon"
    assert edited["source_digest"] != edited["parent_digest"]


def test_source_edit_revision_is_deterministic_and_replay_verified():
    assert canonical(revision()) == canonical(revision())
    assert verify_revision(revision())["id"] == "lantern-quay"


def test_authoring_lease_rejects_stale_revision_and_noop():
    source = world()
    with pytest.raises(HarborError, match="stale source"):
        author_revision(source, [{"op": "merchant_price", "price": 1}], expected_source_digest="0" * 64)
    with pytest.raises(HarborError, match="no-op"):
        author_revision(source, [{"op": "merchant_price", "price": 2}], expected_source_digest=digest(source))


@pytest.mark.parametrize("edits", [
    [{"op": "merchant_price", "price": 0}],
    [{"op": "stock", "id": "missing", "quantity": 2}],
    [{"op": "stock", "id": "wood", "quantity": True}],
    [{"op": "stock", "id": "wood", "quantity": 2}, {"op": "stock", "id": "wood", "quantity": 3}],
    [{"op": "tile", "at": [1, 1], "tile": "#"}],
    [{"op": "tile", "at": [0, 0], "tile": "."}],
    [{"op": "move_resource", "id": "wood", "at": [0, 0]}],
    [{"op": "move_resource", "id": "wood", "at": [1, 1]}],
    [{"op": "delivery", "item": "unknown", "quantity": 1}],
    [{"op": "recipe", "id": "missing", "inputs": {"wood": 1}, "output": {"x": 1}}],
    [{"op": "max_ticks", "value": 0}],
    [{"op": "execute", "script": "print('unsafe')"}],
    [{"op": "merchant_price", "price": 1, "extra": True}],
    [],
    [{"op": "merchant_price", "price": 1}] * 33,
])
def test_invalid_editor_transactions_fail_closed_without_mutation(edits):
    source = world()
    original = deepcopy(source)
    with pytest.raises(HarborError):
        author_revision(source, edits, expected_source_digest=digest(source))
    assert source == original


def test_authoring_rejects_disconnected_resource_and_dock():
    source = world()
    # Block the only corridor between the western food deposit and the start.
    # The map stays geometrically valid, but the food is now unreachable.
    edits = [
        {"op": "tile", "at": [1, 2], "tile": "#"},
        {"op": "tile", "at": [2, 3], "tile": "#"},
    ]
    with pytest.raises(HarborError, match="unreachable"):
        author_revision(source, edits, expected_source_digest=digest(source))


@pytest.mark.parametrize("mutation", [
    lambda r: r["source"]["npc"].update({"price": 60}),
    lambda r: r["parent"]["npc"].update({"price": 99}),
    lambda r: r["operations"][0].update({"price": 60}),
    lambda r: r.update({"source_digest": "0" * 64}),
    lambda r: r.update({"parent_digest": "0" * 64}),
    lambda r: r.update({"revision_digest": "0" * 64}),
])
def test_editor_revision_tampering_is_rejected(mutation):
    edited = revision()
    mutation(edited)
    with pytest.raises(HarborError):
        verify_revision(edited)


def test_resealed_outer_digest_does_not_override_source_edit_replay():
    edited = revision()
    edited["source"]["npc"]["price"] = 60
    edited["source_digest"] = digest(edited["source"])
    edited["revision_digest"] = digest({k: v for k, v in edited.items() if k != "revision_digest"})
    with pytest.raises(HarborError, match="replay mismatch"):
        verify_revision(edited)


def test_cli_editor_and_verifier_round_trip(tmp_path):
    source = world()
    edits = tmp_path / "edits.json"
    edits.write_bytes(canonical([
        {"op": "merchant_price", "price": 1},
        {"op": "stock", "id": "wood", "quantity": 3},
    ]))
    command = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    made = subprocess.run(
        command + ["author", "--edits", str(edits), "--expected-source-digest", digest(source)],
        capture_output=True, check=False,
    )
    assert made.returncode == 0, made.stderr.decode()
    revision_file = tmp_path / "revision.json"
    revision_file.write_bytes(made.stdout)
    verified = subprocess.run(
        command + ["verify-author", "--revision", str(revision_file)],
        capture_output=True, check=False,
    )
    assert verified.returncode == 0, verified.stderr.decode()
    assert decode(verified.stdout)["source"]["npc"]["price"] == 1


def test_cli_refuses_stale_source_lease_without_success_output(tmp_path):
    edits = tmp_path / "edits.json"
    edits.write_bytes(canonical([{"op": "merchant_price", "price": 1}]))
    command = [sys.executable, "-m", "scripts.game.harbor_crafting", "author",
               "--edits", str(edits), "--expected-source-digest", "0" * 64]
    failed = subprocess.run(command, capture_output=True, check=False)
    assert failed.returncode == 2
    assert failed.stdout == b""
