from skeleton.automation import definition_of_done as compatibility
from skeleton.contracts import definition_of_done as canonical


def test_automation_dod_surface_has_no_parallel_authority() -> None:
    assert compatibility.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(compatibility, name) is getattr(canonical, name)
