"""Gameplay analytics: schema, privacy, sessions, funnels, retention, heatmap."""
import json

import pytest

from skeleton.ai.game_builder.analytics import (
    Collector, DifficultyHeatmap, EventError, EventType, Funnel, GameplayEvent, PrivacyPolicy, build_sessions,
    difficulty_heatmap, retention, stage_stats,
)

SALT = b"0123456789abcdef-test"
PLAN = {"levels": [{"id": "l1", "encounters": [{"id": "l1.boss"}]}, {"id": "l2", "encounters": ["l2.e1"]}]}


def play(c, player, session, script, day=0):
    for i, (typ, lv, enc) in enumerate(script):
        ev = {"seq": i, "t": float(i * 10), "type": typ, "day": day}
        if lv:
            ev["level_id"] = lv
        if enc:
            ev["encounter_id"] = enc
        c.ingest(player, session, ev)


WIN = [("session_start", None, None), ("level_start", "l1", None), ("encounter_start", "l1", "l1.boss"),
       ("encounter_complete", "l1", "l1.boss"), ("level_complete", "l1", None), ("level_start", "l2", None),
       ("level_complete", "l2", None), ("session_end", None, None)]
STUCK = [("session_start", None, None), ("level_start", "l1", None), ("encounter_start", "l1", "l1.boss"),
         ("death", "l1", "l1.boss"), ("encounter_fail", "l1", "l1.boss"), ("level_fail", "l1", None),
         ("level_start", "l1", None), ("encounter_start", "l1", "l1.boss"), ("quit", None, None)]


def collector(**kw):
    return Collector(PrivacyPolicy(SALT, **kw))


def test_schema_validation_and_roundtrip():
    e = GameplayEvent("p1", "s1", 0, 1.5, "level_start", level_id="l1", attrs={"weapon": "bow", "damage": 3})
    assert e.type is EventType.LEVEL_START
    assert GameplayEvent.from_dict(json.loads(json.dumps(e.to_dict()))) == e
    with pytest.raises(EventError):
        GameplayEvent("p1", "s1", 0, 0, "level_start")
    with pytest.raises(EventError):
        GameplayEvent("p1", "s1", 0, 0, "encounter_fail", level_id="l1")
    with pytest.raises(EventError):
        GameplayEvent("p1", "s1", 0, 0, "teleport")
    with pytest.raises(EventError):
        GameplayEvent.from_dict({"player": "p", "session_id": "s", "seq": 0, "t": 0, "type": "quit", "ip": "x"})


@pytest.mark.parametrize("attrs", [{"email": "x"}, {"player_name": "Bob"}, {"note": "bob@example.com"},
                                   {"note": "10.0.0.1"}, {"note": "+47 912 34 567"}])
def test_pii_rejected(attrs):
    with pytest.raises(EventError):
        GameplayEvent("p1", "s1", 0, 0, "quit", attrs=attrs)


def test_raw_ids_never_stored_and_pseudonyms_stable():
    c = collector()
    play(c, "alice@example.com", "sess-raw", WIN)
    blob = json.dumps([e.to_dict() for e in c.events])
    assert "alice" not in blob and "sess-raw" not in blob
    assert len({e.player for e in c.events}) == 1
    assert c.events[0].player == PrivacyPolicy(SALT).pseudonym("player", "alice@example.com")
    assert PrivacyPolicy(b"another-salt-0123456").pseudonym("player", "alice@example.com") != c.events[0].player
    with pytest.raises(EventError):
        c.ingest("a", "s", {"seq": 0, "t": 0, "type": "quit", "player": "a"})


def test_opt_out_drop_purges_and_blocks():
    c = collector()
    play(c, "a", "s1", WIN)
    play(c, "b", "s2", WIN)
    c.opt_out("a")
    play(c, "a", "s3", WIN)
    assert {e.player for e in c.events} == {PrivacyPolicy(SALT).pseudonym("player", "b")}
    assert c.counts["opted_out_dropped"] == len(WIN)


def test_opt_out_anonymise_unlinkable():
    c = collector(opt_out="anonymise")
    c.ingest("a", "s1", {"seq": 0, "t": 0, "type": "level_start", "level_id": "l1", "x": 1, "y": 2,
                         "attrs": {"weapon": "bow"}})
    c.opt_out("a")
    play(c, "a", "s2", WIN)
    assert {e.player for e in c.events} == {"anon"}
    assert len({e.session_id for e in c.events}) == 2
    assert all(e.x is None and e.attrs == () for e in c.events)
    assert retention(build_sessions(c.events))["players"] == 0
    assert stage_stats(c.events)[("l1", None)].attempts == 2


def test_shared_raw_session_is_principal_scoped_even_after_anonymisation():
    event = {"seq": 0, "t": 0, "type": "session_start"}
    c = collector(opt_out="anonymise")
    first = c.ingest("player-one", "shared-session", event)
    second = c.ingest("player-two", "shared-session", event)
    assert first is not None and second is not None
    assert first.session_id != second.session_id
    assert len(build_sessions(c.events)) == 2
    c.opt_out("player-one")
    c.opt_out("player-two")
    assert {e.player for e in c.events} == {"anon"}
    assert len({e.session_id for e in c.events}) == 2
    assert len(build_sessions(c.events)) == 2


def test_session_pseudonym_tuple_is_unambiguous_with_delimiters():
    policy = PrivacyPolicy(SALT)
    assert policy.session_pseudonym("a:b", "c") != policy.session_pseudonym("a", "b:c")
    assert policy.session_pseudonym("a", "shared") == policy.session_pseudonym("a", "shared")


@pytest.mark.parametrize("bad", ["", "x" * 257, "name\\nnewline", "name\\x00nul",
                                  "name\\u202ehidden", None, 123])
def test_raw_analytics_identity_rejects_unsafe_inputs(bad):
    c = collector()
    event = {"seq": 0, "t": 0, "type": "session_start"}
    with pytest.raises(EventError):
        c.ingest(bad, "session", event)
    with pytest.raises(EventError):
        c.ingest("player", bad, event)
    with pytest.raises(EventError):
        c.opt_out(bad)
    assert c.events == [] and c.opted_out == set()


def test_collector_bounded_retention_and_purge_releases_capacity():
    from skeleton.ai.game_builder.analytics.privacy import EventCapacityError

    c = Collector(PrivacyPolicy(SALT), max_events=2)
    event = {"seq": 0, "t": 0, "type": "session_start"}
    c.ingest("a", "s1", event)
    c.ingest("a", "s2", event)
    with pytest.raises(EventCapacityError, match="capacity"):
        c.ingest("b", "s3", event)
    assert len(c.events) == 2
    assert c.counts["kept"] == 2
    assert c.counts["rejected"] == 1
    with pytest.raises(EventCapacityError, match="capacity"):
        c.ingest_many([("b", "s3", event)])
    c.opt_out("a")
    assert not c.events
    assert c.ingest("b", "s3", event) is not None
    assert len(c.events) == 1
    with pytest.raises(ValueError, match="max_events"):
        Collector(PrivacyPolicy(SALT), max_events=0)


def test_sampling_is_per_player_and_deterministic():
    c = collector(sample_rate=0.3)
    for i in range(400):
        c.ingest(f"p{i}", f"s{i}", {"seq": 0, "t": 0, "type": "session_start"})
        c.ingest(f"p{i}", f"s{i}", {"seq": 1, "t": 1, "type": "quit"})
    kept = {e.player for e in c.events}
    assert 80 < len(kept) < 160
    assert all(sum(e.player == p for e in c.events) == 2 for p in kept)
    assert PrivacyPolicy(SALT, sample_rate=0.0).sampled("x") is False
    with pytest.raises(ValueError):
        PrivacyPolicy(b"short")


def test_sessions_funnel_retention():
    c = collector()
    play(c, "a", "a1", WIN, day=100)
    play(c, "a", "a2", WIN, day=101)
    play(c, "b", "b1", STUCK, day=100)
    play(c, "b", "b2", STUCK, day=107)
    sessions = build_sessions(c.events)
    assert len(sessions) == 4
    assert sorted(s.ended for s in sessions) == ["quit", "quit", "session_end", "session_end"]
    assert sorted(s.duration for s in sessions) == [70.0, 70.0, 80.0, 80.0]
    f = Funnel(("session_start", "level_start:l1", "encounter_complete:l1:l1.boss", "level_complete:l2")).run(c.events)
    assert f.reached == (2, 2, 1, 1) and f.conversion == (1.0, 1.0, 0.5, 0.5)
    assert retention(sessions) == {"players": 2, "d1": 0.5, "d7": 0.5, "d30": 0.0}


def test_drop_off_and_heatmap_plain_data():
    c = collector()
    for i in range(6):
        play(c, f"w{i}", f"ws{i}", WIN)
    for i in range(4):
        play(c, f"s{i}", f"ss{i}", STUCK)
    st = stage_stats(c.events)
    assert st[("l1", None)].drop_offs == 4 and st[("l1", "l1.boss")].drop_offs == 4
    assert st[("l2", None)].drop_offs == 0
    hm = difficulty_heatmap(c.events, PLAN, min_players=5)
    assert isinstance(hm, DifficultyHeatmap)
    assert [(x.level_id, x.encounter_id) for x in hm.cells] == [("l1", None), ("l1", "l1.boss"), ("l2", None),
                                                                ("l2", "l2.e1")]
    boss = hm.cell("l1", "l1.boss")
    assert (boss.players, boss.attempts, boss.completions, boss.failures, boss.deaths) == (10, 14, 6, 4, 4)
    assert boss.fail_rate == 0.4 and boss.drop_off_rate == 0.4 and boss.difficulty == 0.4
    assert boss.median_clear_s == 10.0 and boss.attempts_per_clear == pytest.approx(14 / 6, abs=1e-3)
    assert hm.cell("l2", "l2.e1").players == 0 and hm.cell("l2", "l2.e1").low_confidence
    assert boss.difficulty > hm.cell("l2").difficulty
    d = json.loads(hm.to_json())
    assert d["schema"].endswith("difficulty_heatmap.v1")
    assert DifficultyHeatmap.from_dict(d) == hm


def test_heatmap_suppresses_small_cells_and_ignores_unknown_ids():
    c = collector()
    play(c, "a", "s", [("level_start", "secret", None), ("level_start", "l2", None)])
    hm = difficulty_heatmap(c.events, PLAN, min_players=5)
    assert hm.suppressed == 1 and hm.cell("l2") is None and hm.cell("secret") is None
    assert difficulty_heatmap(c.events, min_players=1).cell("secret").attempts == 1


def test_analytics_unsampled_infinite_batch_stops_at_row_budget(monkeypatch):
    from itertools import repeat
    from skeleton.ai.game_builder.analytics import privacy as privacy_module

    monkeypatch.setattr(privacy_module, "MAX_BATCH_INGEST_ROWS", 3)
    c = Collector(PrivacyPolicy(SALT, sample_rate=0.0))
    event = {"seq": 0, "t": 0, "type": "session_start"}
    with pytest.raises(privacy_module.EventCapacityError, match="row budget"):
        c.ingest_many(repeat(("a", "s", event)))
    assert c.events == []
    assert c.counts["unsampled"] == 3


def test_heatmap_privacy_threshold_cannot_be_disabled_or_forged():
    c = collector()
    play(c, "single-player", "single-session", [("level_start", "l1", None)])
    for invalid in (0, -1, True, 1.5, 1_000_001):
        with pytest.raises(ValueError, match="min_players"):
            difficulty_heatmap(c.events, PLAN, min_players=invalid)

    valid = difficulty_heatmap(c.events, PLAN, min_players=5).to_dict()
    assert valid["suppressed"] == 1
    for invalid in (0, -1, True, "5"):
        forged = {**valid, "min_players": invalid}
        with pytest.raises(ValueError, match="min_players"):
            DifficultyHeatmap.from_dict(forged)

    disclosed = difficulty_heatmap(c.events, PLAN, min_players=1).to_dict()
    assert disclosed["cells"][0]["players"] == 1
    disclosed["min_players"] = 5
    with pytest.raises(ValueError, match="minimum player threshold"):
        DifficultyHeatmap.from_dict(disclosed)
