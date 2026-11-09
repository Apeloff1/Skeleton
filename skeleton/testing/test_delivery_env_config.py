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


def test_layer_json_rejects_duplicate_keys_and_nonfinite_values():
    for raw in (
        '{"tier":"production","tier":"dev"}',
        '{"health":{"path":"/ready","path":"/health"}}',
        '{"replicas":NaN}', '{"replicas":Infinity}', '{"replicas":-Infinity}',
    ):
        with pytest.raises(DeliveryError, match="duplicate|non.?finite"):
            load_layers({"dev": raw})
    assert load_layers({"dev": '{"tier":"dev"}'}) == {"dev": {"tier": "dev"}}


def test_layer_inventory_and_text_are_bounded(monkeypatch):
    from skeleton.build.delivery import env_config as module

    monkeypatch.setattr(module, "MAX_LAYER_JSON_CHARS", 8)
    with pytest.raises(DeliveryError, match="exceeds bound"):
        load_layers({"dev": '{"tier":"dev"}'})
    with pytest.raises(DeliveryError, match="exceeds bound"):
        load_layers({"dev": 12})
    monkeypatch.setattr(module, "MAX_CONFIG_LAYERS", 1)
    with pytest.raises(DeliveryError, match="inventory exceeds"):
        load_layers({"dev": "{}", "staging": "{}"})


def test_json_parser_resource_failures_are_typed_and_transactional():
    from skeleton.ai.build.core.delivery import env_config as mirrored

    nested = '{"x":' * 1200 + '0' + '}' * 1200
    for load in (load_layers, mirrored.load_layers):
        with pytest.raises(DeliveryError, match="invalid JSON"):
            load({"dev": nested})


def test_layer_loader_bounds_malicious_mapping_iteration():
    from itertools import count
    from skeleton.ai.build.core.delivery import env_config as mirrored

    class UnboundedLayers(dict):
        def items(self):
            return ((f"env{i}", "{}") for i in count())

    for load in (load_layers, mirrored.load_layers):
        with pytest.raises(DeliveryError, match="inventory exceeds bound"):
            load(UnboundedLayers())
