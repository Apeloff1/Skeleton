"""An unknown target is not journaled as a finished materialisation."""

import pytest

from skeleton.forge.universal import Forge
from skeleton.kernel.errors import MaterialisationError


class _Blueprint:
    blueprint_id = "bp"
    name = "demo"

    def validate(self):
        raise AssertionError("an unknown target must fail before validation")


def test_an_unknown_target_is_refused() -> None:
    forge = Forge()
    with pytest.raises(MaterialisationError):
        forge.materialise(_Blueprint(), target="pdf")
    with pytest.raises(ValueError):
        forge.materialise(_Blueprint(), repair="false")
    with pytest.raises(ValueError):
        forge.materialise(_Blueprint(), max_rounds=True)
