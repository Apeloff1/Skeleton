import pytest
from skeleton.frontier.gameforge_lifecycle import Lifecycle,ServiceLifecycle

def test_lifecycle_is_explicit():
 s=ServiceLifecycle(); s.ready(); s.drain(); s.stop(); assert s.state is Lifecycle.STOPPED

def test_lifecycle_rejects_skip_to_drain():
 with pytest.raises(RuntimeError): ServiceLifecycle().drain()
