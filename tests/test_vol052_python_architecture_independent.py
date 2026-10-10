from __future__ import annotations

from copy import deepcopy
import json
import shutil
import tempfile
from pathlib import Path

from scripts import verify_vol052_python_architecture as verifier


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vol052-independent-"))
    for relative in (
        verifier.MASTER,
        verifier.LAYERS,
        verifier.REGISTRY,
        verifier.VALIDATOR,
        verifier.TESTS,
        Path("skeleton/kernel"),
        Path("skeleton/contracts"),
        Path("skeleton/providers"),
        Path("skeleton/context"),
        Path("skeleton/persistence"),
        Path("skeleton/retrieval"),
        Path("skeleton/memory"),
        Path("skeleton/intelligence"),
        Path("skeleton/frontier"),
        Path("skeleton/skills"),
        Path("skeleton/agents"),
        Path("skeleton/automation"),
        Path("skeleton/forge"),
        Path("skeleton/jeeves"),
        Path("skeleton/pipelines"),
        Path("skeleton/api"),
        Path("skeleton/deploy"),
        Path("skeleton/__main__.py"),
    ):
        source = ROOT / relative
        target = temp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    return temp


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_current_repository_passes_independent_vol052_verification() -> None:
    receipt = verifier.verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["volume"] == "VOL-052"
    assert receipt["layer_binding"]["layer_count"] == 5
    assert receipt["layer_binding"]["layer_names"] == [
        "foundation",
        "contracts",
        "runtime-services",
        "orchestration",
        "adapters",
    ]
    assert receipt["registry_binding"]["rule_id"] == "ARCH-PYTHON-LAYERS"
    assert len(receipt["receipt_digest"]) == 64


def test_rejects_upward_permission_in_machine_manifest() -> None:
    root = _fixture()
    path = root / verifier.LAYERS
    data = _load(path)
    data["layers"][0]["allowed_layer_ids"].append("PY-L4")
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("upward dependency permission" in error for error in receipt["errors"])


def test_rejects_duplicate_classified_path_owner() -> None:
    root = _fixture()
    path = root / verifier.LAYERS
    data = _load(path)
    data["layers"][1]["paths"].append("skeleton/kernel")
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "multiple direct owners" in error
        for error in receipt["errors"]
    )


def test_rejects_architecture_rule_downgrade() -> None:
    root = _fixture()
    path = root / verifier.REGISTRY
    data = _load(path)
    rule = next(
        item
        for item in data["rules"]
        if item["id"] == "ARCH-PYTHON-LAYERS"
    )
    rule["severity"] = "advisory"
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("severity must remain blocking" in error for error in receipt["errors"])


def test_rejects_masterplan_gap_binding_loss() -> None:
    root = _fixture()
    path = root / verifier.MASTER
    data = _load(path)
    volume = next(item for item in data["volumes"] if item["key"] == "VOL-052")
    volume["gaps"].remove("add import graph fitness test")
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("gap binding drift" in error for error in receipt["errors"])


def test_rejects_validator_contract_weakening() -> None:
    root = _fixture()
    path = root / verifier.VALIDATOR
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "runtime sys.path/PYTHONPATH mutation is forbidden",
        "runtime path mutation ignored",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("validator invariant missing" in error for error in receipt["errors"])
