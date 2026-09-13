import pytest
from skeleton.frontier.gameforge_limits import positive, non_negative

def test_limits_validate_bounds():
    assert positive(2) == 2
    assert non_negative(0) == 0
    with pytest.raises(ValueError): positive(0)
    with pytest.raises(ValueError): non_negative(-1)
