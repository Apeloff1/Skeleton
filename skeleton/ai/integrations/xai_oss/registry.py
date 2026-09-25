"""Pinned provenance and license disposition for public xAI/Grok sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Final


_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class LicenseDisposition(str, Enum):
    RUNTIME_ADMITTED = "runtime_admitted"
    RESEARCH_ONLY = "research_only"
    METADATA_ONLY = "metadata_only"


@dataclass(frozen=True, slots=True)
class XAISource:
    source_id: str
    repository: str
    commit_sha: str
    license_expression: str
    disposition: LicenseDisposition
    role: str
    snapshot_root: str | None = None
    package_name: str | None = None
    package_version: str | None = None
    minimum_python: tuple[int, int] | None = None
    license_evidence: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must be non-empty")
        if not self.repository.startswith("xai-org/"):
            raise ValueError("repository must be an official xai-org repository")
        if not _FULL_SHA.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a full lowercase Git SHA")
        if not self.license_expression.strip():
            raise ValueError("license_expression must be non-empty")
        if self.snapshot_root is not None and not self.snapshot_root.startswith(
            "skeleton/ai/research/external/xAI/"
        ):
            raise ValueError("snapshot_root must remain in the xAI research quarantine")
        if (
            self.disposition is LicenseDisposition.RUNTIME_ADMITTED
            and self.license_expression != "Apache-2.0"
        ):
            raise ValueError("runtime-admitted xAI sources must be Apache-2.0")

    @property
    def executable_promotion_allowed(self) -> bool:
        return self.disposition is LicenseDisposition.RUNTIME_ADMITTED


SOURCES: Final[dict[str, XAISource]] = {
    "grok-1": XAISource(
        source_id="grok-1",
        repository="xai-org/grok-1",
        commit_sha="7050ed204b8206bb8645c7b7bbef7252f79561b0",
        license_expression="Apache-2.0",
        disposition=LicenseDisposition.RUNTIME_ADMITTED,
        role="open-weight Grok-1 architecture and reference inference implementation",
        snapshot_root="skeleton/ai/research/external/xAI/grok-1",
        license_evidence="README.md plus Apache-2.0 source-file headers",
        notes="Weights are Apache-2.0 but are not committed; materialization stays explicit.",
    ),
    "grok-build": XAISource(
        source_id="grok-build",
        repository="xai-org/grok-build",
        commit_sha="f0e3be1100ef5252488e3be8bb0e91cf68d8c305",
        license_expression="Apache-2.0",
        disposition=LicenseDisposition.RUNTIME_ADMITTED,
        role="coding-agent approvals, MCP ownership, durable checkpoints and runtime research",
        snapshot_root="skeleton/ai/research/external/xAI/grok-build",
        license_evidence="LICENSE",
        notes="Selected first-party files only; vendored third-party implementations are excluded.",
    ),
    "grok-build-plugin-cc": XAISource(
        source_id="grok-build-plugin-cc",
        repository="xai-org/grok-build-plugin-cc",
        commit_sha="92b76a670713335229644e94add15ab40c80e547",
        license_expression="Apache-2.0",
        disposition=LicenseDisposition.RUNTIME_ADMITTED,
        role="cross-agent delegation and session-transfer research",
        snapshot_root="skeleton/ai/research/external/xAI/grok-build-plugin-cc",
        license_evidence="LICENSE",
    ),
    "xai-sdk-python": XAISource(
        source_id="xai-sdk-python",
        repository="xai-org/xai-sdk-python",
        commit_sha="47125e210ed7e0c5056464b476ce6efce8e6c56d",
        license_expression="Apache-2.0",
        disposition=LicenseDisposition.RUNTIME_ADMITTED,
        role="official xAI API provider-edge interoperability",
        snapshot_root="skeleton/ai/research/external/xAI/xai-sdk-python",
        package_name="xai-sdk",
        package_version="1.20.0",
        minimum_python=(3, 10),
        license_evidence="LICENSE and pyproject.toml",
    ),
    "xai-proto": XAISource(
        source_id="xai-proto",
        repository="xai-org/xai-proto",
        commit_sha="c22ad8b1d87375ab8796b224aa56785ed922eb0d",
        license_expression="Apache-2.0",
        disposition=LicenseDisposition.RUNTIME_ADMITTED,
        role="public xAI gRPC service and message contracts",
        snapshot_root="skeleton/ai/research/external/xAI/xai-proto",
        license_evidence="LICENSE",
    ),
    "grok-prompts": XAISource(
        source_id="grok-prompts",
        repository="xai-org/grok-prompts",
        commit_sha="a7c186f5ccac95875c0041aed60398f6ecb6d6c7",
        license_expression="AGPL-3.0-only",
        disposition=LicenseDisposition.METADATA_ONLY,
        role="published Grok assistant prompt research",
        license_evidence="LICENSE",
        notes="Not copied or imported; copyleft review required before future use.",
    ),
    "xai-cookbook": XAISource(
        source_id="xai-cookbook",
        repository="xai-org/xai-cookbook",
        commit_sha="01d842179c4c41c326bd8ce8aa65edce9c9c231d",
        license_expression="LicenseRef-xAI-Beta-Testing",
        disposition=LicenseDisposition.METADATA_ONLY,
        role="xAI API example and integration research",
        license_evidence="LICENSE",
        notes="Beta license limits intended use to testing/evaluation; no source copied.",
    ),
}


def source(source_id: str) -> XAISource:
    try:
        return SOURCES[source_id]
    except KeyError as exc:
        raise KeyError(f"unknown xAI OSS source: {source_id}") from exc


__all__ = ["LicenseDisposition", "SOURCES", "XAISource", "source"]
