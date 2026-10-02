from __future__ import annotations

import pytest

from scripts.prepare_p2_tranche1_activation import (
    P2Tranche1ActivationError,
    build_activation_proposal,
)


def test_reactivation_is_fail_closed() -> None:
    with pytest.raises(P2Tranche1ActivationError, match="already activated"):
        build_activation_proposal()
