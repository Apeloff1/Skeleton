"""Vault imports must remain side-effect free for backend route registration."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_compressed_vault_first_use_initializes_only_on_demand(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    scratch = tmp_path / "scratch"
    script = """
from pathlib import Path
from core import compressed_vault as storage
assert not storage.VAULT_ROOT.exists(), 'vault directory created during import'
assert not storage.SCRATCH_ROOT.exists(), 'scratch directory created during import'
assert storage.list_shards() == []
assert storage.VAULT_ROOT.is_dir(), 'vault not initialized on demand'
assert storage.SCRATCH_ROOT.is_dir(), 'scratch not initialized on demand'
assert storage.get_shard_entry('missing') is None
assert storage.vault_stats()['shard_count'] == 0
"""
    env = os.environ.copy()
    env["HYPERSCALE_VAULT_DIR"] = str(vault)
    env["HYPERSCALE_SCRATCH_DIR"] = str(scratch)
    backend = Path(__file__).resolve().parents[1]
    outcome = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert outcome.returncode == 0, outcome.stderr
