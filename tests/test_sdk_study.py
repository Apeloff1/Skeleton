"""Focused fail-closed SDK ingestion and candidate-corpus integration tests."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from skeleton.ai.training.sdk_study import (
    SDKStudyError, SDK_SCHEMA, REVIEW_SCHEMA, extend_multidomain,
    target_inventory, validate_sources,
)
from skeleton.ai.training.jeeves_multidomain import (
    SCHEMA as MULTI_SCHEMA, generate_modules, load_multidomain_corpus,
)


def _write(path: Path, value: object):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def _sources(tmp_path: Path, *, admitted: bool = True):
    sdk = tmp_path / "installed" / "rgbds"
    sdk.mkdir(parents=True)
    raw = b"An original example of how a typed tile identifier is used.\n"
    (sdk / "README.md").write_bytes(raw)
    source_hash = sha256(raw).hexdigest()
    source = {
        "schema_version": SDK_SCHEMA,
        "sdks": [{
            "sdk_id": "rgbds", "version": "v1", "target_ids": ["game_boy"],
            "root": str(sdk),
            "documents": [{"path": "README.md", "sha256": source_hash}],
            "rights": {
                "training_permitted": admitted,
                "human_reviewed": admitted,
                "rights_holder": "Original author",
                "rights_basis": "original:author-owned examples",
                "review_id": "review-sdk-001",
            },
        }],
    }
    manifest = _write(tmp_path / "source.json", source)
    return manifest, source_hash, sdk


def _corpus(tmp_path: Path):
    root = tmp_path / "base"
    root.mkdir()
    modules = generate_modules()
    domain_ids = {
        domain: next(m["module_id"] for m in modules
                     if m["domain"] == domain and m["lens"] == "construct")
        for domain in ("gaming", "ai", "coding")
    }
    vocab = ["quartz", "vortex", "cedar", "selenium", "marigold", "citadel",
             "horizon", "mosaic", "willow", "octagon", "meadow", "cobalt",
             "saffron", "quiver", "tundra", "pinnacle", "aurora", "stellar",
             "indigo", "orchid", "harvest", "ripple", "bramble", "silicon",
             "topaz", "plasma", "amber", "valley"]
    for split, per_domain in (("train", 6), ("heldout", 3)):
        rows = []
        for domain in domain_ids:
            for n in range(per_domain):
                k = len(rows) + (0 if split == "train" else 18)
                word = vocab[k]
                rows.append({
                    "id": "base." + split + "." + str(k),
                    "source_project_id": "base." + split + "." + str(n % 3),
                    "split": split,
                    "module_id": domain_ids[domain],
                    "prompt": "Explain the " + word + " abstraction and its typed ownership boundaries.",
                    "answer": "For the " + word + " abstraction, build a unique explicit contract with a narrow proof and deterministic repair plan.",
                    "rights": {
                        "training_permitted": True, "human_reviewed": True,
                        "source_ref": "original-" + word,
                        "rights_basis": "original:operator-authored",
                    },
                })
        data = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
        (root / (split + ".jsonl")).write_bytes(data)
        if split == "train":
            tr = sha256(data).hexdigest()
        else:
            he = sha256(data).hexdigest()
    manifest = {
        "schema_version": MULTI_SCHEMA, "rights_reviewed": True,
        "review_id": "base-human-approved", "train_file": "train.jsonl",
        "train_sha256": tr, "heldout_file": "heldout.jsonl",
        "heldout_sha256": he,
    }
    return _write(root / "manifest.json", manifest)


def test_inventory_does_not_claim_training():
    report = target_inventory()
    assert report["canonical_target_count"] > 20
    assert not report["training_executed"]
    assert not report["production_weights_modified"]
    assert all(not row["compile_verified"] for row in report["targets"])


def test_exact_sdk_pins_and_rights(tmp_path):
    path, digest, sdk = _sources(tmp_path)
    receipt, source_map = validate_sources(path)
    assert receipt["admitted_documents"] == 1
    assert source_map[digest]["trainable"]
    (sdk / "README.md").write_text("Changed without review", encoding="utf-8")
    with pytest.raises(SDKStudyError, match="changed"):
        validate_sources(path)


def test_unreviewed_sdk_inventory_never_trainable(tmp_path):
    path, digest, _ = _sources(tmp_path, admitted=False)
    receipt, entries = validate_sources(path)
    assert receipt["admitted_documents"] == 0
    assert not entries[digest]["trainable"]


def test_symlink_and_traversal_blocked(tmp_path):
    path, _, sdk = _sources(tmp_path)
    (sdk / "link.md").symlink_to(sdk / "README.md")
    source = json.loads(path.read_text())
    source["sdks"][0]["documents"][0]["path"] = "link.md"
    _write(path, source)
    with pytest.raises(SDKStudyError, match="symlink"):
        validate_sources(path)
    source["sdks"][0]["documents"][0]["path"] = "../README.md"
    _write(path, source)
    with pytest.raises(SDKStudyError, match="unsafe"):
        validate_sources(path)


def test_merge_uses_existing_trainer_validation_and_never_touches_weights(tmp_path):
    src, source_hash, _ = _sources(tmp_path)
    baseline = _corpus(tmp_path)
    load_multidomain_corpus(baseline)
    review = {
        "schema_version": REVIEW_SCHEMA, "id": "sdk.rgbds.exam01",
        "sdk_id": "rgbds", "source_sha256": source_hash, "split": "train",
        "module_id": "jeeves.coding.types.construct",
        "prompt": "Explain original tile identifier typing for this source SDK version.",
        "answer": "Use original typed tile identifiers derived from a reviewed documented source, keeping layouts and compile details explicit.",
        "quality_approved": True, "quality_reviewer_id": "human-technical-operator",
        "quality_review_note": "This answer was checked against the original pinned README and reviewed for accuracy.",
    }
    review_path = tmp_path / "review.jsonl"
    review_path.write_text(json.dumps(review) + "\n", encoding="utf-8")
    out = tmp_path / "published"
    out.mkdir()
    result = extend_multidomain(src, review_path, baseline, out,
                                prefix="sdk_train_001", review_id="human-review-signed-001")
    assert result["sdk_reviewed_rows"] == 1
    assert result["checkpoint_touched"] is False
    assert result["model_training_executed"] is False
    training, heldout, proof = load_multidomain_corpus(Path(result["manifest"]))
    assert len(training) == 19
    assert sum(map(len, heldout.values())) == 9
    assert proof["independent_projects"]
    with pytest.raises(SDKStudyError, match="already published"):
        extend_multidomain(src, review_path, baseline, out,
                           prefix="sdk_train_001", review_id="human-review-signed-001")


def test_no_automatic_rights_or_quality_approval(tmp_path):
    src, digest, _ = _sources(tmp_path, admitted=False)
    base = _corpus(tmp_path)
    reviewed = tmp_path / "review.jsonl"
    row = {
        "schema_version": REVIEW_SCHEMA, "id": "sdk.rgbds.exam01",
        "sdk_id": "rgbds", "source_sha256": digest, "split": "train",
        "module_id": "jeeves.coding.types.construct",
        "prompt": "Explain SDK source ownership and explicit version pinning.",
        "answer": "Use a verified documentation digest as evidence and never imply native binary certification.",
        "quality_approved": True, "quality_reviewer_id": "human-reviewer",
        "quality_review_note": "Reviewed against the original SDK documentation and checked the answer.",
    }
    reviewed.write_text(json.dumps(row) + "\n")
    dest = tmp_path / "published"
    dest.mkdir()
    with pytest.raises(SDKStudyError, match="not admitted"):
        extend_multidomain(src, reviewed, base, dest,
                           prefix="blocked_sdk_001", review_id="human-review-signed-001")
    assert list(dest.iterdir()) == []
