from pathlib import Path

import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.env_config import deep_merge, diff_configs, load_layers, resolve

ENV_DIR = Path(__file__).resolve().parents[1] / "build" / "delivery" / "envs"


def _layers():
    return load_layers({p.stem: p.read_text() for p in ENV_DIR.glob("*.json")})


def test_shipped_configs_resolve():
    layers = _layers()
    for name in ("dev", "staging", "production"):
        env = resolve(name, layers)
        assert env.tier == name
    prod = resolve("production", layers)
    assert prod.lineage == ("production", "staging", "base")
    assert prod.replicas == 4
    assert prod.get("health.path") == "/healthz"
    assert prod.get("health.max_latency_ms") == 800
    assert prod.get("features.debug_routes") is None


def test_deep_merge_and_delete():
    merged = deep_merge({"a": {"b": 1, "c": 2}, "d": 1}, {"a": {"b": 3}, "d": None})
    assert merged == {"a": {"b": 3, "c": 2}}


def test_validation_errors():
    base = {"tier": "production", "replicas": 1, "health": {"path": "/h"}, "rollout": {"strategy": "rolling"}}
    with pytest.raises(DeliveryError, match="2 replicas"):
        resolve("p", {"p": base})
    with pytest.raises(DeliveryError, match="secret"):
        resolve("p", {"p": base | {"replicas": 2, "token": "abc"}})
    with pytest.raises(DeliveryError, match="cycle"):
        resolve("a", {"a": {"extends": "b"}, "b": {"extends": "a"}})
    with pytest.raises(DeliveryError, match="unknown"):
        resolve("a", {"a": {"extends": "zz"}})


def test_digest_changes_with_values_and_diff():
    layers = _layers()
    staging, prod = resolve("staging", layers), resolve("production", layers)
    assert staging.digest != prod.digest
    diff = diff_configs(staging, prod)
    assert diff["replicas"] == (2, 4)
    assert diff["tier"] == ("staging", "production")


def test_load_layers_rejects_non_objects():
    with pytest.raises(DeliveryError):
        load_layers({"dev": "[]"})
    with pytest.raises(DeliveryError):
        load_layers({"dev": "{"})


@pytest.mark.parametrize("payload, fragment", [
    ('{"tier":"dev","tier":"production"}', "duplicate"),
    ('{"health":{"path":"/safe","path":"/other"}}', "duplicate"),
    ('{"tier":"dev","replicas":NaN}', "non-finite"),
    ('{"tier":"dev","replicas":Infinity}', "non-finite"),
    ('{"tier":"dev","replicas":-Infinity}', "non-finite"),
])
def test_load_layers_rejects_ambiguous_or_nonfinite_json(payload, fragment):
    with pytest.raises(DeliveryError, match=fragment):
        load_layers({"dev": payload})


def test_load_layers_rejects_oversized_untrusted_json():
    from skeleton.build.delivery.env_config import MAX_LAYER_BYTES

    with pytest.raises(DeliveryError, match="exceeds"):
        load_layers({"dev": " " * (MAX_LAYER_BYTES + 1)})
