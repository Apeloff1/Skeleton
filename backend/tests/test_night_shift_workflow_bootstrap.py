from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "night-shift.yml"
RUNTIME_INSTALL = 'run: python -m pip install "pydantic>=2.5,<3" "pydantic-settings>=2.1,<3"'
NIGHT_SHIFT_RUN = "run: python -m skeleton.automation.night_shift"


def test_night_shift_installs_required_runtime_slice_before_module_execution():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert RUNTIME_INSTALL in source
    assert NIGHT_SHIFT_RUN in source
    assert source.index(RUNTIME_INSTALL) < source.index(NIGHT_SHIFT_RUN)


def test_night_shift_keeps_checkout_credentials_disabled():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "persist-credentials: false" in source
