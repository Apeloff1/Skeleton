from skeleton.frontier.gameforge_fence import Fence

def test_fence_defaults_open_and_closes():
    f=Fence(); assert f.allow(); f.close(); assert not f.allow(); f.open(); assert f.allow()

def test_fence_can_start_closed():
    assert not Fence(False).allow()
