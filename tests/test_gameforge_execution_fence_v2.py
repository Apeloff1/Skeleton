from skeleton.frontier.gameforge_execution_fence_v2 import ExecutionFenceV2


def test_fence_allows_one_acquisition():
    fence = ExecutionFenceV2()
    assert fence.acquire()
    assert fence.closed
    assert not fence.acquire()
