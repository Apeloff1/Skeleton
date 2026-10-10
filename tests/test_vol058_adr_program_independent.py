from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from scripts import verify_vol058_adr_program as verifier


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vol058-independent-"))
    for relative in (
        verifier.MASTER,
        verifier.INDEX,
        verifier.REGISTRY,
        verifier.VALIDATOR,
        verifier.TESTS,
        verifier.ADR_DIR,
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


def test_current_repository_passes_independent_vol058_verification() -> None:
    receipt = verifier.verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["volume"] == "VOL-058"
    assert receipt["index_binding"]["record_count"] >= 1
    assert (
        receipt["index_binding"]["record_count"]
        == receipt["index_binding"]["document_count"]
    )
    assert receipt["index_binding"]["governed_pattern_count"] >= 5
    assert receipt["registry_binding"]["rule_id"] == "ARCH-ADR-INDEX"
    assert receipt["registry_binding"]["waivable"] is False
    assert len(receipt["receipt_digest"]) == 64


def test_rejects_unindexed_adr_document() -> None:
    root = _fixture()
    extra = root / verifier.ADR_DIR / "ADR-9999-unindexed.md"
    extra.write_text("# unindexed\n", encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("document/index coverage drift" in error for error in receipt["errors"])


def test_rejects_inactive_governed_path_coverage() -> None:
    root = _fixture()
    path = root / verifier.INDEX
    data = _load(path)
    governed = data["governed_path_patterns"][0]
    for record in data["records"]:
        if record["status"] in data["policy"]["active_statuses"]:
            record["impacted_paths"] = [
                item for item in record["impacted_paths"] if item != governed
            ]
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("lack active ADR impact" in error for error in receipt["errors"])


def test_rejects_unknown_masterplan_reference() -> None:
    root = _fixture()
    path = root / verifier.INDEX
    data = _load(path)
    data["records"][0]["masterplan_refs"].append("VOL-999")
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("unknown masterplan refs" in error for error in receipt["errors"])


def test_rejects_adr_rule_becoming_waivable() -> None:
    root = _fixture()
    path = root / verifier.REGISTRY
    data = _load(path)
    rule = next(item for item in data["rules"] if item["id"] == "ARCH-ADR-INDEX")
    rule["waiver_policy"]["allowed"] = True
    rule["waiver_policy"]["max_ttl_days"] = 7
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("must remain non-waivable" in error for error in receipt["errors"])


def test_rejects_masterplan_gap_binding_loss() -> None:
    root = _fixture()
    path = root / verifier.MASTER
    data = _load(path)
    volume = next(item for item in data["volumes"] if item["key"] == "VOL-058")
    volume["gaps"].remove("bind cross-cutting changes to ADR check")
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("gap binding drift" in error for error in receipt["errors"])


def test_rejects_supersession_guard_weakening() -> None:
    root = _fixture()
    path = root / verifier.VALIDATOR
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "superseded record needs superseded_by",
        "superseded record may omit replacement",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("ADR invariant missing" in error for error in receipt["errors"])
