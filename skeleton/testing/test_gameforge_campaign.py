"""Narrative integration uses actual archived dialogue and quest owners."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from skeleton.app.gameforge_campaign import (
    REQUEST_SCHEMA, append_actions, build_campaign, play_campaign,
    verify_campaign, verify_session,
)
from skeleton.app.gameforge_campaign_cli import main
from skeleton.app.gameforge_campaign_store import CampaignStore, CampaignStoreError, RevisionConflict
from skeleton.app.gameforge_quest_bridge import REQUEST_SCHEMA as QUEST_SCHEMA
from skeleton.game.gameplay.dialogue_graph import replay


def spec():
    authored = json.loads((Path(__file__).parent / "fixtures" /
                           "dialogue_original_lantern_harbor.json").read_text(encoding="utf-8"))
    return {
        "schema": REQUEST_SCHEMA,
        "quest_request": {
            "schema": QUEST_SCHEMA,
            "vision": {"title": "Lantern Harbor", "pitch": "Restore the beacon",
                       "genre": "adventure", "pillars": ["exploration", "story"]},
            "config": {"regions": 6, "budget_bytes": 200000},
            "quest": {
                "packs": [{"id": "movement", "provides": ["movement"]},
                          {"id": "quest", "provides": ["quests"], "requires": ["movement"]}],
                "pack_ids": ["quest", "movement"],
                "policy": {"allowed_reward_kinds": ["gold"],
                           "max_reward_per_step": 2, "max_total_reward": 12},
                "seed": 31, "quest_length": 4, "npcs": {"keeper": "r00"},
            },
        },
        "dialogues": [{"npc": "keeper", "source": authored,
                       "gates": {"s0": "restore-western-lens"},
                       "witness": ["listen", "promise-repair"]}],
    }


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def rehash(value, field):
    value[field] = hashlib.sha256(encoded({k: v for k, v in value.items() if k != field})).hexdigest()


def invoke(command, data, database=None):
    args = [command] + (["--database", str(database)] if database is not None else [])
    output, error = io.StringIO(), io.StringIO()
    code = main(args, stdin=io.BytesIO(encoded(data)), stdout=output, stderr=error)
    return code, json.loads(output.getvalue()) if output.getvalue() else None, error.getvalue()


def test_archived_dialogue_runtime_controls_generated_quest():
    source = spec()
    design = build_campaign(source)
    witness = design["witness"]
    assert witness[:2] == [
        {"type": "dialogue", "npc": "keeper", "choice": "listen"},
        {"type": "dialogue", "npc": "keeper", "choice": "promise-repair"},
    ]
    assert design["witness_state"]["status"] == "completed"
    assert design["witness_state"]["dialogues"]["keeper"] == replay(
        source["dialogues"][0]["source"], ["listen", "promise-repair"]
    )
    assert len(design["witness_state"]["earned_rewards"]) == 4
    assert design == build_campaign(deepcopy(source))
    assert verify_campaign(source, design)
    assert not design["native_qualified"] and not design["release_qualified"]
    empty = play_campaign(source, [])
    assert not empty["state"]["earned_rewards"]
    assert empty["state"]["status"] == "in_progress"
    assert empty["state"]["dialogues"]["keeper"]["state"]["phase"] == "active"
    assert verify_session(source, empty)
    first = play_campaign(source, witness[:1])
    assert first["state"]["dialogues"]["keeper"]["state"]["reputation"] == 2
    assert not first["state"]["earned_rewards"]
    complete = append_actions(source, first, witness[1:])
    assert complete == play_campaign(source, witness)
    assert complete["state"] == design["witness_state"]


def test_departure_is_a_real_alternative_and_cannot_fabricate_grant():
    source = spec()
    actions = build_campaign(source)["witness"]
    depart = {"type": "dialogue", "npc": "keeper", "choice": "depart"}
    previous = play_campaign(source, [depart])
    assert previous["state"]["dialogues"]["keeper"]["state"]["reputation"] == -2
    assert not previous["state"]["dialogues"]["keeper"]["state"]["quests"]
    assert not previous["state"]["earned_rewards"]
    with pytest.raises(ValueError, match="grant"):
        append_actions(source, previous, actions[2:])
    with pytest.raises(ValueError, match="terminal"):
        append_actions(source, previous, actions[:1])
    assert verify_session(source, previous)


def test_no_conversation_teleportation_and_gate_cannot_be_skipped():
    source = spec()
    design = build_campaign(source)
    with pytest.raises(ValueError, match="grant"):
        play_campaign(source, design["witness"][2:])
    neighbor = design["world"]["edges"]["r00"][0]
    with pytest.raises(ValueError, match="location"):
        play_campaign(source, [{"type": "move", "to": neighbor}, design["witness"][0]])
    with pytest.raises(ValueError):
        play_campaign(source, [{"type": "dialogue", "npc": "keeper", "choice": "promise-repair"}])


def test_every_witness_event_is_legal_when_offered():
    source = spec()
    actions = build_campaign(source)["witness"]
    for index, event in enumerate(actions):
        before = play_campaign(source, actions[:index])
        assert event in before["state"]["legal_actions"]
    assert play_campaign(source, actions)["state"]["legal_actions"] == []


@pytest.mark.parametrize("edit", [
    lambda d: d["dialogues"][0]["source"].update(world_id="wrong-world"),
    lambda d: d["dialogues"][0].update(npc="missing"),
    lambda d: d["dialogues"][0].update(witness=["depart"]),
    lambda d: d["dialogues"][0].update(gates={"s0": "unearned"}),
    lambda d: d["dialogues"][0].update(gates={"s99": "restore-western-lens"}),
    lambda d: d["dialogues"].append(deepcopy(d["dialogues"][0])),
])
def test_unbound_dialogue_contracts_denied(edit):
    source = spec()
    edit(source)
    code, data, _ = invoke("build", source)
    assert code == 1 and data is None


def test_rehashed_dialogue_reputation_and_progress_fail_replay():
    source = spec()
    receipt = play_campaign(source, [])
    forged = deepcopy(receipt)
    forged["state"]["dialogues"]["keeper"]["state"]["quests"] = ["restore-western-lens"]
    rehash(forged, "session_digest")
    assert not verify_session(source, forged)
    with pytest.raises(ValueError):
        append_actions(source, forged, build_campaign(source)["witness"])
    changed = deepcopy(source)
    changed["dialogues"][0]["source"]["nodes"][0]["text"] += " Changed."
    assert not verify_session(changed, receipt)
    assert not verify_campaign(changed, build_campaign(source))


def test_persistent_reopen_idempotency_and_cas(tmp_path):
    source = spec()
    witness = build_campaign(source)["witness"]
    path = tmp_path / "campaign.sqlite"
    with sqlite3.connect(path) as db:
        first = CampaignStore(db).create("slot-a", source, "create-1")
        assert first["revision"] == 0
    with sqlite3.connect(path) as db:
        store = CampaignStore(db)
        assert store.read("slot-a", source) == first
        assert store.create("slot-a", source, "create-1") == first
        second = store.append("slot-a", source, 0, "listen-1", witness[:1])
        assert second["revision"] == 1
        assert store.append("slot-a", source, 0, "listen-1", witness[:1]) == second
        with pytest.raises(RevisionConflict):
            store.append("slot-a", source, 0, "stale", witness[:1])
        with pytest.raises(RevisionConflict):
            store.append("slot-a", source, 0, "listen-1", witness[:2])
        done = store.append("slot-a", source, 1, "complete", witness[1:])
        assert done["receipt"]["state"]["status"] == "completed"
        assert store.read("slot-a", source, 0) == first
        assert store.append("slot-a", source, 0, "listen-1", witness[:1]) == second
        assert [row["revision"] for row in store.history("slot-a", source)["revisions"]] == [0, 1, 2]
        assert store.read("slot-a", source) == done
        changed = deepcopy(source)
        changed["quest_request"]["quest"]["seed"] += 1
        with pytest.raises(CampaignStoreError):
            store.read("slot-a", changed)


def test_failed_append_is_atomic_and_operations_are_scoped(tmp_path):
    source = spec()
    witness = build_campaign(source)["witness"]
    with sqlite3.connect(tmp_path / "campaign.sqlite") as db:
        store = CampaignStore(db)
        zero = store.create("one", source, "same")
        store.create("two", source, "same")
        with pytest.raises(ValueError):
            store.append("one", source, 0, "retry", witness[2:])
        assert store.read("one", source) == zero
        assert len(store.history("one", source)["revisions"]) == 1
        assert store.append("one", source, 0, "retry", witness[:1])["revision"] == 1
        assert store.read("two", source)["revision"] == 0


def test_competing_connection_cannot_advance_stale_head(tmp_path):
    source = spec()
    witness = build_campaign(source)["witness"]
    path = tmp_path / "campaign.sqlite"
    with sqlite3.connect(path) as a, sqlite3.connect(path) as b:
        left, right = CampaignStore(a), CampaignStore(b)
        left.create("slot", source, "create")
        assert right.read("slot", source)["revision"] == 0
        left.append("slot", source, 0, "left", witness[:1])
        with pytest.raises(RevisionConflict):
            right.append("slot", source, 0, "right", witness[:1])
        assert right.read("slot", source)["revision"] == 1


def test_modified_database_receipt_or_lineage_fails_closed(tmp_path):
    source = spec()
    witness = build_campaign(source)["witness"]
    with sqlite3.connect(tmp_path / "campaign.sqlite") as db:
        store = CampaignStore(db)
        store.create("slot", source, "create")
        second = store.append("slot", source, 0, "one", witness[:1])
        db.execute("UPDATE gf_campaign_revisions_v1 SET previous_digest=? WHERE revision=1", ("0"*64,))
        db.commit()
        with pytest.raises(CampaignStoreError):
            store.read("slot", source)
        with pytest.raises(CampaignStoreError):
            store.history("slot", source)
        receipt = deepcopy(second["receipt"])
        receipt["state"]["earned_rewards"] = [{"kind": "gold", "amount": 99}]
        rehash(receipt, "session_digest")
        db.execute("UPDATE gf_campaign_revisions_v1 SET receipt=?,receipt_digest=? WHERE revision=1",
                   (encoded(receipt), receipt["session_digest"]))
        db.commit()
        with pytest.raises(CampaignStoreError):
            store.read("slot", source)


def test_cli_persistent_roundtrip_and_canonical_entrypoint(tmp_path):
    source = spec()
    path = tmp_path / "campaign.sqlite"
    code, design, _ = invoke("build", source)
    assert code == 0
    assert invoke("verify", {"request": source, "receipt": design})[0] == 0
    body = {"request": source, "slot": "a", "operation": "create"}
    assert invoke("create-slot", body, path)[0] == 0
    code, complete, _ = invoke("append-slot", {"request": source, "slot": "a",
        "operation": "win", "expected_revision": 0, "additional": design["witness"]}, path)
    assert code == 0 and complete["receipt"]["state"]["status"] == "completed"
    assert invoke("read-slot", {"request": source, "slot": "a"}, path)[1] == complete
    assert invoke("history", {"request": source, "slot": "a"}, path)[1]["head"] == 1
    proc = subprocess.run([sys.executable, "-m", "skeleton", "gameforge-campaign", "build"],
                          input=encoded(source), capture_output=True, timeout=60, check=True)
    assert json.loads(proc.stdout) == design


def test_cli_does_not_create_db_during_read(tmp_path):
    path = tmp_path / "absent.sqlite"
    assert invoke("read-slot", {"request": spec(), "slot": "a"}, path)[0] == 1
    assert not path.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file mode requirement")
def test_cli_refuses_symlink_and_public_parent(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "actual.sqlite"
    target.touch(mode=0o600)
    link = private / "link.sqlite"
    link.symlink_to(target)
    data = {"request": spec(), "slot": "a", "operation": "new"}
    assert invoke("create-slot", data, link)[0] == 1
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    assert invoke("create-slot", data, public / "db.sqlite")[0] == 1
