"""Public offline quest entrypoint: real recovered engines and hostile input."""
from copy import deepcopy
import hashlib
import io
import json
import subprocess
import sys

import pytest

from skeleton.app.original_quest_cli import (
    MAX_BYTES, REQUEST_SCHEMA, QuestRequestError, build_receipt,
    main, read_document, verify_receipt,
)


def request():
    return {
        "schema": REQUEST_SCHEMA, "slice_id": "lantern-harbor",
        "packs": [
            {"id": "movement", "provides": ["movement"]},
            {"id": "quest", "provides": ["quests"], "requires": ["movement"]},
        ],
        "pack_ids": ["quest", "movement"],
        "world": {"start": "village", "edges": {
            "village": ["forest"], "forest": ["cave"], "cave": [],
            "unreachable": [],
        }, "npcs": {"ranger": "forest"}},
        "policy": {"max_reward_per_step": 4, "max_total_reward": 20,
                   "allowed_reward_kinds": ["xp"], "banned_terms": ["forbidden"]},
        "seed": 7, "quest_length": 3,
    }


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def cli(command, value):
    output, error = io.StringIO(), io.StringIO()
    raw = value if isinstance(value, bytes) else canonical(value)
    code = main([command], stdin=io.BytesIO(raw), stdout=output, stderr=error)
    return code, json.loads(output.getvalue()) if output.getvalue() else None, error.getvalue()


def test_build_and_independent_replay():
    source = request()
    initial = build_receipt(source)
    assert initial == build_receipt(deepcopy(source))
    assert initial["source_digest"] == digest(source)
    artifact = initial["artifact"]
    assert artifact["mechanics"]["capabilities"]["quests"] == "quest"
    assert artifact["proof"]["status"] == "completed"
    steps = artifact["world_quest"]["quest"]["steps"]
    assert len(steps) == 3
    assert all(step["location"] != "unreachable" for step in steps)
    assert all(r["kind"] == "xp" for s in steps for r in s["rewards"])
    assert verify_receipt(source, initial)
    assert initial["native_qualified"] is False
    assert initial["release_qualified"] is False


def test_command_line_roundtrip_with_real_module():
    source = request()
    built = subprocess.run(
        [sys.executable, "-m", "skeleton.app.original_quest_cli", "build"],
        input=canonical(source), capture_output=True, timeout=30, check=True,
    )
    receipt = json.loads(built.stdout)
    checked = subprocess.run(
        [sys.executable, "-m", "skeleton.app.original_quest_cli", "verify"],
        input=canonical({"request": source, "receipt": receipt}),
        capture_output=True, timeout=30, check=True,
    )
    assert json.loads(checked.stdout) == {
        "verified": True, "abstract_replay_verified": True,
        "native_qualified": False, "release_qualified": False,
    }


def test_receipt_does_not_authorize_new_source_policy_or_native_claim():
    source = request()
    receipt = build_receipt(source)
    for changed in (
        {**source, "seed": 8},
        {**source, "policy": {**source["policy"], "max_total_reward": 21}},
        {**source, "world": {**source["world"], "npcs": {}}},
        {**source, "pack_ids": ["movement"]},
    ):
        assert not verify_receipt(changed, receipt)
    for changed_receipt in (
        {**receipt, "native_qualified": True},
        {**receipt, "release_qualified": True},
        {**receipt, "abstract_replay_verified": 1},
        {**receipt, "extra": "untrusted"},
    ):
        assert not verify_receipt(source, changed_receipt)


def test_rehashed_artifact_and_source_replacement_rejected():
    source = request()
    forged = deepcopy(build_receipt(source))
    artifact = forged["artifact"]
    artifact["proof"]["snapshot"]["progress"]["s0"] = 99
    artifact["proof"]["snapshot"]["digest"] = digest({
        k: v for k, v in artifact["proof"]["snapshot"].items() if k != "digest"
    })
    artifact["digest"] = digest({k: v for k, v in artifact.items() if k != "digest"})
    assert not verify_receipt(source, forged)
    other = deepcopy(source)
    other["policy"]["max_total_reward"] += 1
    forged = deepcopy(build_receipt(other))
    forged["source_digest"] = digest(source)
    # Changing just an unused reward cap may produce identical artifacts;
    # use an actually different seed to show why the whole replay matters.
    other["seed"] = 139
    forged = deepcopy(build_receipt(other))
    forged["source_digest"] = digest(source)
    assert not verify_receipt(source, forged)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(seed=True),
    lambda d: d.update(quest_length=129),
    lambda d: d.update(slice_id=""),
    lambda d: d.update(extra="not authorized"),
    lambda d: d["world"]["edges"]["forest"].append("missing"),
    lambda d: d["world"]["npcs"].update(ghost="missing"),
    lambda d: d["world"].update(start="missing"),
    lambda d: d["packs"].append(deepcopy(d["packs"][0])),
    lambda d: d["pack_ids"].append("quest"),
    lambda d: d["packs"][1].update(provides="quests"),
    lambda d: d["policy"].update(max_reward_per_step=True),
    lambda d: d["policy"].update(allowed_reward_kinds=[]),
    lambda d: d["policy"].update(max_total_reward=0),
    lambda d: d.update(quest_title="forbidden"),
    lambda d: d.update(overrides={"unselected": {}}),
])
def test_invalid_request_never_emits_a_receipt(mutate):
    source = request()
    mutate(source)
    code, output, error = cli("build", source)
    assert code == 1
    assert output is None
    assert error.startswith("quest request rejected:")
    assert "lantern-harbor" not in error


@pytest.mark.parametrize("raw", [
    b'{"schema":1,"schema":2}',
    b'{"x":NaN}',
    b'{"x":1e999}',
    b'{"x":"\\ud800"}',
    b'\xff',
    b"[" * 40 + b"0" + b"]" * 40,
    b" " * (MAX_BYTES + 1),
])
def test_parser_denies_ambiguous_or_unbounded_input(raw):
    with pytest.raises(QuestRequestError):
        read_document(io.BytesIO(raw))
    code, output, _ = cli("build", raw)
    assert code == 1 and output is None


def test_verify_cli_rejects_receipt_without_independent_request():
    receipt = build_receipt(request())
    assert cli("verify", receipt)[0] == 1
    assert cli("verify", {"request": request(), "receipt": receipt})[0] == 0
    forged = {**receipt, "release_qualified": True}
    assert cli("verify", {"request": request(), "receipt": forged})[0] == 1
