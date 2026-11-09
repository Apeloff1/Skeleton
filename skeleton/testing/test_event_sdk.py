import pytest
from skeleton.frontier.event_sdk import *
def test_duplicate_is_idempotent(): 
 sdk=EventSDK();e=sdk.envelope(EventPublisher("x","v1"),"1",{});sdk,ok=sdk.consume(EventConsumer("c","x","v1"),e);sdk,again=sdk.consume(EventConsumer("c","x","v1"),e);assert ok and not again
def test_schema_drift_fails():
 with pytest.raises(ValueError):EventSDK().consume(EventConsumer("c","x","v2"),{"id":"1","schema":"x","version":"v1","payload":{}})

def test_malformed_envelope_rejected():
 import pytest
 with pytest.raises(ValueError):EventSDK().consume(EventConsumer("c","s","v"),{"id":"e"})
