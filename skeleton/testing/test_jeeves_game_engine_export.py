from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace

import pytest

from skeleton.forge.lafs import Lafs
from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_export import (
    PACKAGE_FILE_PREFIX,
    PACKAGE_MANIFEST_PATH,
    PackageFile,
    archive_project_package,
    build_project_package,
    inspect_project_archive,
    materialise_project_package,
    publish_project_package,
    restore_package_tree,
    verify_project_package,
)
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_project import (
    ExecutableGameProjectLab,
)


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.PONG,
        EngineEra.EARLY_3D,
        EngineEra.HD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_canonical_project_package_is_deterministic_and_verified(
    era: EngineEra,
) -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        era,
        "action_adventure",
    )

    first = build_project_package(
        project,
        lab=lab,
    )
    second = build_project_package(
        project,
        lab=lab,
    )

    assert first == second
    assert first.tree_digest == project.tree.digest
    assert first.file_count == len(project.tree.files)
    assert first.total_bytes == sum(
        len(
            content.encode(
                "utf-8"
            )
        )
        for content
        in project.tree.files.values()
    )
    assert len(first.package_digest) == 64
    verification = verify_project_package(
        first
    )
    assert verification.passed
    assert verification.failures == ()


def test_package_manifest_attests_every_file_in_sorted_order() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.MODERN
    )
    package = build_project_package(
        project
    )
    manifest = package.manifest()

    paths = [
        item["path"]
        for item
        in manifest["files"]
    ]

    assert paths == sorted(paths)
    assert paths == sorted(
        project.tree.files
    )
    assert manifest["file_count"] == len(paths)
    assert manifest["total_bytes"] == package.total_bytes
    assert manifest["tree_digest"] == project.tree.digest
    assert (
        manifest["package_digest"]
        == package.package_digest
    )
    assert (
        manifest["executable_sandbox_code"]
        is False
    )


def test_package_restore_recovers_exact_virtual_tree_identity() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.NEXT
    )
    package = build_project_package(
        project
    )

    restored = restore_package_tree(
        package
    )

    assert restored.digest == project.tree.digest
    assert dict(restored.files) == dict(project.tree.files)


def test_failing_project_is_not_exportable_by_default() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.HD
    )
    path = (
        "audio/compiled/manifest.json"
    )
    broken = project.apply(
        (
            SandboxPatch(
                path,
                "{}",
                project.tree.file_digest(
                    path
                ),
            ),
        )
    )

    report = lab.evaluate(
        broken
    )
    assert not report.passed

    with pytest.raises(
        GameEngineLabError,
        match="cannot package project",
    ):
        build_project_package(
            broken,
            lab=lab,
        )


def test_package_digest_tamper_is_detected() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.EIGHT_BIT
    )
    package = build_project_package(
        project
    )
    forged = replace(
        package,
        package_digest="0" * 64,
    )

    verification = verify_project_package(
        forged
    )

    assert not verification.passed
    assert not verification.package_digest_ok
    assert (
        "package_digest"
        in verification.failures
    )


def test_package_content_tamper_breaks_tree_and_package_identity() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.FIXED_3D
    )
    package = build_project_package(
        project
    )
    first = package.files[0]
    content = first.content + "\n# tamper\n"
    forged_file = PackageFile(
        first.path,
        len(
            content.encode(
                "utf-8"
            )
        ),
        __import__("hashlib").sha256(
            content.encode(
                "utf-8"
            )
        ).hexdigest(),
        content,
    )
    forged = replace(
        package,
        files=(
            forged_file,
            *package.files[1:],
        ),
    )

    verification = verify_project_package(
        forged
    )

    assert not verification.passed
    assert verification.file_digests_ok
    assert not verification.tree_digest_ok
    assert not verification.package_digest_ok


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.PONG,
        EngineEra.SHADER,
        EngineEra.NEXT,
    ],
)
def test_portable_zip_is_byte_for_byte_reproducible(
    era: EngineEra,
) -> None:
    project = ExecutableGameProjectLab().create(
        era
    )
    package = build_project_package(
        project
    )

    first = archive_project_package(
        package
    )
    second = archive_project_package(
        package
    )

    assert first == second
    assert first.data == second.data
    assert len(first.digest) == 64
    assert first.file_count == package.file_count
    assert (
        first.uncompressed_bytes
        == package.total_bytes
    )


def test_portable_zip_manifest_and_inventory_round_trip() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.MODERN
    )
    package = build_project_package(
        project
    )
    archive = archive_project_package(
        package
    )

    inspection = inspect_project_archive(
        archive.data
    )

    assert (
        inspection["archive_digest"]
        == archive.digest
    )
    assert (
        inspection["package_digest"]
        == package.package_digest
    )
    assert (
        inspection["tree_digest"]
        == project.tree.digest
    )
    assert (
        inspection["file_count"]
        == package.file_count
    )
    assert (
        inspection["engine_era"]
        == EngineEra.MODERN.value
    )


def test_archive_tamper_is_rejected() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.EIGHT_BIT
    )
    archive = archive_project_package(
        build_project_package(
            project
        )
    )
    data = bytearray(
        archive.data
    )
    data[
        len(data) // 2
    ] ^= 0x01

    with pytest.raises(
        GameEngineLabError,
    ):
        inspect_project_archive(
            bytes(data)
        )


def test_structured_json_materialisation_reuses_forge_registry() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.PONG
    )
    package = build_project_package(
        project
    )

    data = materialise_project_package(
        package,
        materialiser="json",
    )
    payload = json.loads(
        data
    )

    assert (
        payload["package"]["package_digest"]
        == package.package_digest
    )
    assert (
        set(payload["files"])
        == set(project.tree.files)
    )
    assert (
        payload["pack"]["tree_digest"]
        == project.tree.digest
    )


def test_unknown_structured_materialiser_fails_closed() -> None:
    package = build_project_package(
        ExecutableGameProjectLab().create(
            EngineEra.PONG
        )
    )

    with pytest.raises(
        GameEngineLabError,
        match="unknown project package materialiser",
    ):
        materialise_project_package(
            package,
            materialiser="does-not-exist",
        )


def test_lafs_publication_reassembles_exact_archive_bytes() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.MODERN
    )
    package = build_project_package(
        project
    )
    archive = archive_project_package(
        package
    )
    lafs = Lafs()

    publication = publish_project_package(
        package,
        lafs,
        name="tests/modern-project.zip",
        chunk_bytes=256,
    )

    assert publication.name == "tests/modern-project.zip"
    assert publication.package_digest == package.package_digest
    assert publication.archive_digest == archive.digest
    assert len(publication.chunk_digests) > 1
    assert (
        lafs.read_manifest(
            publication.name
        )
        == archive.data
    )
    assert (
        publication.manifest.total_bytes
        == len(archive.data)
    )


def test_default_lafs_name_is_content_addressed() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.HD
    )
    package = build_project_package(
        project
    )
    publication = publish_project_package(
        package,
        Lafs(),
    )

    assert package.package_digest in publication.name
    assert publication.name.endswith(".zip")


@pytest.mark.parametrize(
    "chunk_bytes",
    [
        0,
        -1,
        2 * 1024 * 1024,
    ],
)
def test_lafs_publication_rejects_invalid_chunk_size(
    chunk_bytes: int,
) -> None:
    package = build_project_package(
        ExecutableGameProjectLab().create(
            EngineEra.PONG
        )
    )

    with pytest.raises(
        GameEngineLabError,
        match="chunk size",
    ):
        publish_project_package(
            package,
            Lafs(),
            chunk_bytes=chunk_bytes,
        )


def test_jeeves_owns_package_archive_materialise_and_publish_workflow() -> None:
    jeeves = Jeeves()
    project = jeeves.build_game_project(
        EngineEra.MODERN,
        gameplay_dialect="immersive_sim",
    )

    package = jeeves.package_game_project(
        project
    )
    archive = jeeves.archive_game_project(
        project
    )
    structured = jeeves.materialise_game_project(
        project,
        materialiser="json",
    )
    lafs = Lafs()
    publication = jeeves.publish_game_project(
        project,
        lafs,
        name="jeeves/modern.zip",
        chunk_bytes=512,
    )

    assert verify_project_package(
        package
    ).passed
    assert (
        inspect_project_archive(
            archive.data
        )["package_digest"]
        == package.package_digest
    )
    assert (
        json.loads(
            structured
        )["package"]["package_digest"]
        == package.package_digest
    )
    assert (
        lafs.read_manifest(
            publication.name
        )
        == archive.data
    )


def test_portable_archive_uses_reserved_manifest_and_project_prefixes() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.PONG
    )
    package = build_project_package(
        project
    )

    assert PACKAGE_MANIFEST_PATH.startswith(
        "META-INF/"
    )
    assert PACKAGE_FILE_PREFIX == "project/"
    assert all(
        not item.path.startswith(
            "META-INF/"
        )
        for item in package.files
    )



def test_archive_inspection_rejects_compressed_reencoding() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.PONG
    )
    archive = archive_project_package(
        build_project_package(
            project
        )
    )
    source = zipfile.ZipFile(
        io.BytesIO(
            archive.data
        ),
        "r",
    )
    output = io.BytesIO()
    with source, zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as rewritten:
        for name in source.namelist():
            rewritten.writestr(
                name,
                source.read(
                    name
                ),
                compress_type=zipfile.ZIP_DEFLATED,
            )

    with pytest.raises(
        GameEngineLabError,
        match="noncanonical ZIP encoding",
    ):
        inspect_project_archive(
            output.getvalue()
        )


def test_archive_inspection_rejects_forged_package_digest() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.EIGHT_BIT
    )
    archive = archive_project_package(
        build_project_package(
            project
        )
    )
    source = zipfile.ZipFile(
        io.BytesIO(
            archive.data
        ),
        "r",
    )
    output = io.BytesIO()
    with source, zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as rewritten:
        for name in source.namelist():
            payload = source.read(
                name
            )
            if (
                name
                == PACKAGE_MANIFEST_PATH
            ):
                manifest = json.loads(
                    payload
                )
                manifest[
                    "package_digest"
                ] = "0" * 64
                payload = (
                    json.dumps(
                        manifest,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode(
                    "utf-8"
                )
            info = zipfile.ZipInfo(
                name,
                date_time=(
                    1980,
                    1,
                    1,
                    0,
                    0,
                    0,
                ),
            )
            info.compress_type = (
                zipfile.ZIP_STORED
            )
            info.create_system = 3
            info.external_attr = (
                0o100644 << 16
            )
            rewritten.writestr(
                info,
                payload,
            )

    with pytest.raises(
        GameEngineLabError,
        match="package digest mismatch",
    ):
        inspect_project_archive(
            output.getvalue()
        )


def test_archive_inspection_rejects_noncanonical_file_order() -> None:
    project = ExecutableGameProjectLab().create(
        EngineEra.PONG
    )
    archive = archive_project_package(
        build_project_package(
            project
        )
    )
    source = zipfile.ZipFile(
        io.BytesIO(
            archive.data
        ),
        "r",
    )
    names = source.namelist()
    assert len(names) > 2
    output = io.BytesIO()
    with source, zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as rewritten:
        reordered = (
            names[:1]
            + list(
                reversed(
                    names[1:]
                )
            )
        )
        for name in reordered:
            info = zipfile.ZipInfo(
                name,
                date_time=(
                    1980,
                    1,
                    1,
                    0,
                    0,
                    0,
                ),
            )
            info.compress_type = (
                zipfile.ZIP_STORED
            )
            info.create_system = 3
            info.external_attr = (
                0o100644 << 16
            )
            rewritten.writestr(
                info,
                source.read(
                    name
                ),
            )

    with pytest.raises(
        GameEngineLabError,
        match="ordering is noncanonical",
    ):
        inspect_project_archive(
            output.getvalue()
        )
