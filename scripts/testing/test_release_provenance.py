from __future__ import annotations

import argparse
import gzip
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release_provenance.py"
SPEC = importlib.util.spec_from_file_location("release_provenance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
release_provenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_provenance)

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _write_sdist(
    path: Path,
    *,
    gzip_mtime: int,
    member_mtime: int,
    uid: int,
    gid: int,
    uname: str,
    gname: str,
) -> None:
    payload = b"Metadata-Version: 2.4\nName: skeleton\nVersion: 16.0.0\n"
    with path.open("wb") as raw_output:
        with gzip.GzipFile(
            filename="source-name-that-must-not-survive.tar",
            mode="wb",
            fileobj=raw_output,
            mtime=gzip_mtime,
        ) as gzip_output:
            with tarfile.open(fileobj=gzip_output, mode="w", format=tarfile.PAX_FORMAT) as archive:
                directory = tarfile.TarInfo("skeleton-16.0.0")
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o775
                directory.mtime = member_mtime
                directory.uid = uid
                directory.gid = gid
                directory.uname = uname
                directory.gname = gname
                archive.addfile(directory)

                metadata = tarfile.TarInfo("skeleton-16.0.0/PKG-INFO")
                metadata.size = len(payload)
                metadata.mode = 0o664
                metadata.mtime = member_mtime
                metadata.uid = uid
                metadata.gid = gid
                metadata.uname = uname
                metadata.gname = gname
                archive.addfile(metadata, io.BytesIO(payload))


def test_normalize_sdist_removes_archive_metadata_nondeterminism(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_sdist(
        first,
        gzip_mtime=1_700_000_001,
        member_mtime=1_700_000_011,
        uid=1000,
        gid=1000,
        uname="runner-a",
        gname="runner-a",
    )
    _write_sdist(
        second,
        gzip_mtime=1_700_000_099,
        member_mtime=1_700_000_199,
        uid=2000,
        gid=3000,
        uname="runner-b",
        gname="runner-c",
    )
    assert first.read_bytes() != second.read_bytes()

    epoch = 1_699_999_999
    for path in (first, second):
        args = argparse.Namespace(path=str(path), source_date_epoch=str(epoch))
        assert release_provenance.normalize_sdist(args) == 0

    assert first.read_bytes() == second.read_bytes()
    assert int.from_bytes(first.read_bytes()[4:8], "little") == epoch
    with tarfile.open(first, mode="r:gz") as archive:
        members = archive.getmembers()
    assert [member.name for member in members] == [
        "skeleton-16.0.0",
        "skeleton-16.0.0/PKG-INFO",
    ]
    assert all(member.mtime == epoch for member in members)
    assert all(member.uid == 0 and member.gid == 0 for member in members)
    assert all(member.uname == "" and member.gname == "" for member in members)
    assert members[0].mode == 0o755
    assert members[1].mode == 0o644


def test_emit_provenance_is_deterministic_and_hashes_release_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tmp_path / "dist"
    artifacts.mkdir()
    wheel = artifacts / "skeleton-16.0.0-py3-none-any.whl"
    wheel.write_bytes(b"deterministic-wheel")
    sbom = artifacts / "release-sbom.cdx.json"
    sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    build_lock = tmp_path / "requirements-build.txt"
    build_lock.write_text("build==1.3.0\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    first = tmp_path / "first.json"
    first_sums = tmp_path / "first.sha256"
    args = argparse.Namespace(
        artifacts_dir=str(artifacts),
        output=str(first),
        checksums=str(first_sums),
        source_commit=COMMIT,
        source_date_epoch="1700000000",
        input=[build_lock.name],
        sbom_ref=[str(sbom)],
    )
    assert release_provenance.emit_provenance(args) == 0

    second = tmp_path / "second.json"
    second_sums = tmp_path / "second.sha256"
    args.output = str(second)
    args.checksums = str(second_sums)
    assert release_provenance.emit_provenance(args) == 0

    assert first.read_bytes() == second.read_bytes()
    assert first_sums.read_bytes() == second_sums.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["source"] == {"commit": COMMIT, "source_date_epoch": 1700000000}
    assert [item["name"] for item in payload["artifacts"]] == [
        "release-sbom.cdx.json",
        "skeleton-16.0.0-py3-none-any.whl",
    ]
    assert payload["inputs"][0]["name"] == "requirements-build.txt"
    assert payload["inputs"][0]["sha256"] == release_provenance._sha256(build_lock)
    assert payload["sbom_refs"][0]["name"] == "release-sbom.cdx.json"


def test_compare_provenance_fails_when_artifact_digest_changes(tmp_path: Path) -> None:
    base = {
        "source": {"commit": COMMIT, "source_date_epoch": 1},
        "toolchain": {"python": "3.11.11"},
        "inputs": [],
        "sbom_refs": [],
        "artifacts": [{"name": "x.whl", "sha256": "a", "size": 1}],
    }
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(base), encoding="utf-8")
    changed = dict(base)
    changed["artifacts"] = [{"name": "x.whl", "sha256": "b", "size": 1}]
    right.write_text(json.dumps(changed), encoding="utf-8")

    args = argparse.Namespace(left=str(left), right=str(right))
    assert release_provenance.compare_provenance(args) == 1


def test_sbom_is_deterministic_and_tracks_declared_runtime_requirements(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "example"
version = "1.2.3"
dependencies = ["uvicorn[standard]>=0.23.0", "fastapi>=0.100.0"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "sbom.json"
    args = argparse.Namespace(pyproject=str(pyproject), output=str(output), source_commit=COMMIT)

    assert release_provenance.write_sbom(args) == 0
    first = output.read_bytes()
    assert release_provenance.write_sbom(args) == 0
    assert output.read_bytes() == first

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bomFormat"] == "CycloneDX"
    assert payload["specVersion"] == "1.6"
    assert [component["name"] for component in payload["components"]] == ["fastapi", "uvicorn"]


def test_invalid_source_identity_fails_closed() -> None:
    with pytest.raises(ValueError):
        release_provenance._validate_commit("main")
    with pytest.raises(ValueError):
        release_provenance._validate_epoch("-1")


def test_emit_provenance_rejects_absolute_input_names(tmp_path: Path) -> None:
    artifacts = tmp_path / "dist"
    artifacts.mkdir()
    (artifacts / "skeleton.whl").write_bytes(b"artifact")
    build_lock = tmp_path / "requirements-build.txt"
    build_lock.write_text("build==1.3.0\n", encoding="utf-8")

    args = argparse.Namespace(
        artifacts_dir=str(artifacts),
        output=str(tmp_path / "provenance.json"),
        checksums=str(tmp_path / "SHA256SUMS"),
        source_commit=COMMIT,
        source_date_epoch="1700000000",
        input=[str(build_lock)],
        sbom_ref=[],
    )
    with pytest.raises(ValueError, match="repository-relative POSIX"):
        release_provenance.emit_provenance(args)

def test_schema_version_1_callers_are_unchanged(tmp_path: Path) -> None:
    assert release_provenance.SCHEMA_VERSION == 1
    artifacts = tmp_path / "dist"
    artifacts.mkdir()
    wheel = artifacts / "skeleton-16.0.0-py3-none-any.whl"
    wheel.write_bytes(b"deterministic-wheel")
    sbom = artifacts / "release-sbom.cdx.json"
    sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    output = tmp_path / "provenance.json"
    checksums = tmp_path / "SHA256SUMS"
    args = argparse.Namespace(
        artifacts_dir=str(artifacts),
        output=str(output),
        checksums=str(checksums),
        source_commit=COMMIT,
        source_date_epoch="1700000000",
        input=[],
        sbom_ref=[str(sbom)],
    )
    assert release_provenance.emit_provenance(args) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert "schema_id" not in payload
    assert payload["source"]["commit"] == COMMIT


def test_evidence_loader_does_not_require_preexisting_pythonpath() -> None:
    """Reproducible Release pytest runs from the parent of the checkout."""

    root = str(REPO_ROOT.resolve())
    original_path = list(sys.path)
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "pydantic"
        or name.startswith("pydantic.")
        or name == "skeleton"
        or name.startswith("skeleton.")
    }
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry not in {"", ".", root}
        and Path(entry).resolve() != REPO_ROOT.resolve()
    ]
    for name in list(original_modules):
        sys.modules.pop(name, None)
    try:
        module = release_provenance._load_release_evidence()
        assert module.SCHEMA_ID == "skeleton.release.evidence"
        assert "pydantic" not in sys.modules
        assert "skeleton.config.settings" not in sys.modules
    finally:
        sys.path[:] = original_path
        sys.modules.update(original_modules)


def test_evidence_adapter_gates_missing_tests_and_binds_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tmp_path / "dist"
    artifacts.mkdir()
    wheel = artifacts / "skeleton-16.0.0-py3-none-any.whl"
    wheel.write_bytes(b"deterministic-wheel")
    sbom = artifacts / "release-sbom.cdx.json"
    sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    build_lock = tmp_path / "requirements-build.txt"
    build_lock.write_text("build==1.3.0\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    provenance_path = tmp_path / "provenance.json"
    checksums = tmp_path / "SHA256SUMS"
    emit_args = argparse.Namespace(
        artifacts_dir=str(artifacts),
        output=str(provenance_path),
        checksums=str(checksums),
        source_commit=COMMIT,
        source_date_epoch="1700000000",
        input=[build_lock.name],
        sbom_ref=[str(sbom)],
    )
    assert release_provenance.emit_provenance(emit_args) == 0

    evidence_path = tmp_path / "evidence.json"
    missing = argparse.Namespace(
        provenance=str(provenance_path),
        output=str(evidence_path),
        source_commit=COMMIT,
        test_evidence=[],
        eval_evidence=[],
        asset_provenance=None,
        observed=[],
        gate=True,
    )
    assert release_provenance.emit_release_evidence(missing) == 1

    tests = tmp_path / "tests.json"
    tests.write_text(
        json.dumps(
            [
                {
                    "evidence_id": "unit",
                    "name": "unit.xml",
                    "sha256": "a" * 64,
                    "result": "pass",
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    evals = tmp_path / "evals.json"
    evals.write_text(
        json.dumps(
            [
                {
                    "evidence_id": "eval",
                    "name": "eval.json",
                    "sha256": "b" * 64,
                    "result": "pass",
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    observed = [
        f"skeleton-16.0.0-py3-none-any.whl={wheel}",
        f"release-sbom.cdx.json={sbom}",
    ]
    ready = argparse.Namespace(
        provenance=str(provenance_path),
        output=str(evidence_path),
        source_commit=COMMIT,
        test_evidence=[str(tests)],
        eval_evidence=[str(evals)],
        asset_provenance=None,
        observed=observed,
        gate=True,
    )
    assert release_provenance.emit_release_evidence(ready) == 0
    document = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert document["schema_id"] == "skeleton.release.evidence"
    assert document["provenance"]["schema_version"] == 1

    gate_args = argparse.Namespace(
        evidence=str(evidence_path),
        source_commit=COMMIT,
        observed=observed,
    )
    assert release_provenance.gate_release_evidence(gate_args) == 0
    gate_args.source_commit = "ffffffffffffffffffffffffffffffffffffffff"
    assert release_provenance.gate_release_evidence(gate_args) == 1


def test_reproducible_release_workflow_gates_bound_release_evidence() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "reproducible-release.yml"
    ).read_text(encoding="utf-8")

    assert '"skeleton/release/evidence.py"' in workflow
    assert '"pytest-asyncio==1.4.0"' in workflow
    assert '"skeleton/testing/test_release_evidence.py"' in workflow
    assert "--junitxml=source-a/release-meta/release-tests.xml" in workflow
    assert "source-a/skeleton/testing/test_ai_golden_journey.py" in workflow
    assert "--junitxml=source-a/release-meta/ai-golden-tests.xml" in workflow
    assert "ai-golden-engine-tool-approval" in workflow
    assert "ai-golden-tests" in workflow
    assert "ai-golden-eval.json" in workflow
    assert "reproducibility-eval.json" in workflow
    assert "scripts/release_provenance.py evidence" in workflow
    assert "--test-evidence release-meta/test-evidence.json" in workflow
    assert "--eval-evidence release-meta/eval-evidence.json" in workflow
    assert "--output release-meta/release-evidence.json" in workflow
    assert "--gate" in workflow
    assert "scripts/release_provenance.py gate" in workflow
    assert 'find dist -maxdepth 1 -type f' in workflow
    assert 'source-a/release-meta/' in workflow
