from core.shift_supervisor.config import SupervisorConfig


def test_supervisor_config_defaults(monkeypatch):
    for key in (
        "SHIFT_SECRETARY_INTERVAL_SECONDS",
        "SHIFT_MANAGER_INTERVAL_SECONDS",
        "SHIFT_NORMAL_MINUTES",
        "SHIFT_OVERTIME_SOFT_LIMIT_MINUTES",
    ):
        monkeypatch.delenv(key, raising=False)
    config = SupervisorConfig.from_env()
    assert config.secretary_interval_seconds == 900
    assert config.manager_interval_seconds == 1800
    assert config.normal_shift_minutes == 480
    assert config.overtime_soft_limit_minutes == 120
