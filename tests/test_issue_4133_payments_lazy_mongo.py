"""Regression guard for #4133: payments dependency + lazy Mongo at route import.

creator_economy/marketplace must resolve ``emergentintegrations.payments`` from
the local boot-safe layer (backend/emergentintegrations), and swarm_hub /
swarm_cold_legion must import without opening a Mongo client.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

_PROBE = r"""
import importlib, sys
mods = sys.argv[1:]
for m in mods:
    importlib.import_module("routes." + m)
import core.databases as d
pay = importlib.import_module("emergentintegrations.payments.stripe.checkout")
print("SYNC_CLIENT", d._sync_client is None)
print("PAYMENTS", pay.__file__)
"""


def _probe(*mods):
    env = dict(os.environ, MONGO_URL="mongodb://127.0.0.1:1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=os.pathsep.join([str(ROOT), str(BACKEND)]))
    return subprocess.run([sys.executable, "-c", _PROBE, *mods], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("mod", ["creator_economy", "marketplace"])
def test_payments_routes_import_with_local_compat_layer(mod):
    r = _probe(mod)
    assert r.returncode == 0, r.stderr[-2000:]
    pay_line = [l for l in r.stdout.splitlines() if l.startswith("PAYMENTS")][0]
    assert str(BACKEND / "emergentintegrations") in pay_line


@pytest.mark.parametrize("mod", ["swarm_hub", "swarm_cold_legion"])
def test_swarm_routes_do_not_connect_mongo_at_import(mod):
    r = _probe(mod)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "SYNC_CLIENT True" in r.stdout


def test_requirements_do_not_reintroduce_emergent_registry_sdk():
    req = (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert not any(l.strip().lower().startswith("emergentintegrations") for l in req)
