"""Acceptance for accessible replay-derived campaign captions and offline pages."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.combat_campaign import (
    advance_campaign, finish_campaign, new_campaign, original_campaign,
)
from skeleton.game.gameplay.combat_campaign_captions import (
    SCHEMA, build_captions, caption_page, verify_captions,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _played():
    return finish_campaign(original_campaign())


def test_full_play_to_accessible_transcript_and_portable_replay():
    session = _played()
    transcript = build_captions(session)
    assert transcript["schema_version"] == SCHEMA
    assert transcript["manifest"]["phase"] == "won"
    assert transcript["manifest"]["completed_encounters"] == 2
    assert transcript["manifest"]["earned_currency"] == 30
    assert transcript["manifest"]["caption_count"] == len(transcript["captions"])
    assert transcript["manifest"]["caption_count"] > 0
    assert transcript["manifest"]["total_damage"] > 0
    assert any(row["action"] == "attack" and row["damage"] > 0
               for row in transcript["captions"])
    assert any(row["knockout"] for row in transcript["captions"])
    assert any("wins the encounter" in row["caption"]
               for row in transcript["captions"])
    assert verify_captions(json.loads(json.dumps(transcript))) == transcript
    assert build_captions(session) == transcript


def test_partial_checkpoint_has_only_earned_rewards_and_replayed_turns():
    source = original_campaign()
    first = advance_campaign(new_campaign(source))
    partial = build_captions(first)
    assert partial["manifest"]["phase"] == "active"
    assert partial["manifest"]["completed_encounters"] == 1
    assert partial["manifest"]["earned_currency"] == 10
    assert partial["encounters"][0]["reward"] == 10
    assert len(partial["captions"]) == partial["encounters"][0]["caption_count"]
    completed = build_captions(finish_campaign(source, resume=first))
    assert completed["captions"][:len(partial["captions"])] == partial["captions"]
    assert completed["manifest"]["earned_currency"] == 30


def test_pages_are_bounded_ordered_and_bind_complete_transcript():
    transcript = build_captions(_played())
    gathered = []
    offset = 0
    while True:
        page = caption_page(transcript, offset=offset, limit=3)
        assert page["transcript_receipt"] == transcript["receipt"]
        assert page["offset"] == offset
        assert len(page["captions"]) <= 3
        gathered.extend(page["captions"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert gathered == transcript["captions"]
    assert caption_page(transcript, offset=len(gathered))["captions"] == []


@pytest.mark.parametrize("field", ["caption", "damage", "after_digest", "turn_receipt"])
def test_modified_turn_text_damage_or_receipt_fails_closed(field):
    transcript = build_captions(_played())
    forged = copy.deepcopy(transcript)
    if field == "damage":
        forged["captions"][0][field] += 1
    else:
        forged["captions"][0][field] = "tampered"
    with pytest.raises(CombatSessionError):
        verify_captions(forged)


def test_rehashed_forgery_still_fails_canonical_replay():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig

    forged = copy.deepcopy(build_captions(_played()))
    forged["manifest"]["earned_currency"] = 100000
    forged["receipt"] = dig({k: v for k, v in forged.items() if k != "receipt"})
    with pytest.raises(CombatSessionError, match="replay mismatch"):
        verify_captions(forged)


def test_mutated_campaign_session_rejected_before_caption_rendering():
    session = _played()
    forged = copy.deepcopy(session)
    forged["state"]["currency"] = 100000
    with pytest.raises(CombatSessionError):
        build_captions(forged)


@pytest.mark.parametrize("offset,limit", [
    (-1, 3), (0, 0), (0, 65), (129, 2), (True, 2), (0, False),
])
def test_invalid_page_requests_rejected(offset, limit):
    transcript = build_captions(_played())
    with pytest.raises(CombatSessionError):
        caption_page(transcript, offset=offset, limit=limit)


def _cli(capsys, *args):
    status = main(list(args))
    output = capsys.readouterr()
    return status, json.loads(output.out or output.err)


def test_main_cli_source_runtime_save_export_verify_and_page(capsys):
    status, transcript = _cli(capsys, "combat-campaign-captions", "demo")
    assert status == 0
    status, verified = _cli(capsys, "combat-campaign-captions", "verify",
                            "--transcript-json", json.dumps(transcript))
    assert status == 0 and verified == transcript
    status, page = _cli(capsys, "combat-campaign-captions", "page",
                        "--transcript-json", json.dumps(transcript),
                        "--offset", "0", "--limit", "2")
    assert status == 0 and len(page["captions"]) == 2
    status, checkpoint = _cli(capsys, "combat-campaign", "demo")
    assert status == 0
    status, rebuilt = _cli(capsys, "combat-campaign-captions", "build",
                           "--session-json", json.dumps(checkpoint))
    assert status == 0 and rebuilt == transcript


def test_main_cli_invalid_payload_fails_without_partial_export(capsys):
    status, error = _cli(capsys, "combat-campaign-captions", "build",
                         "--session-json", '{"bad":true}')
    assert status == 2 and error["ok"] is False
    status, error = _cli(capsys, "combat-campaign-captions", "page",
                         "--transcript-json", '{"bad":true}')
    assert status == 2 and error["ok"] is False
