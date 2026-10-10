from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from scripts import verify_vol054_manifest_references as verifier


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vol054-independent-"))
    policy = json.loads((ROOT / verifier.POLICY).read_text(encoding="utf-8"))
    paths: set[Path] = {
        verifier.MASTER,
        verifier.POLICY,
        verifier.REGISTRY,
        verifier.VALIDATOR,
        verifier.TESTS,
    }
    for group in policy["reference_groups"]:
        manifest = Path(group["manifest"])
        paths.add(manifest)
        payload = json.loads((ROOT / manifest).read_text(encoding="utf-8"))
        current = payload
        for raw in group["json_pointer"].split("/")[1:]:
            token = raw.replace("~1", "/").replace("~0", "~")
            current = current[token]
        values = list(current.values()) if group["kind"] == "repo_path_map" else [current]
        paths.update(Path(value) for value in values)
    for binding in policy["doc_bindings"]:
        paths.add(Path(binding["source"]))
        paths.add(Path(binding["doc"]))

    for relative in sorted(paths, key=lambda value: value.as_posix()):
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
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_current_repository_passes_independent_vol054_verification() -> None:
    receipt = verifier.verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["volume"] == "VOL-054"
    assert receipt["volume_binding"]["implementation_status"] in {
        "implemented",
        "hardened",
        "verified",
    }
    assert receipt["policy_binding"]["reference_group_count"] >= 5
    assert receipt["policy_binding"]["checked_reference_count"] > 0
    assert receipt["policy_binding"]["doc_binding_count"] >= 5
    assert receipt["registry_binding"]["rule_id"] == "ARCH-MANIFEST-REFERENCES"
    assert receipt["registry_binding"]["waivable"] is False
    assert len(receipt["receipt_digest"]) == 64


def test_rejects_schema_downgrade() -> None:
    root = _fixture()
    path = root / verifier.POLICY
    data = _load(path)
    data["schema_version"] = "skeleton.architecture.manifest_reference_policy.v0"
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("schema downgrade" in error for error in receipt["errors"])


def test_rejects_missing_reference_target() -> None:
    root = _fixture()
    policy = _load(root / verifier.POLICY)
    group = next(item for item in policy["reference_groups"] if item["kind"] == "repo_path")
    manifest_path = root / group["manifest"]
    manifest = _load(manifest_path)
    current = manifest
    tokens = group["json_pointer"].split("/")[1:]
    for token in tokens[:-1]:
        current = current[token]
    current[tokens[-1]] = "scripts/does-not-exist.py"
    _write(manifest_path, manifest)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("reference target missing" in error for error in receipt["errors"])


def test_rejects_stale_document_digest() -> None:
    root = _fixture()
    policy = _load(root / verifier.POLICY)
    binding = policy["doc_bindings"][0]
    source = root / binding["source"]
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "machine-git-blob marker missing/duplicated" in error
        for error in receipt["errors"]
    )


def test_rejects_manifest_rule_becoming_waivable() -> None:
    root = _fixture()
    path = root / verifier.REGISTRY
    data = _load(path)
    rule = next(
        item
        for item in data["rules"]
        if item["id"] == "ARCH-MANIFEST-REFERENCES"
    )
    rule["waiver_policy"]["allowed"] = True
    rule["waiver_policy"]["max_ttl_days"] = 7
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("must remain non-waivable" in error for error in receipt["errors"])


def test_rejects_old_implementation_gap_binding() -> None:
    root = _fixture()
    path = root / verifier.POLICY
    data = _load(path)
    data["masterplan_binding"]["required_gap_texts"] = [
        "unify manifest reference validation",
        "bind generated docs to manifest digests",
    ]
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("qualification-gap binding drift" in error for error in receipt["errors"])


def test_rejects_duplicate_doc_binding_source() -> None:
    root = _fixture()
    path = root / verifier.POLICY
    data = _load(path)
    duplicate = dict(data["doc_bindings"][0])
    duplicate["doc"] = data["doc_bindings"][1]["doc"]
    data["doc_bindings"].append(duplicate)
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("duplicate manifest doc-binding source" in error for error in receipt["errors"])
