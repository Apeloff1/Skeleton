from core.shift_supervisor.version import SUPERVISOR_SCHEMA_VERSION


def test_schema_version_is_non_empty():
    assert SUPERVISOR_SCHEMA_VERSION
