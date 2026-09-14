from __future__ import annotations

from datetime import datetime

import pytest

from core.deployment_checkpoint_ledger import DeploymentCheckpointLedger
from core.deployment_checkpoint_pin_ledger import DeploymentCheckpointPinLedger
from core.transparency_witness import TrustedWitness


def test_enabled_checkpoint_witness_key_is_validated_at_construction(tmp_path):
    checkpoints = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    with pytest.raises(ValueError, match="malformed Ed25519 public key"):
        DeploymentCheckpointPinLedger(
            tmp_path / "pins",
            checkpoint_ledger=checkpoints,
            trusted_witnesses=(TrustedWitness("w0", "org-a", True, "not-base64"),),
            required_groups=1,
        )


def test_naive_datetime_fails_before_local_timezone_conversion(tmp_path):
    checkpoints = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    ledger = DeploymentCheckpointPinLedger(
        tmp_path / "pins",
        checkpoint_ledger=checkpoints,
        trusted_witnesses=(),
        required_groups=1,
    )
    naive = datetime(2026, 9, 14, 20, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        ledger.quorum(now=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        ledger.portable_bundle(now=naive)
