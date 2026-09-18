"""Deterministic export and publication for Jeeves game-engine projects.

A winning GameProjectSandbox is an in-memory authority. This module turns that
authority into portable bytes without introducing a second filesystem or store:

* every sandbox file is re-attested by SHA-256;
* package metadata is deterministic and quality-gated;
* ZIP output uses fixed metadata, sorted paths and stored entries so identical
  projects produce identical bytes across runs;
* structured exports reuse Forge MaterialisationRegistry;
* durable publication reuses Forge LAFS and its existing SHA-256 chunk store.

The export boundary never mutates the project and never executes sandbox code.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Iterable

from skeleton.forge.lafs import (
    CHUNK_MAX_BYTES,
    Lafs,
    Manifest,
)
from skeleton.forge.materialisers import (
    MaterialisationRegistry,
)
from skeleton.kernel.errors import (
    MaterialisationError,
)

from .game_engine_lab import (
    GameEngineLabError,
    VirtualFileTree,
)
from .game_engine_project import (
    ExecutableGameProjectLab,
    GameProjectSandbox,
    ProjectQualityReport,
)

PACKAGE_SCHEMA_VERSION = 1
PACKAGE_MANIFEST_PATH = (
    "META-INF/jeeves-package.json"
)
PACKAGE_FILE_PREFIX = "project/"
MAX_PACKAGE_FILES = 4096
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 96 * 1024 * 1024


def _canonical(
    value: object,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _sha_bytes(
    value: bytes,
) -> str:
    return hashlib.sha256(
        value
    ).hexdigest()


def _sha_text(
    value: str,
) -> str:
    return _sha_bytes(
        value.encode(
            "utf-8"
        )
    )


def _quality_document(
    report: ProjectQualityReport,
) -> dict[str, object]:
    return {
        "passed":
            report.passed,
        "score":
            report.score,
        "runtime_score":
            report.runtime_score,
        "asset_score":
            report.asset_score,
        "script_score":
            report.script_score,
        "physics_score":
            report.physics_score,
        "audio_score":
            report.audio_score,
        "animation_score":
            report.animation_score,
        "failed":
            list(
                report.failed
            ),
    }


@dataclass(
    frozen=True,
    slots=True,
)
class PackageFile:
    path: str
    size: int
    digest: str
    content: str

    def __post_init__(
        self,
    ) -> None:
        if (
            not self.path
            or self.path.startswith("/")
            or ".."
            in self.path.split("/")
        ):
            raise GameEngineLabError(
                "package file path is unsafe"
            )
        encoded = self.content.encode(
            "utf-8"
        )
        if self.size != len(
            encoded
        ):
            raise GameEngineLabError(
                "package file size mismatch"
            )
        if (
            self.digest
            != _sha_bytes(
                encoded
            )
        ):
            raise GameEngineLabError(
                "package file digest mismatch"
            )

    def manifest_entry(
        self,
    ) -> dict[str, object]:
        return {
            "path":
                self.path,
            "size":
                self.size,
            "sha256":
                self.digest,
        }


@dataclass(
    frozen=True,
    slots=True,
)
class ProjectPackage:
    schema_version: int
    era: str
    family: str
    gameplay_dialect: str | None
    tree_digest: str
    files: tuple[
        PackageFile,
        ...,
    ]
    quality: tuple[
        tuple[str, object],
        ...,
    ]
    package_digest: str

    @property
    def file_count(
        self,
    ) -> int:
        return len(
            self.files
        )

    @property
    def total_bytes(
        self,
    ) -> int:
        return sum(
            item.size
            for item
            in self.files
        )

    def quality_document(
        self,
    ) -> dict[str, object]:
        return dict(
            self.quality
        )

    def identity_document(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version":
                self.schema_version,
            "engine_era":
                self.era,
            "engine_family":
                self.family,
            "gameplay_dialect":
                self.gameplay_dialect,
            "tree_digest":
                self.tree_digest,
            "file_count":
                self.file_count,
            "total_bytes":
                self.total_bytes,
            "files": [
                item.manifest_entry()
                for item
                in self.files
            ],
            "quality":
                self.quality_document(),
            "executable_sandbox_code":
                False,
        }

    def manifest(
        self,
    ) -> dict[str, object]:
        value = (
            self.identity_document()
        )
        value[
            "package_digest"
        ] = self.package_digest
        return value

    def payload(
        self,
    ) -> dict[str, object]:
        """Structured payload compatible with Forge materialisers."""

        return {
            "name":
                (
                    "jeeves-"
                    + self.era
                    + "-project"
                ),
            "package":
                self.manifest(),
            "pack": {
                "engine_era":
                    self.era,
                "engine_family":
                    self.family,
                "tree_digest":
                    self.tree_digest,
                "package_digest":
                    self.package_digest,
            },
            "files": {
                item.path:
                    item.content
                for item
                in self.files
            },
        }


@dataclass(
    frozen=True,
    slots=True,
)
class PackageVerification:
    passed: bool
    package_digest_ok: bool
    tree_digest_ok: bool
    file_inventory_ok: bool
    file_digests_ok: bool
    quality_attested: bool
    failures: tuple[
        str,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class PackageArchive:
    data: bytes
    digest: str
    file_count: int
    uncompressed_bytes: int

    def __post_init__(
        self,
    ) -> None:
        if (
            self.digest
            != _sha_bytes(
                self.data
            )
        ):
            raise GameEngineLabError(
                "archive digest mismatch"
            )
        if (
            len(self.data)
            > MAX_ARCHIVE_BYTES
        ):
            raise GameEngineLabError(
                "portable archive exceeds bounded size"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class PackagePublication:
    name: str
    archive_digest: str
    package_digest: str
    chunk_digests: tuple[
        str,
        ...,
    ]
    total_bytes: int
    manifest: Manifest


def _package_files(
    tree: VirtualFileTree,
) -> tuple[
    PackageFile,
    ...,
]:
    values = []
    for path in sorted(
        tree.files
    ):
        content = tree.read(
            path
        )
        encoded = content.encode(
            "utf-8"
        )
        values.append(
            PackageFile(
                path,
                len(encoded),
                _sha_bytes(
                    encoded
                ),
                content,
            )
        )
    if (
        len(values)
        > MAX_PACKAGE_FILES
    ):
        raise GameEngineLabError(
            "package file budget exceeded"
        )
    if (
        sum(
            item.size
            for item in values
        )
        > MAX_PACKAGE_BYTES
    ):
        raise GameEngineLabError(
            "package byte budget exceeded"
        )
    return tuple(
        values
    )


def build_project_package(
    project: GameProjectSandbox,
    *,
    lab:
        ExecutableGameProjectLab
        | None = None,
    require_quality: bool = True,
) -> ProjectPackage:
    """Build a deterministic package from a project without mutating it."""

    active_lab = (
        lab
        or ExecutableGameProjectLab()
    )
    report = (
        active_lab.evaluate(
            project
        )
    )
    if (
        require_quality
        and not report.passed
    ):
        raise GameEngineLabError(
            (
                "cannot package project "
                "that fails quality gates: "
                + ",".join(
                    report.failed
                )
            )
        )
    files = _package_files(
        project.tree
    )
    quality = (
        _quality_document(
            report
        )
    )
    quality_tuple = tuple(
        sorted(
            quality.items(),
            key=lambda row:
                row[0],
        )
    )
    identity = {
        "schema_version":
            PACKAGE_SCHEMA_VERSION,
        "engine_era":
            project.era.value,
        "engine_family":
            project.family.value,
        "gameplay_dialect":
            project.gameplay_dialect,
        "tree_digest":
            project.tree.digest,
        "file_count":
            len(files),
        "total_bytes":
            sum(
                item.size
                for item in files
            ),
        "files": [
            item.manifest_entry()
            for item
            in files
        ],
        "quality":
            quality,
        "executable_sandbox_code":
            False,
    }
    return ProjectPackage(
        PACKAGE_SCHEMA_VERSION,
        project.era.value,
        project.family.value,
        project.gameplay_dialect,
        project.tree.digest,
        files,
        quality_tuple,
        _sha_text(
            _canonical(
                identity
            )
        ),
    )


def verify_project_package(
    package: ProjectPackage,
) -> PackageVerification:
    failures: list[str] = []

    if (
        package.schema_version
        != PACKAGE_SCHEMA_VERSION
    ):
        failures.append(
            "schema"
        )

    expected_package_digest = (
        _sha_text(
            _canonical(
                package.identity_document()
            )
        )
    )
    package_digest_ok = (
        package.package_digest
        == expected_package_digest
    )
    if not package_digest_ok:
        failures.append(
            "package_digest"
        )

    sorted_paths = tuple(
        sorted(
            item.path
            for item
            in package.files
        )
    )
    actual_paths = tuple(
        item.path
        for item
        in package.files
    )
    file_inventory_ok = (
        len(actual_paths)
        == len(
            set(
                actual_paths
            )
        )
        and actual_paths
        == sorted_paths
        and package.file_count
        <= MAX_PACKAGE_FILES
        and package.total_bytes
        <= MAX_PACKAGE_BYTES
    )
    if not file_inventory_ok:
        failures.append(
            "inventory"
        )

    file_digests_ok = True
    tree_files: dict[
        str,
        str,
    ] = {}
    for item in package.files:
        encoded = (
            item.content.encode(
                "utf-8"
            )
        )
        if (
            len(encoded)
            != item.size
            or _sha_bytes(
                encoded
            )
            != item.digest
        ):
            file_digests_ok = False
        tree_files[
            item.path
        ] = item.content
    if not file_digests_ok:
        failures.append(
            "file_digest"
        )

    try:
        restored = VirtualFileTree(
            tree_files
        )
    except GameEngineLabError:
        tree_digest_ok = False
    else:
        tree_digest_ok = (
            restored.digest
            == package.tree_digest
        )
    if not tree_digest_ok:
        failures.append(
            "tree_digest"
        )

    quality = (
        package.quality_document()
    )
    quality_attested = (
        quality.get(
            "passed"
        )
        is True
        and quality.get(
            "failed"
        )
        == []
        and all(
            (
                isinstance(
                    quality.get(
                        name
                    ),
                    (
                        int,
                        float,
                    ),
                )
                and float(
                    quality[
                        name
                    ]
                )
                == 1.0
            )
            for name
            in (
                "runtime_score",
                "asset_score",
                "script_score",
                "physics_score",
                "audio_score",
                "animation_score",
            )
        )
    )
    if not quality_attested:
        failures.append(
            "quality"
        )

    return PackageVerification(
        not failures,
        package_digest_ok,
        tree_digest_ok,
        file_inventory_ok,
        file_digests_ok,
        quality_attested,
        tuple(
            failures
        ),
    )


def restore_package_tree(
    package: ProjectPackage,
) -> VirtualFileTree:
    verification = (
        verify_project_package(
            package
        )
    )
    if not verification.passed:
        raise GameEngineLabError(
            (
                "package verification failed: "
                + ",".join(
                    verification.failures
                )
            )
        )
    return VirtualFileTree(
        {
            item.path:
                item.content
            for item
            in package.files
        }
    )


def _zip_info(
    path: str,
) -> zipfile.ZipInfo:
    # ZIP's minimum timestamp is 1980. Pin every mutable metadata field.
    info = zipfile.ZipInfo(
        path,
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
    info.flag_bits = 0
    return info


def archive_project_package(
    package: ProjectPackage,
) -> PackageArchive:
    """Emit deterministic portable ZIP bytes for a verified package."""

    verification = (
        verify_project_package(
            package
        )
    )
    if not verification.passed:
        raise GameEngineLabError(
            (
                "cannot archive invalid package: "
                + ",".join(
                    verification.failures
                )
            )
        )
    stream = io.BytesIO()
    with zipfile.ZipFile(
        stream,
        mode="w",
        compression=
            zipfile.ZIP_STORED,
        allowZip64=False,
    ) as archive:
        manifest_bytes = (
            json.dumps(
                package.manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode(
            "utf-8"
        )
        archive.writestr(
            _zip_info(
                PACKAGE_MANIFEST_PATH
            ),
            manifest_bytes,
        )
        for item in package.files:
            archive.writestr(
                _zip_info(
                    PACKAGE_FILE_PREFIX
                    + item.path
                ),
                item.content.encode(
                    "utf-8"
                ),
            )
    data = stream.getvalue()
    if (
        len(data)
        > MAX_ARCHIVE_BYTES
    ):
        raise GameEngineLabError(
            "portable archive exceeds bounded size"
        )
    return PackageArchive(
        data,
        _sha_bytes(
            data
        ),
        package.file_count,
        package.total_bytes,
    )


def inspect_project_archive(
    data: bytes,
) -> dict[str, object]:
    """Read and fully attest a canonical portable archive without execution."""

    if (
        not isinstance(
            data,
            bytes,
        )
        or not data
        or len(data)
        > MAX_ARCHIVE_BYTES
    ):
        raise GameEngineLabError(
            "invalid portable archive bytes"
        )
    try:
        stream = io.BytesIO(
            data
        )
        with zipfile.ZipFile(
            stream,
            "r",
        ) as archive:
            infos = (
                archive.infolist()
            )
            names = tuple(
                item.filename
                for item
                in infos
            )
            if (
                not names
                or names[0]
                != PACKAGE_MANIFEST_PATH
            ):
                raise GameEngineLabError(
                    "portable archive manifest must be first"
                )
            if (
                len(names)
                > MAX_PACKAGE_FILES + 1
                or len(names)
                != len(
                    set(names)
                )
            ):
                raise GameEngineLabError(
                    "portable archive inventory outside bounds"
                )
            if any(
                (
                    name.startswith("/")
                    or name.endswith("/")
                    or ".."
                    in name.split("/")
                )
                for name
                in names
            ):
                raise GameEngineLabError(
                    "portable archive contains unsafe path"
                )
            if any(
                (
                    item.compress_type
                    != zipfile.ZIP_STORED
                    or (
                        item.flag_bits
                        & 0x1
                    )
                    != 0
                )
                for item
                in infos
            ):
                raise GameEngineLabError(
                    "portable archive uses noncanonical ZIP encoding"
                )
            total_uncompressed = sum(
                item.file_size
                for item
                in infos[
                    1:
                ]
            )
            if (
                total_uncompressed
                > MAX_PACKAGE_BYTES
            ):
                raise GameEngineLabError(
                    "portable archive expands beyond package bounds"
                )

            manifest_bytes = (
                archive.read(
                    PACKAGE_MANIFEST_PATH
                )
            )
            if (
                len(manifest_bytes)
                > 2 * 1024 * 1024
            ):
                raise GameEngineLabError(
                    "portable archive manifest exceeds bounds"
                )
            manifest = json.loads(
                manifest_bytes.decode(
                    "utf-8"
                )
            )
            if (
                not isinstance(
                    manifest,
                    dict,
                )
                or manifest.get(
                    "schema_version"
                )
                != PACKAGE_SCHEMA_VERSION
            ):
                raise GameEngineLabError(
                    "portable archive package schema mismatch"
                )
            file_rows = (
                manifest.get(
                    "files"
                )
            )
            if not isinstance(
                file_rows,
                list,
            ):
                raise GameEngineLabError(
                    "portable archive file manifest malformed"
                )
            if (
                manifest.get(
                    "file_count"
                )
                != len(file_rows)
                or len(file_rows)
                > MAX_PACKAGE_FILES
            ):
                raise GameEngineLabError(
                    "portable archive file count mismatch"
                )

            expected_names: list[str] = []
            expected_digests: dict[
                str,
                str,
            ] = {}
            expected_sizes: dict[
                str,
                int,
            ] = {}
            sandbox_paths: list[
                str
            ] = []
            for row in file_rows:
                if not isinstance(
                    row,
                    dict,
                ):
                    raise GameEngineLabError(
                        "portable archive file entry malformed"
                    )
                path = row.get(
                    "path"
                )
                digest = row.get(
                    "sha256"
                )
                size = row.get(
                    "size"
                )
                if (
                    not isinstance(
                        path,
                        str,
                    )
                    or not path
                    or path.startswith("/")
                    or ".."
                    in path.split("/")
                    or not isinstance(
                        digest,
                        str,
                    )
                    or len(digest)
                    != 64
                    or not isinstance(
                        size,
                        int,
                    )
                    or isinstance(
                        size,
                        bool,
                    )
                    or size < 0
                ):
                    raise GameEngineLabError(
                        "portable archive file entry invalid"
                    )
                archive_name = (
                    PACKAGE_FILE_PREFIX
                    + path
                )
                if archive_name in (
                    expected_digests
                ):
                    raise GameEngineLabError(
                        "portable archive manifest duplicates a path"
                    )
                expected_names.append(
                    archive_name
                )
                expected_digests[
                    archive_name
                ] = digest
                expected_sizes[
                    archive_name
                ] = size
                sandbox_paths.append(
                    path
                )

            if (
                sandbox_paths
                != sorted(
                    sandbox_paths
                )
                or names[
                    1:
                ]
                != tuple(
                    expected_names
                )
            ):
                raise GameEngineLabError(
                    "portable archive ordering is noncanonical"
                )
            if (
                manifest.get(
                    "total_bytes"
                )
                != sum(
                    expected_sizes.values()
                )
                or manifest[
                    "total_bytes"
                ]
                != total_uncompressed
            ):
                raise GameEngineLabError(
                    "portable archive byte count mismatch"
                )

            tree_files: dict[
                str,
                str,
            ] = {}
            for archive_name, digest in (
                expected_digests.items()
            ):
                raw = archive.read(
                    archive_name
                )
                if (
                    len(raw)
                    != expected_sizes[
                        archive_name
                    ]
                    or _sha_bytes(
                        raw
                    )
                    != digest
                ):
                    raise GameEngineLabError(
                        "portable archive file digest mismatch"
                    )
                path = archive_name[
                    len(
                        PACKAGE_FILE_PREFIX
                    ):
                ]
                tree_files[
                    path
                ] = raw.decode(
                    "utf-8"
                )

            restored = VirtualFileTree(
                tree_files
            )
            if (
                restored.digest
                != manifest.get(
                    "tree_digest"
                )
            ):
                raise GameEngineLabError(
                    "portable archive tree digest mismatch"
                )

            package_digest = (
                manifest.get(
                    "package_digest"
                )
            )
            identity = dict(
                manifest
            )
            identity.pop(
                "package_digest",
                None,
            )
            if (
                not isinstance(
                    package_digest,
                    str,
                )
                or len(
                    package_digest
                )
                != 64
                or _sha_text(
                    _canonical(
                        identity
                    )
                )
                != package_digest
            ):
                raise GameEngineLabError(
                    "portable archive package digest mismatch"
                )
    except GameEngineLabError:
        raise
    except (
        zipfile.BadZipFile,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise GameEngineLabError(
            "portable archive is malformed"
        ) from exc
    return {
        "archive_digest":
            _sha_bytes(
                data
            ),
        "package_digest":
            manifest[
                "package_digest"
            ],
        "tree_digest":
            manifest[
                "tree_digest"
            ],
        "file_count":
            manifest[
                "file_count"
            ],
        "engine_era":
            manifest[
                "engine_era"
            ],
    }


def materialise_project_package(
    package: ProjectPackage,
    *,
    materialiser: str = "json",
    registry:
        MaterialisationRegistry
        | None = None,
) -> bytes:
    """Reuse Forge materialisers for structured package representations."""

    verification = (
        verify_project_package(
            package
        )
    )
    if not verification.passed:
        raise GameEngineLabError(
            "cannot materialise invalid package"
        )
    active = (
        registry
        or MaterialisationRegistry()
    )
    try:
        encoder = active.get(
            materialiser
        )
        return encoder.encode(
            package.payload()
        )
    except MaterialisationError as exc:
        raise GameEngineLabError(
            (
                "unknown project package materialiser: "
                + materialiser
            )
        ) from exc


def _chunks(
    data: bytes,
    size: int,
) -> Iterable[bytes]:
    for offset in range(
        0,
        len(data),
        size,
    ):
        yield data[
            offset:
            offset + size
        ]


def publish_project_package(
    package: ProjectPackage,
    lafs: Lafs,
    *,
    name: str | None = None,
    chunk_bytes: int = (
        CHUNK_MAX_BYTES
    ),
) -> PackagePublication:
    """Publish deterministic archive bytes into existing append-only LAFS."""

    if (
        type(chunk_bytes) is not int
        or not 1
        <= chunk_bytes
        <= CHUNK_MAX_BYTES
    ):
        raise GameEngineLabError(
            "LAFS package chunk size outside bounds"
        )
    archive = (
        archive_project_package(
            package
        )
    )
    manifest_name = (
        name
        or (
            "jeeves/"
            + package.era
            + "/"
            + package.package_digest
            + ".zip"
        )
    )
    if (
        not isinstance(
            manifest_name,
            str,
        )
        or not manifest_name.strip()
        or len(
            manifest_name
        )
        > 256
    ):
        raise GameEngineLabError(
            "LAFS package manifest name invalid"
        )

    digests = tuple(
        lafs.put_chunk(
            chunk
        )
        for chunk
        in _chunks(
            archive.data,
            chunk_bytes,
        )
    )
    if not digests:
        raise GameEngineLabError(
            "package archive unexpectedly empty"
        )
    manifest = lafs.pin_manifest(
        manifest_name,
        list(
            digests
        ),
    )
    reassembled = lafs.read_manifest(
        manifest_name
    )
    if (
        reassembled
        != archive.data
        or _sha_bytes(
            reassembled
            if reassembled
            is not None
            else b""
        )
        != archive.digest
    ):
        raise GameEngineLabError(
            "LAFS package publication verification failed"
        )
    return PackagePublication(
        manifest_name,
        archive.digest,
        package.package_digest,
        digests,
        len(
            archive.data
        ),
        manifest,
    )
