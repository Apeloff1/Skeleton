"""Regression coverage for runtime lifecycle export boundaries."""

from skeleton.application.runtime_lifecycle_factory import (
    build_lifecycle_command_service,
)


def test_lifecycle_factory_is_importable():
    """The lifecycle factory remains a stable application integration seam."""

    assert callable(build_lifecycle_command_service)
