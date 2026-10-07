from skeleton.school.decision_ledger import DecisionLedger, EvidenceKind, EvidenceRef
from skeleton.school.replay import JeevesReplay, replay_digest


def _ledger() -> DecisionLedger:
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e", EvidenceKind.OBSERVATION, "skill", "observed"))
    ledger.append(session_id="s", decision_id="d", domain="curriculum", action="teach", evidence=("e",))
    return ledger


def test_replay_matches_expected_actions() -> None:
    ledger = _ledger()
    replay = JeevesReplay(ledger)
    report = replay.compare_actions("s", {"d": "teach"})
    assert report.valid
    assert replay_digest(report.records) == ledger.head_hash


def test_replay_detects_action_divergence() -> None:
    report = JeevesReplay(_ledger()).compare_actions("s", {"d": "challenge"})
    assert not report.valid
    assert report.mismatches[0].field == "action"
