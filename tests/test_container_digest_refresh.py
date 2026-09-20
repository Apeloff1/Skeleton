from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import container_digest_refresh as refresh


OLD_A = "a" * 64
OLD_B = "b" * 64
NEW_A = "c" * 64
NEW_B = "d" * 64
COMMIT = "1" * 40


def configure_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    files: dict[str, str],
) -> Path:
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    monkeypatch.setattr(refresh, "DEFAULT_FILES", tuple(files))
    monkeypatch.setattr(refresh, "DEFAULT_WORKFLOW_GLOB", ".github/workflows/*.yml")
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def one_pin_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reference: str = "python:3.14-alpine",
    digest: str = OLD_A,
) -> dict[str, object]:
    configure_repo(
        tmp_path,
        monkeypatch,
        {"Dockerfile": f"FROM {reference}@sha256:{digest}\n"},
    )
    return refresh.build_inventory()


def resolution(reference: str, digest: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": refresh.SCHEMA_VERSION,
        "resolver": "test-resolver",
        "resolved": {reference: digest},
    }
    payload["resolution_digest"] = refresh._json_digest(payload)
    return payload


def test_inventory_finds_dockerfile_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = one_pin_inventory(tmp_path, monkeypatch)
    assert payload["schema_version"] == 1
    pins = payload["pins"]
    assert isinstance(pins, list)
    assert len(pins) == 1
    assert pins[0]["query_reference"] == "python:3.14-alpine"
    assert pins[0]["old_digest"] == OLD_A
    assert pins[0]["occurrences"][0]["line"] == 1


def test_inventory_finds_yaml_image_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "docker-compose.yml": (
                "services:\n"
                "  mongo:\n"
                f"    image: mongo:7.0.41@sha256:{OLD_A}\n"
            )
        },
    )
    payload = refresh.build_inventory()
    assert refresh.inventory_queries(payload) == ("mongo:7.0.41",)


def test_inventory_finds_workflow_service_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    monkeypatch.setattr(refresh, "DEFAULT_FILES", ())
    monkeypatch.setattr(refresh, "DEFAULT_WORKFLOW_GLOB", ".github/workflows/*.yml")
    path = tmp_path / ".github/workflows/ci.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "jobs:\n"
        "  test:\n"
        "    services:\n"
        "      mongo:\n"
        f"        image: mongo:7@sha256:{OLD_A}\n",
        encoding="utf-8",
    )
    payload = refresh.build_inventory()
    assert refresh.inventory_queries(payload) == ("mongo:7",)


def test_comments_do_not_create_inventory_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": (
                f"# FROM fake:1@sha256:{OLD_B}\n"
                f"FROM python:3.14@sha256:{OLD_A}\n"
            )
        },
    )
    assert refresh.inventory_queries(refresh.build_inventory()) == ("python:3.14",)


def test_dockerfile_arg_is_expanded_for_registry_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "frontend/Dockerfile": (
                "ARG NODE_VERSION=24\n"
                f"FROM node:${{NODE_VERSION}}-alpine@sha256:{OLD_A} AS deps\n"
                f"FROM node:${{NODE_VERSION}}-alpine@sha256:{OLD_A} AS production\n"
            )
        },
    )
    payload = refresh.build_inventory()
    assert refresh.inventory_queries(payload) == ("node:24-alpine",)
    pin = payload["pins"][0]
    assert len(pin["occurrences"]) == 2
    assert all(
        item["raw_reference"] == "node:${NODE_VERSION}-alpine"
        for item in pin["occurrences"]
    )


def test_unresolved_dockerfile_arg_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": f"FROM node:${{NODE_VERSION}}-alpine@sha256:{OLD_A}\n"
        },
    )
    with pytest.raises(refresh.DigestRefreshPolicyError, match="unresolved"):
        refresh.build_inventory()


def test_dynamic_arg_value_is_not_used_for_registry_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": (
                "ARG NODE_VERSION=${OTHER}\n"
                f"FROM node:${{NODE_VERSION}}-alpine@sha256:{OLD_A}\n"
            )
        },
    )
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh.build_inventory()


def test_same_reference_occurrences_are_grouped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": f"FROM python:3.14@sha256:{OLD_A}\n",
            "backend/Dockerfile": (
                f"FROM python:3.14@sha256:{OLD_A} AS build\n"
                f"FROM python:3.14@sha256:{OLD_A} AS runtime\n"
            ),
        },
    )
    payload = refresh.build_inventory()
    pins = payload["pins"]
    assert len(pins) == 1
    assert len(pins[0]["occurrences"]) == 3


def test_same_reference_with_different_digest_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": f"FROM python:3.14@sha256:{OLD_A}\n",
            "backend/Dockerfile": f"FROM python:3.14@sha256:{OLD_B}\n",
        },
    )
    with pytest.raises(refresh.DigestRefreshPolicyError, match="inconsistent"):
        refresh.build_inventory()


def test_inventory_sources_are_content_addressed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = f"FROM python:3.14@sha256:{OLD_A}\n"
    configure_repo(tmp_path, monkeypatch, {"Dockerfile": text})
    payload = refresh.build_inventory()
    source = payload["sources"][0]
    assert source["size"] == len(text.encode())
    assert source["sha256"] == hashlib.sha256(text.encode()).hexdigest()


def test_inventory_digest_binds_all_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = one_pin_inventory(tmp_path, monkeypatch)
    expected = payload["inventory_digest"]
    unsigned = dict(payload)
    unsigned.pop("inventory_digest")
    assert expected == refresh._json_digest(unsigned)


def test_tampered_inventory_digest_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = one_pin_inventory(tmp_path, monkeypatch)
    payload["inventory_digest"] = "0" * 64
    with pytest.raises(refresh.DigestRefreshPolicyError, match="inventory digest"):
        refresh.inventory_queries(payload)


def test_inventory_queries_are_sorted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": (
                f"FROM zed:1@sha256:{OLD_A}\n"
                f"FROM alpha:2@sha256:{OLD_B}\n"
            )
        },
    )
    assert refresh.inventory_queries(refresh.build_inventory()) == ("alpha:2", "zed:1")


def test_reference_requires_explicit_tag() -> None:
    with pytest.raises(refresh.DigestRefreshPolicyError, match="explicit tag"):
        refresh._validate_query_reference("ubuntu")


@pytest.mark.parametrize(
    "reference",
    [
        "",
        " ubuntu:1",
        "ubuntu:1 ",
        "ubuntu:1\n",
        "ubuntu:1@sha256:" + OLD_A,
        "-q:1",
        "registry.example/-q:1",
    ],
)
def test_invalid_query_reference_is_rejected(reference: str) -> None:
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh._validate_query_reference(reference)


def test_resolution_tsv_is_normalized(tmp_path: Path) -> None:
    path = tmp_path / "resolved.tsv"
    path.write_text(
        f"python:3.14\tsha256:{NEW_A}\n"
        f"mongo:7\t{NEW_B}\n",
        encoding="utf-8",
    )
    payload = refresh.resolutions_from_tsv(path, resolver="docker-buildx")
    assert payload["resolved"] == {"mongo:7": NEW_B, "python:3.14": NEW_A}
    assert len(payload["resolution_digest"]) == 64


@pytest.mark.parametrize(
    "row",
    [
        "python:3.14",
        "python:3.14\tbad",
        "python:3.14\tsha256:xyz",
        "python:3.14\t" + ("a" * 63),
        "python:3.14\t" + ("a" * 65),
        "python:3.14\t" + ("A" * 64),
    ],
)
def test_resolution_tsv_rejects_malformed_rows(tmp_path: Path, row: str) -> None:
    path = tmp_path / "resolved.tsv"
    path.write_text(row + "\n", encoding="utf-8")
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh.resolutions_from_tsv(path, resolver="test")


def test_resolution_tsv_rejects_duplicate_reference(tmp_path: Path) -> None:
    path = tmp_path / "resolved.tsv"
    path.write_text(
        f"python:3.14\t{NEW_A}\npython:3.14\t{NEW_A}\n",
        encoding="utf-8",
    )
    with pytest.raises(refresh.DigestRefreshPolicyError, match="duplicate"):
        refresh.resolutions_from_tsv(path, resolver="test")


def test_resolution_tsv_rejects_empty_input(tmp_path: Path) -> None:
    path = tmp_path / "resolved.tsv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(refresh.DigestRefreshPolicyError, match="no image"):
        refresh.resolutions_from_tsv(path, resolver="test")


@pytest.mark.parametrize("resolver", ["", "   "])
def test_resolution_requires_named_resolver(tmp_path: Path, resolver: str) -> None:
    path = tmp_path / "resolved.tsv"
    path.write_text(f"python:3.14\t{NEW_A}\n", encoding="utf-8")
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh.resolutions_from_tsv(path, resolver=resolver)


def test_plan_contains_only_changed_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    assert len(plan["entries"]) == 1
    assert plan["entries"][0]["old_digest"] == OLD_A
    assert plan["entries"][0]["new_digest"] == NEW_A


def test_plan_omits_unchanged_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", OLD_A),
        source_commit=COMMIT,
    )
    assert plan["entries"] == []


def test_plan_requires_exact_resolution_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    with pytest.raises(refresh.DigestRefreshPolicyError, match="exactly"):
        refresh.build_plan(
            inventory,
            resolution("other:1", NEW_A),
            source_commit=COMMIT,
        )


@pytest.mark.parametrize("commit", ["", "abc", "g" * 40, "1" * 39, "1" * 41])
def test_plan_requires_exact_commit_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    commit: str,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh.build_plan(
            inventory,
            resolution("python:3.14-alpine", NEW_A),
            source_commit=commit,
        )


def test_plan_digest_is_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    resolved = resolution("python:3.14-alpine", NEW_A)
    first = refresh.build_plan(inventory, resolved, source_commit=COMMIT)
    second = refresh.build_plan(inventory, resolved, source_commit=COMMIT)
    assert first == second
    assert len(first["plan_digest"]) == 64


def test_tampered_resolution_digest_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    resolved = resolution("python:3.14-alpine", NEW_A)
    resolved["resolution_digest"] = "0" * 64
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh.build_plan(inventory, resolved, source_commit=COMMIT)


def test_apply_updates_exact_digest_and_emits_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    text = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert f"python:3.14-alpine@sha256:{NEW_A}" in text
    assert OLD_A not in text
    assert evidence["source_commit"] == COMMIT
    assert evidence["changed_paths"] == ["Dockerfile"]
    assert len(evidence["replacements"]) == 1
    assert len(evidence["evidence_digest"]) == 64


def test_apply_updates_every_occurrence_of_grouped_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": (
                f"FROM python:3.14@sha256:{OLD_A} AS build\n"
                f"FROM python:3.14@sha256:{OLD_A} AS runtime\n"
            )
        },
    )
    inventory = refresh.build_inventory()
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14", NEW_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    text = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert text.count(NEW_A) == 2
    assert len(evidence["replacements"]) == 2


def test_apply_preserves_raw_variable_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "frontend/Dockerfile": (
                "ARG NODE_VERSION=24\n"
                f"FROM node:${{NODE_VERSION}}-alpine@sha256:{OLD_A}\n"
            )
        },
    )
    inventory = refresh.build_inventory()
    plan = refresh.build_plan(
        inventory,
        resolution("node:24-alpine", NEW_A),
        source_commit=COMMIT,
    )
    refresh.apply_plan(plan, expected_source_commit=COMMIT)
    text = (tmp_path / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert f"node:${{NODE_VERSION}}-alpine@sha256:{NEW_A}" in text


def test_apply_rejects_wrong_checkout_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    with pytest.raises(refresh.DigestRefreshStateError):
        refresh.apply_plan(plan, expected_source_commit="2" * 40)
    assert OLD_A in (tmp_path / "Dockerfile").read_text(encoding="utf-8")


def test_apply_rejects_source_file_changed_after_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    with (tmp_path / "Dockerfile").open("a", encoding="utf-8") as handle:
        handle.write("# changed\n")
    with pytest.raises(refresh.DigestRefreshStateError, match="changed after inventory"):
        refresh.apply_plan(plan, expected_source_commit=COMMIT)


def test_apply_empty_change_plan_is_noop_with_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", OLD_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    assert evidence["changed_paths"] == []
    assert evidence["replacements"] == []
    assert evidence["postimages"] == {}


def test_verify_evidence_accepts_current_postimages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    refresh.verify_evidence(plan, evidence)


def test_verify_evidence_detects_post_apply_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    (tmp_path / "Dockerfile").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(refresh.DigestRefreshStateError, match="postimage"):
        refresh.verify_evidence(plan, evidence)


def _rehash_evidence(evidence: dict[str, object]) -> None:
    unsigned = dict(evidence)
    unsigned.pop("evidence_digest", None)
    evidence["evidence_digest"] = refresh._json_digest(unsigned)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("resolver", "different-resolver"),
        ("changed_paths", []),
        ("preimages", {}),
        ("replacements", []),
        ("postimages", {}),
    ],
)
def test_verify_evidence_rejects_semantic_tamper_even_when_rehashed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: object,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    evidence[field] = replacement
    _rehash_evidence(evidence)
    with pytest.raises(
        (refresh.DigestRefreshPolicyError, refresh.DigestRefreshStateError)
    ):
        refresh.verify_evidence(plan, evidence)


def test_verify_evidence_rejects_rehashed_replacement_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    replacement = dict(evidence["replacements"][0])
    replacement["new_digest"] = "9" * 64
    evidence["replacements"] = [replacement]
    _rehash_evidence(evidence)
    with pytest.raises(refresh.DigestRefreshStateError, match="replacements"):
        refresh.verify_evidence(plan, evidence)


def test_verify_evidence_detects_document_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    evidence["resolver"] = "attacker"
    with pytest.raises(refresh.DigestRefreshPolicyError, match="evidence digest"):
        refresh.verify_evidence(plan, evidence)


@pytest.mark.parametrize("bad_size", [True, 1.5, "1"])
def test_self_hashed_plan_rejects_coerced_source_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_size: object,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    plan["sources"][0]["size"] = bad_size
    unsigned = dict(plan)
    unsigned.pop("plan_digest", None)
    plan["plan_digest"] = refresh._json_digest(unsigned)
    with pytest.raises(refresh.DigestRefreshPolicyError, match="source"):
        refresh.apply_plan(plan, expected_source_commit=COMMIT)


def test_self_hashed_plan_rejects_occurrence_outside_source_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    plan["entries"][0]["occurrences"][0]["path"] = "other/Dockerfile"
    unsigned = dict(plan)
    unsigned.pop("plan_digest", None)
    plan["plan_digest"] = refresh._json_digest(unsigned)
    with pytest.raises(refresh.DigestRefreshPolicyError, match="outside"):
        refresh.apply_plan(plan, expected_source_commit=COMMIT)


def test_self_hashed_plan_rejects_duplicate_occurrence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    occurrence = dict(plan["entries"][0]["occurrences"][0])
    plan["entries"][0]["occurrences"].append(occurrence)
    unsigned = dict(plan)
    unsigned.pop("plan_digest", None)
    plan["plan_digest"] = refresh._json_digest(unsigned)
    with pytest.raises(refresh.DigestRefreshPolicyError, match="duplicate"):
        refresh.apply_plan(plan, expected_source_commit=COMMIT)


def test_plan_tamper_is_rejected_before_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14-alpine", NEW_A),
        source_commit=COMMIT,
    )
    plan["resolver"] = "tampered"
    with pytest.raises(refresh.DigestRefreshPolicyError, match="plan digest"):
        refresh.apply_plan(plan, expected_source_commit=COMMIT)


def test_source_path_escape_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {"Dockerfile": f"FROM python:3.14@sha256:{OLD_A}\n"},
    )
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh._safe_source_path("../outside")


def test_inventory_requires_at_least_one_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(tmp_path, monkeypatch, {"Dockerfile": "FROM scratch\n"})
    with pytest.raises(refresh.DigestRefreshPolicyError, match="no digest"):
        refresh.build_inventory()


def test_json_writer_uses_stable_sorted_encoding(tmp_path: Path) -> None:
    output = tmp_path / "value.json"
    refresh._write_json(output, {"z": 1, "a": 2})
    assert output.read_text(encoding="utf-8") == '{\n  "a": 2,\n  "z": 1\n}\n'


def test_json_loader_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh._load_json(path)


def test_json_loader_rejects_symlink_input(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"schema_version": 1}\n', encoding="utf-8")
    link = tmp_path / "input.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(refresh.DigestRefreshPolicyError, match="non-symlink"):
        refresh._load_json(link)


def test_json_loader_rejects_directory_input(tmp_path: Path) -> None:
    with pytest.raises(refresh.DigestRefreshPolicyError, match="regular"):
        refresh._load_json(tmp_path)

def test_json_loader_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(refresh.DigestRefreshPolicyError):
        refresh._load_json(path)


def test_cli_inventory_and_queries_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {"Dockerfile": f"FROM python:3.14@sha256:{OLD_A}\n"},
    )
    inventory = tmp_path / "inventory.json"
    assert refresh.main(["inventory", "--output", str(inventory)]) == 0
    assert refresh.main(["queries", "--inventory", str(inventory)]) == 0
    assert "python:3.14" in capsys.readouterr().out


def test_cli_full_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {"Dockerfile": f"FROM python:3.14@sha256:{OLD_A}\n"},
    )
    inventory = tmp_path / "inventory.json"
    tsv = tmp_path / "resolved.tsv"
    resolutions = tmp_path / "resolutions.json"
    plan = tmp_path / "plan.json"
    evidence = tmp_path / "evidence.json"

    assert refresh.main(["inventory", "--output", str(inventory)]) == 0
    tsv.write_text(f"python:3.14\tsha256:{NEW_A}\n", encoding="utf-8")
    assert refresh.main([
        "resolutions", "--input", str(tsv), "--output", str(resolutions),
        "--resolver", "test",
    ]) == 0
    assert refresh.main([
        "plan", "--inventory", str(inventory), "--resolutions", str(resolutions),
        "--source-commit", COMMIT, "--output", str(plan),
    ]) == 0
    assert refresh.main([
        "apply", "--plan", str(plan), "--source-commit", COMMIT,
        "--evidence", str(evidence),
    ]) == 0
    assert refresh.main([
        "verify", "--plan", str(plan), "--evidence", str(evidence),
    ]) == 0
    assert NEW_A in (tmp_path / "Dockerfile").read_text(encoding="utf-8")


def test_cli_returns_failure_for_policy_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(tmp_path, monkeypatch, {"Dockerfile": "FROM scratch\n"})
    assert refresh.main([
        "inventory", "--output", str(tmp_path / "inventory.json"),
    ]) == 1


def test_full_inventory_handles_multiple_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": f"FROM python:3.14@sha256:{OLD_A}\n",
            "frontend/Dockerfile": (
                "ARG NODE_VERSION=24\n"
                f"FROM node:${{NODE_VERSION}}-alpine@sha256:{OLD_B}\n"
            ),
            "docker-compose.yml": (
                "services:\n  mongo:\n"
                f"    image: mongo:7@sha256:{OLD_A}\n"
            ),
        },
    )
    assert refresh.inventory_queries(refresh.build_inventory()) == (
        "mongo:7",
        "node:24-alpine",
        "python:3.14",
    )


def test_multi_reference_plan_applies_all_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": (
                f"FROM python:3.14@sha256:{OLD_A}\n"
                f"FROM alpine:3.22@sha256:{OLD_B}\n"
            )
        },
    )
    inventory = refresh.build_inventory()
    resolved_payload: dict[str, object] = {
        "schema_version": 1,
        "resolver": "test",
        "resolved": {"alpine:3.22": NEW_B, "python:3.14": NEW_A},
    }
    resolved_payload["resolution_digest"] = refresh._json_digest(resolved_payload)
    plan = refresh.build_plan(inventory, resolved_payload, source_commit=COMMIT)
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    text = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert NEW_A in text and NEW_B in text
    assert len(evidence["replacements"]) == 2


def test_evidence_preimages_include_all_inventory_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {
            "Dockerfile": f"FROM python:3.14@sha256:{OLD_A}\n",
            "backend/Dockerfile": f"FROM python:3.14@sha256:{OLD_A}\n",
        },
    )
    inventory = refresh.build_inventory()
    plan = refresh.build_plan(
        inventory,
        resolution("python:3.14", NEW_A),
        source_commit=COMMIT,
    )
    evidence = refresh.apply_plan(plan, expected_source_commit=COMMIT)
    assert set(evidence["preimages"]) == {"Dockerfile", "backend/Dockerfile"}
    assert set(evidence["postimages"]) == {"Dockerfile", "backend/Dockerfile"}


def test_resolution_tsv_rejects_symlink_input(tmp_path: Path) -> None:
    target = tmp_path / "resolved-target.tsv"
    target.write_text(f"python:3.14\t{NEW_A}\n", encoding="utf-8")
    link = tmp_path / "resolved.tsv"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(refresh.DigestRefreshPolicyError, match="non-symlink"):
        refresh.resolutions_from_tsv(link, resolver="test")


def test_resolution_tsv_rejects_directory_input(tmp_path: Path) -> None:
    with pytest.raises(refresh.DigestRefreshPolicyError, match="regular"):
        refresh.resolutions_from_tsv(tmp_path, resolver="test")


def test_resolution_tsv_rejects_oversized_file_before_parse(tmp_path: Path) -> None:
    path = tmp_path / "resolved.tsv"
    with path.open("wb") as handle:
        handle.seek(refresh.MAX_INPUT_BYTES)
        handle.write(b"x")
    with pytest.raises(refresh.DigestRefreshPolicyError, match="byte bound"):
        refresh.resolutions_from_tsv(path, resolver="test")

def test_resolutions_digest_binds_resolver_identity(tmp_path: Path) -> None:
    path = tmp_path / "resolved.tsv"
    path.write_text(f"python:3.14\t{NEW_A}\n", encoding="utf-8")
    one = refresh.resolutions_from_tsv(path, resolver="one")
    two = refresh.resolutions_from_tsv(path, resolver="two")
    assert one["resolution_digest"] != two["resolution_digest"]


def test_plan_digest_binds_source_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = one_pin_inventory(tmp_path, monkeypatch)
    resolved = resolution("python:3.14-alpine", NEW_A)
    one = refresh.build_plan(inventory, resolved, source_commit="1" * 40)
    two = refresh.build_plan(inventory, resolved, source_commit="2" * 40)
    assert one["plan_digest"] != two["plan_digest"]


def test_uppercase_digest_is_not_managed_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {"Dockerfile": f"FROM python:3.14@sha256:{OLD_A.upper()}\n"},
    )
    with pytest.raises(
        refresh.DigestRefreshPolicyError,
        match="invalid digest-pinned container reference",
    ):
        refresh.build_inventory()


def test_inventory_line_numbers_bind_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_repo(
        tmp_path,
        monkeypatch,
        {"Dockerfile": "# one\n# two\n" + f"FROM python:3.14@sha256:{OLD_A}\n"},
    )
    assert refresh.build_inventory()["pins"][0]["occurrences"][0]["line"] == 3


def test_refresh_errors_do_not_echo_secret_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "SUPER_SECRET"
    configure_repo(
        tmp_path,
        monkeypatch,
        {"Dockerfile": f"FROM user:{secret}@registry/image:1@sha256:{OLD_A}\n"},
    )
    with pytest.raises(refresh.DigestRefreshPolicyError) as caught:
        refresh.build_inventory()
    assert secret not in str(caught.value)
