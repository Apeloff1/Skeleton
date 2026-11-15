"""Bounded local telemetry JSON, not device qualification."""
import pytest
from skeleton.ai.model_runtime.offline_json_guard import load_strict_telemetry_json


@pytest.mark.parametrize("raw", [b'{"x": 1, "x": 2}', b'{"x": 1e309}',
    b'{"x": NaN}', b'{"x": "\\ud800"}', b'{"\\udfff": 1}',
    b'{"x": ' + b'9' * 129 + b'}'])
def test_strict_json_rejects_noncanonical_or_unbounded_scalars(raw):
    with pytest.raises(ValueError):
        load_strict_telemetry_json(raw, max_bytes=4096)


def test_strict_json_applies_aggregate_structure_budget():
    with pytest.raises(ValueError, match="structure budget"):
        load_strict_telemetry_json(b'{"x": [0, 1, 2, 3]}', max_bytes=4096, max_nodes=5)
    with pytest.raises(ValueError, match="structure budget"):
        load_strict_telemetry_json(b'[[[0]]]', max_bytes=4096, max_depth=2)
    assert load_strict_telemetry_json(b'{"x": [0, 1]}', max_bytes=4096, max_nodes=4) == {"x": [0, 1]}


def test_json_integer_boundary_is_not_global_interpreter_setting():
    value = b'9' * 128
    assert load_strict_telemetry_json(value, max_bytes=4096) == int(value)
