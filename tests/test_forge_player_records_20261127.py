"""Closed derived player records; these never authorize tools or releases."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.forge.game_design_spec import compile_brief
from skeleton.forge.playable_runtime import (
    SAVE_SCHEMA, PROFILE_COUNTERS, save_profile_digest, save_profile_id, verify_save_document,
)


DESIGN = "a" * 64


def document():
    payload = {"design_sha256": DESIGN, "runs": 3, "wins": 2, "losses": 1,
               "best_score": 1200, "best_time_ms": 8000}
    return {"schema": SAVE_SCHEMA, "payload": payload, "checksum": save_profile_digest(payload)}


def test_records_bind_the_complete_design_even_when_original_id_and_title_match():
    first = compile_brief("A small shooter.")
    second = deepcopy(first)
    second["gameplay"]["player_speed"] = 300
    assert first["spec_id"] == second["spec_id"] and first["title"] == second["title"]
    digests = [sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest() for spec in (first, second)]
    assert save_profile_id(digests[0]) != save_profile_id(digests[1])
    with pytest.raises(ValueError):
        save_profile_id("../arbitrary-user-path")


def test_complete_records_load_without_mutating_the_document():
    saved = document()
    previous = deepcopy(saved)
    status, payload = verify_save_document(saved, DESIGN)
    assert status == "loaded" and payload == saved["payload"]
    assert saved == previous
    assert set(payload) == {"design_sha256", *PROFILE_COUNTERS}


@pytest.mark.parametrize("value", [True, -1, 1.5, 10**12 + 1, float("nan"), float("inf"), 2**4096, "1", None])
def test_counter_types_and_bounds_are_closed(value):
    saved = document()
    saved["payload"]["best_score"] = value
    assert verify_save_document(saved, DESIGN)[0] == "rejected"


@pytest.mark.parametrize("location,key", [("document", "execution_authority"),
    ("payload", "credentials"), ("payload", "save_verified"), ("payload", "position")])
def test_records_never_accept_authority_proof_or_world_fields(location, key):
    saved = document()
    target = saved if location == "document" else saved["payload"]
    target[key] = True
    assert verify_save_document(saved, DESIGN)[0] == "rejected"


def test_corrupt_foreign_and_inconsistent_profiles_are_refused():
    corrupt = document()
    corrupt["checksum"] = "0" * 64
    assert verify_save_document(corrupt, DESIGN)[0] == "rejected"
    assert verify_save_document(document(), "b" * 64)[0] == "other_game"
    inconsistent = document()
    inconsistent["payload"]["wins"] = 5
    inconsistent["checksum"] = save_profile_digest(inconsistent["payload"])
    assert verify_save_document(inconsistent, DESIGN)[0] == "rejected"
    old_schema = document()
    old_schema["schema"] = "skeleton.forge.save.v1"
    assert verify_save_document(old_schema, DESIGN)[0] == "rejected"
