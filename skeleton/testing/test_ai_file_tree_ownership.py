from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scripts import check_ai_file_tree_ownership as ownership


ROOT = Path(__file__).resolve().parents[2]


def _manifest() -> dict:
    return {
        "schema_version": 1,
        "baseline_git_sha": "0" * 40,
        "canonical_root": "skeleton/ai",
        "mappings": [
            {
                "id": "AIFT-RUNTIME",
                "source": "skeleton/runtime",
                "destination": "skeleton/ai/runtime",
                "kind": "tree",
                "source_git_object_sha": "1" * 40,
                "source_disposition": "retain_until_cutover",
            }
        ],
        "native_ai_owners": [
            {
                "id": "AIFT-NATIVE-TOOLS",
                "path": "skeleton/ai/native",
                "kind": "tree",
                "ownership_mode": "canonical_native",
                "residual_only": False,
            }
        ],
    }


def _tracked() -> list[str]:
    return [
        "skeleton/ai/runtime/core.py",
        "skeleton/ai/native/tool.py",
    ]


def test_synthetic_graph_is_complete_and_deterministic() -> None:
    manifest = _manifest()
    first = ownership.build_ownership_graph(manifest, _tracked())
    second = ownership.build_ownership_graph(
        deepcopy(manifest),
        reversed(_tracked()),
    )

    assert first["valid"] is True
    assert first["errors"] == []
    assert first["tracked_file_count"] == 2
    assert first["owned_file_count"] == 2
    assert first["graph_digest"] == second["graph_digest"]
    assert first["owner_file_counts"] == {
        "AIFT-NATIVE-TOOLS": 1,
        "AIFT-RUNTIME": 1,
    }


def test_unowned_ai_path_fails_closed() -> None:
    graph = ownership.build_ownership_graph(
        _manifest(),
        _tracked() + ["skeleton/ai/orphan.py"],
    )

    assert graph["valid"] is False
    assert any(
        error == "unowned AI-tree path: skeleton/ai/orphan.py"
        for error in graph["errors"]
    )


def test_native_owner_requires_explicit_mapping_overlay() -> None:
    manifest = _manifest()
    manifest["native_ai_owners"][0] = {
        "id": "AIFT-NATIVE-RUNTIME-EXTENSION",
        "path": "skeleton/ai/runtime/native",
        "kind": "tree",
        "ownership_mode": "canonical_native",
        "residual_only": False,
    }

    graph = ownership.build_ownership_graph(
        manifest,
        [
            "skeleton/ai/runtime/core.py",
            "skeleton/ai/runtime/native/extension.py",
        ],
    )

    assert graph["valid"] is False
    assert any(
        "without an explicit overlay" in error
        for error in graph["errors"]
    )


def test_explicit_overlay_routes_to_more_specific_native_owner() -> None:
    manifest = _manifest()
    manifest["mappings"][0]["overlay_children"] = ["native"]
    manifest["native_ai_owners"][0] = {
        "id": "AIFT-NATIVE-RUNTIME-EXTENSION",
        "path": "skeleton/ai/runtime/native",
        "kind": "tree",
        "ownership_mode": "canonical_native",
        "residual_only": False,
    }

    graph = ownership.build_ownership_graph(
        manifest,
        [
            "skeleton/ai/runtime/core.py",
            "skeleton/ai/runtime/native/extension.py",
        ],
    )

    assert graph["valid"] is True
    assert graph["owner_file_counts"] == {
        "AIFT-NATIVE-RUNTIME-EXTENSION": 1,
        "AIFT-RUNTIME": 1,
    }


def test_duplicate_mapping_destination_is_rejected() -> None:
    manifest = _manifest()
    duplicate = deepcopy(manifest["mappings"][0])
    duplicate["id"] = "AIFT-RUNTIME-DUPLICATE"
    duplicate["source"] = "skeleton/other-runtime"
    duplicate["source_git_object_sha"] = "2" * 40
    manifest["mappings"].append(duplicate)

    graph = ownership.build_ownership_graph(manifest, _tracked())

    assert graph["valid"] is False
    assert any(
        error == "duplicate mapping destination: skeleton/ai/runtime"
        for error in graph["errors"]
    )


def test_repository_ai_tree_has_one_effective_owner_per_tracked_file() -> None:
    receipt = ownership.verify_repository(ROOT)

    assert receipt["volume"] == "VOL-051"
    assert receipt["verifier"] == "independent-ai-file-tree-ownership-v1"
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["tracked_file_count"] > 0
    assert receipt["tracked_file_count"] == receipt["owned_file_count"]
    assert receipt["mapping_owner_count"] > 0
    assert receipt["native_owner_count"] > 0
    assert receipt["direct_ai_roots"]
    assert len(receipt["ownership_graph_digest"]) == 64
    assert len(receipt["receipt_digest"]) == 64


def test_repository_architecture_binds_ai_file_tree_authority() -> None:
    receipt = ownership.verify_repository(ROOT)

    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["canonical_root"] == "skeleton/ai"
    assert receipt["manifest_path"] == "machine/ai_file_tree.json"
    assert receipt["parity_validator"] == "scripts/check_ai_file_tree.py"
