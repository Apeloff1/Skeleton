import math

import pytest

from skeleton.frontier.execution import ExecutionPolicy


@pytest.mark.parametrize("field,value", [
    ("max_concurrency", 0), ("max_concurrency", True), ("max_queue", -1),
    ("max_queue", 1.5), ("execution_timeout", math.nan),
    ("queue_timeout", math.inf), ("event_timeout", 0),
    ("max_payload_bytes", False), ("max_attempts", 11), ("retry_delay", "1"),
])
def test_limits_reject_invalid_values(field, value):
    with pytest.raises(ValueError):
        ExecutionPolicy(**{field: value})


def test_retry_backoff_is_capped():
    policy = ExecutionPolicy(max_queue=0, retry_delay=0.25, max_retry_delay=1)
    assert [policy.backoff(i) for i in range(1, 6)] == [0.25, 0.5, 1, 1, 1]
    with pytest.raises(ValueError):
        ExecutionPolicy(retry_delay=2, max_retry_delay=1)
