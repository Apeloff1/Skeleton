import pytest
from skeleton.frontier.gameforge_lifecycle import Lifecycle,ServiceLifecycle

def test_lifecycle_is_explicit():
 s=ServiceLifecycle(); assert not s.can_accept; s.ready(); assert s.can_accept; s.drain(); assert s.draining; s.stop(); assert s.state is Lifecycle.STOPPED

def test_lifecycle_rejects_skip_to_drain():
 with pytest.raises(RuntimeError): ServiceLifecycle().drain()
