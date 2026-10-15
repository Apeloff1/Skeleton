"""Real Jeeves catalogue, project-partition and tamper regression coverage."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import pytest

from skeleton.ai.training.jeeves_multidomain import (
    SCHEMA, digest_with_mirrors, generate_modules, load_multidomain_corpus,
    validate_catalog,
)
from skeleton.ai.training.jeeves_parallel_mirrors import run_parallel_candidates


def _fixture(folder: Path, *, dual_views: bool = False) -> Path:
    folder.mkdir(parents=True)
    train, held = [], []
    for domain, topic in (("gaming", "world"), ("ai", "evaluation"), ("coding", "testing")):
        for i in range(9):
            split = "train" if i < 6 else "heldout"
            row = {
                "id": f"{domain}-{i}-example", "module_id": f"jeeves.{domain}.{topic}.construct",
                "split": split,
                "source_project_id": ("authored-a" if i % 2 else "authored-b")
                if split == "train" else ("review-a" if i % 2 else "review-b"),
                "prompt": (f"Investigate {domain} case {i} with separately authored sources and reproducible system behavior."
                           if split == "train" else
                           f"Study new {domain} evaluation experiment {i} with alternative corrective design evidence."),
                "answer": (f"An original {domain} implementation for case {i} describes assumptions, tradeoffs, and observable outcome."
                           if split == "train" else
                           f"Independent {domain} evaluation response {i} specifies bounded edge conditions and review receipts."),
                "rights": {"training_permitted": True, "human_reviewed": True,
                           "source_ref": f"homebrew:{domain}:{i}",
                           "rights_basis": "Original material with explicit review"},
            }
            (train if split == "train" else held).append(row)
        if dual_views:
            for i in range(9, 15):
                train.append({
                    "id": f"{domain}-{i}-counterexample",
                    "module_id": f"jeeves.{domain}.{topic}.counterexample",
                    "split": "train",
                    "source_project_id": "authored-a" if i % 2 else "authored-b",
                    "prompt": f"Challenge the independent {domain} implementation {i} with a different original counterexample and failure proof.",
                    "answer": f"Adversarial {domain} case {i} provides a documented violating input, reproducible observations and scoped correction.",
                    "rights": {"training_permitted": True, "human_reviewed": True,
                               "source_ref": f"homebrew:{domain}:{i}",
                               "rights_basis": "Original material with explicit review"},
                })
    def dump(name, rows):
        raw = b"".join((json.dumps(row, sort_keys=True) + "\n").encode() for row in rows)
        (folder / name).write_bytes(raw)
        return sha256(raw).hexdigest()
    train_sha = dump("train.jsonl", train)
    held_sha = dump("heldout.jsonl", held)
    manifest = folder / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": SCHEMA, "rights_reviewed": True, "review_id": "fixture-independent-review",
        "train_file": "train.jsonl", "heldout_file": "heldout.jsonl",
        "train_sha256": train_sha, "heldout_sha256": held_sha,
    }))
    return manifest


def test_576_unique_executable_specialization_routes():
    rows = generate_modules()
    assert len(rows) == 576
    assert len({m["module_id"] for m in rows}) == 576
    assert {m["domain"] for m in rows} == {"gaming", "ai", "coding"}
    assert validate_catalog()["catalogue_valid"] is True


def test_concurrent_four_angle_digest_never_claims_weight_training(tmp_path):
    m = _fixture(tmp_path / "corpus")
    train, held, receipt = load_multidomain_corpus(m)
    assert len(train) == 18 and sum(len(v) for v in held.values()) == 9
    assert "Jeeves module jeeves.gaming.world.construct" in train[0]
    assert "Objective:" in train[0] and "Lens:" in train[0]
    assert "Constraints:" in train[0] and " Jeeves: " in train[0]
    assert not receipt["heldout_used_for_training"]
    output = digest_with_mirrors(m, workers=4)
    assert output["active_modules"] == 3 and len(output["mirrors"]) == 4
    assert all(part["weight_updates"] == 0 for part in output["mirrors"])
    assert not output["actual_candidate_training_executed"]


def test_changed_heldout_hash_fails_closed(tmp_path):
    m = _fixture(tmp_path / "tamper")
    with (m.parent / "heldout.jsonl").open("ab") as writer:
        writer.write(b"tamper\n")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_multidomain_corpus(m)


def test_cross_split_project_is_rejected(tmp_path):
    m = _fixture(tmp_path / "leak")
    target = m.parent / "heldout.jsonl"
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    rows[0]["source_project_id"] = "authored-a"
    raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
    target.write_bytes(raw)
    conf = json.loads(m.read_text()); conf["heldout_sha256"] = sha256(raw).hexdigest()
    m.write_text(json.dumps(conf))
    with pytest.raises(ValueError, match="source-project leakage"):
        load_multidomain_corpus(m)


def test_missing_live_attestation_does_not_create_weights(tmp_path, monkeypatch):
    m = _fixture(tmp_path / "closed", dual_views=True)
    output = tmp_path / "candidate"; output.mkdir()
    monkeypatch.delenv("SKELETON_OWN", raising=False)
    with pytest.raises((OSError, ValueError), match="SKELETON_OWN|attestation|checkpoint"):
        run_parallel_candidates(
            catalog_path=Path("machine/jeeves_training_modules.json"),
            manifest_path=m, attestation_path=tmp_path / "missing-attestation.json",
            output_directory=output, receipt_path=output / "receipt.json")
    assert list(output.iterdir()) == []

def test_optimizer_mirrors_refuse_unreviewed_adversarial_examples(tmp_path):
    m = _fixture(tmp_path / "one-sided")
    train, heldout, receipt = load_multidomain_corpus(m, training_view="constructive")
    assert len(train) == 18 and receipt["training_view"] == "constructive"
    with pytest.raises(ValueError, match="adversarial training view lacks"):
        load_multidomain_corpus(m, training_view="adversarial")
    with pytest.raises(ValueError, match="unknown optimizer training view"):
        load_multidomain_corpus(m, training_view="unreviewed")

def test_reviewed_mirror_views_use_distinct_specialist_lessons(tmp_path):
    m = _fixture(tmp_path / "dual", dual_views=True)
    constructive, held_a, receipt_a = load_multidomain_corpus(m, training_view="constructive")
    adversarial, held_b, receipt_b = load_multidomain_corpus(m, training_view="adversarial")
    assert len(constructive) == 18 and len(adversarial) == 18
    assert not (set(constructive) & set(adversarial))
    assert held_a == held_b
    assert receipt_a["manifest_sha256"] == receipt_b["manifest_sha256"]
    assert receipt_a["training_view"] == "constructive"
    assert receipt_b["training_view"] == "adversarial"
