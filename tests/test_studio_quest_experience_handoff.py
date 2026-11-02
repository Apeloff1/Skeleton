"""Original quest presentation+pacing+advisories exact-session integration."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_localization import (
    PROMPT as LOCALE_PROMPT, propose_quest_localization, compile_quest_localization,
)
from skeleton.ai.game_builder.studio_quest_achievements import (
    PROMPT as AWARD_PROMPT, propose_quest_achievements, compile_quest_achievements,
)
from skeleton.ai.game_builder.studio_quest_pacing import (
    PROMPT as PACE_PROMPT, propose_quest_pacing, compile_quest_pacing,
)
from skeleton.ai.game_builder.studio_quest_advisories import (
    PROMPT as WARNING_PROMPT, propose_quest_advisories, compile_quest_advisories,
)
from skeleton.ai.game_builder.studio_quest_experience_handoff import (
    FILENAME, compile_quest_experience_bundle, compile_quest_experience_handoff,
    render_quest_experience_review_html, publish_quest_experience,
    restore_quest_experience,
)


def fixture():
    docs = {
        "quest": {"project_id": "original_demo", "release_certified": False,
                  "stage_graph": [
                      {"id": "first", "prerequisites": [],
                       "alternatives": ["help", "leave"], "reward": "earned_token"}
                  ]},
        "narrative": {"project_id": "original_demo", "release_certified": False,
                      "endings": [{"id": "good", "requires": ["earned_token"]}]},
    }
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    actions = [["first", "help"]]
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    lp = propose_quest_localization(
        docs, LOCALE_PROMPT, "en-US", actions, "good", **leases)
    for row in lp["rows"]:
        row["reviewed"] = True
    locale = compile_quest_localization(docs, lp, **leases)
    ap = propose_quest_achievements(
        docs, AWARD_PROMPT, actions, target_ending="good", **leases)
    awards = compile_quest_achievements(docs, ap, **leases)
    pp = propose_quest_pacing(
        docs, PACE_PROMPT, actions, target_ending="good", **leases)
    pp["beats"][0]["reviewed"] = True
    pacing = compile_quest_pacing(docs, pp, **leases)
    wp = propose_quest_advisories(
        docs, WARNING_PROMPT, actions, target_ending="good", **leases)
    wp["advisories"][0].update({
        "reviewed": True, "summary": "Contains a loud original sound",
        "topics": ["loud_audio"], "severity": 2, "spoiler_level": "mild"})
    warnings = compile_quest_advisories(docs, wp, **leases)
    return docs, locale, awards, pacing, warnings


def compile_all(parts, topics):
    return compile_quest_experience_bundle(*parts, topics, authorized=True)


def test_end_to_end_source_bound_handoff_and_consent():
    parts = fixture()
    bundle = compile_all(parts, ["loud_audio"])
    assert bundle["blocking_reasons"] == []
    assert bundle["playable_handoff_allowed"] is True
    assert bundle["estimated_play_seconds"] == 90
    assert bundle["sandbox_points"] == 10
    assert bundle["canonical_quest_replay_verified"] is True
    handoff = compile_quest_experience_handoff(
        *parts, ["loud_audio"], authorized=True)
    assert handoff["source_digest"] == bundle["source_digest"]
    assert handoff["session_digest"] == bundle["session_digest"]
    assert handoff["current_consent"]["can_continue"] is True
    assert handoff["native_gameplay_verified"] is False
    assert handoff["release_certified"] is False


def test_missing_consent_blocks_handoff_without_changing_canonical_history():
    parts = fixture()
    bundle = compile_all(parts, [])
    assert bundle["playable_handoff_allowed"] is False
    assert "player_has_not_accepted_current_warnings" in bundle["blocking_reasons"]
    assert bundle["session_digest"] == compile_all(parts, ["loud_audio"])["session_digest"]
    with pytest.raises(StudioQuestError):
        compile_quest_experience_handoff(*parts, [], authorized=True)


def test_unreviewed_pacing_and_advisories_fail_closed():
    parts = list(fixture())
    pace = copy.deepcopy(parts[3])
    pace["authoring"]["beats"][0]["reviewed"] = False
    # Tampering with a receipt is rejected, not interpreted as a draft.
    parts[3] = pace
    with pytest.raises(StudioQuestError):
        compile_all(parts, ["loud_audio"])
    parts = list(fixture())
    warning = copy.deepcopy(parts[4])
    warning["all_stages_reviewed"] = False
    parts[4] = warning
    with pytest.raises(StudioQuestError):
        compile_all(parts, ["loud_audio"])


def test_mixed_sessions_and_source_digest_fail_closed():
    parts = list(fixture())
    forged = copy.deepcopy(parts[1])
    forged["session_digest"] = "0" * 64
    parts[1] = forged
    with pytest.raises(StudioQuestError):
        compile_all(parts, ["loud_audio"])
    parts = list(fixture())
    forged = copy.deepcopy(parts[2])
    forged["source_digest"] = "0" * 64
    parts[2] = forged
    with pytest.raises(StudioQuestError):
        compile_all(parts, ["loud_audio"])


@pytest.mark.parametrize("topics", [
    ["loud_audio", "loud_audio"], ["unknown"], ["loud_audio", "fear"],
    [True], "loud_audio",
])
def test_invalid_player_topics_rejected(topics):
    with pytest.raises(StudioQuestError):
        compile_all(fixture(), topics)


def test_csp_preview_escapes_reviewed_advisory_content():
    parts = list(fixture())
    # Authored source uses an HTML-looking value; compile it before preview.
    docs, loc, ach, pace, warnings = parts
    warning_plan = copy.deepcopy(warnings["authoring"])
    warning_plan["advisories"][0]["summary"] = "</script><img src=x>"
    source = compile_quest_program(docs).source_digest
    initial = start_quest(docs, authorized=True).digest
    warnings = compile_quest_advisories(
        docs, warning_plan, authorized=True,
        expected_source_digest=source,
        expected_initial_session_digest=initial)
    html = render_quest_experience_review_html(
        docs, loc, ach, pace, warnings, ["loud_audio"], authorized=True)
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"&lt;/script&gt;" in html
    assert b"</script><img" not in html


def test_private_bundle_publish_restore_and_symlink(tmp_path):
    parts = fixture()
    result = publish_quest_experience(
        *parts, ["loud_audio"], tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    restored = restore_quest_experience(
        *parts, ["loud_audio"], tmp_path, authorized=True)
    assert restored["bundle_digest"] == result["bundle_digest"]
    with pytest.raises(FileExistsError):
        publish_quest_experience(*parts, ["loud_audio"], tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_experience(
            *parts, ["loud_audio"], tmp_path, authorized=True)


def test_cli_reads_private_receipts_and_compiles_handoff(tmp_path, capsys, monkeypatch):
    from scripts import studio_quest_experience_cli as cli
    parts = fixture()
    monkeypatch.setattr(cli, "read_blueprint", lambda _: parts[0])
    paths = []
    for i, receipt in enumerate(parts[1:]):
        path = tmp_path / ("receipt-" + str(i) + ".json")
        path.write_text(json.dumps(receipt))
        os.chmod(path, 0o600)
        paths.append(path)
    args = ["--project", "original_demo", "--localization-file", str(paths[0]),
            "--achievements-file", str(paths[1]), "--pacing-file", str(paths[2]),
            "--advisories-file", str(paths[3]), "--accept-topic", "loud_audio"]
    assert cli.main(args + ["--handoff"]) == 0
    assert json.loads(capsys.readouterr().out)["playable_handoff"]["current_consent"]["can_continue"]
    assert cli.main(args + ["--review-html"]) == 0
    assert "Source-replayed quest experience" in capsys.readouterr().out
