from skeleton.frontier.gameforge_event_bus import EventEnvelope
from skeleton.frontier.gameforge_replay import ReplayCursor

def test_replay_cursor_is_idempotent():
 c=ReplayCursor(); events=(EventEnvelope(0,"a"),EventEnvelope(1,"b")); assert [x.value for x in c.consume(events)]==["a","b"]; assert c.consume(events)==()
