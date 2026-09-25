"""Pinned provenance registry for OpenAI-published open-source material.

The executable Skeleton tree never imports source from the research quarantine.
This registry binds clean-room adapters to exact upstream commits and licenses.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final


_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class OpenAISource:
    source_id: str
    repository: str
    commit_sha: str
    license_spdx: str
    package_name: str | None
    minimum_python: tuple[int, int] | None
    snapshot_root: str
    role: str

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_id.strip():
            raise ValueError("source_id must be non-empty")
        if not self.repository.startswith("openai/"):
            raise ValueError("repository must be an OpenAI GitHub repository")
        if not _FULL_SHA.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a full lowercase Git SHA")
        if self.license_spdx not in {"MIT", "Apache-2.0", "CC0-1.0"}:
            raise ValueError("unsupported upstream license")
        if not self.snapshot_root.startswith(
            "skeleton/ai/research/external/OpenAI/"
        ):
            raise ValueError("snapshot_root must remain in OpenAI research quarantine")

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "license_spdx": self.license_spdx,
            "package_name": self.package_name,
            "minimum_python": (
                None
                if self.minimum_python is None
                else ".".join(str(part) for part in self.minimum_python)
            ),
            "snapshot_root": self.snapshot_root,
            "role": self.role,
        }


SOURCES: Final[dict[str, OpenAISource]] = {
    "agents-sdk": OpenAISource(
        source_id="agents-sdk",
        repository="openai/openai-agents-python",
        commit_sha="525cd20f6da65f23a24ea1632ba620f6f3bd2f93",
        license_spdx="MIT",
        package_name="openai-agents",
        minimum_python=(3, 10),
        snapshot_root="skeleton/ai/research/external/OpenAI/openai-agents-python",
        role="agent handoffs, guardrails, sessions and interoperability research",
    ),
    "tiktoken": OpenAISource(
        source_id="tiktoken",
        repository="openai/tiktoken",
        commit_sha="4e71bbe0c078468e00fefbf94b39849389f346e5",
        license_spdx="MIT",
        package_name="tiktoken",
        minimum_python=(3, 9),
        snapshot_root="skeleton/ai/research/external/OpenAI/tiktoken",
        role="exact BPE token accounting and context budgeting",
    ),
    "whisper": OpenAISource(
        source_id="whisper",
        repository="openai/whisper",
        commit_sha="86098128c0b4f24f0e2aa2994de830614b474227",
        license_spdx="MIT",
        package_name="openai-whisper",
        minimum_python=(3, 8),
        snapshot_root="skeleton/ai/research/external/OpenAI/whisper",
        role="local speech recognition and transcription",
    ),
    "harmony": OpenAISource(
        source_id="harmony",
        repository="openai/harmony",
        commit_sha="abd677f7ac962629c808197caa1feb9e3e95d2b0",
        license_spdx="Apache-2.0",
        package_name="openai-harmony",
        minimum_python=(3, 8),
        snapshot_root="skeleton/ai/research/external/OpenAI/harmony",
        role="gpt-oss response/tool-call encoding",
    ),
    "gpt-oss": OpenAISource(
        source_id="gpt-oss",
        repository="openai/gpt-oss",
        commit_sha="7b583341fe16729127f6d5b94a7b09ccae97e1a1",
        license_spdx="Apache-2.0",
        package_name="gpt-oss",
        minimum_python=(3, 12),
        snapshot_root="skeleton/ai/research/external/OpenAI/gpt-oss",
        role="open-weight local reasoning and agent-tool runtime research",
    ),
    "codex": OpenAISource(
        source_id="codex",
        repository="openai/codex",
        commit_sha="782826663df3e898d0c594a13f6f75cc2a498644",
        license_spdx="Apache-2.0",
        package_name="openai-codex",
        minimum_python=None,
        snapshot_root="skeleton/ai/research/external/OpenAI/codex",
        role="coding-agent sandbox, approval and patch execution interoperability",
    ),
    "evals": OpenAISource(
        source_id="evals",
        repository="openai/evals",
        commit_sha="8eac7a7de5215c907fbddc30efdaf316913eccdd",
        license_spdx="MIT",
        package_name="evals",
        minimum_python=(3, 9),
        snapshot_root="skeleton/ai/research/external/OpenAI/evals",
        role="evaluation harness and recorder interoperability",
    ),
    "model-spec": OpenAISource(
        source_id="model-spec",
        repository="openai/model_spec",
        commit_sha="7f1cf79fcb656c07f77c8d95b6fbc78dc7fac5b6",
        license_spdx="CC0-1.0",
        package_name=None,
        minimum_python=None,
        snapshot_root="skeleton/ai/research/external/OpenAI/model_spec",
        role="behavioral-policy research reference only; never runtime authority",
    ),
}


def source(source_id: str) -> OpenAISource:
    try:
        return SOURCES[source_id]
    except KeyError as exc:
        raise KeyError(f"unknown OpenAI OSS source: {source_id}") from exc


__all__ = ["OpenAISource", "SOURCES", "source"]
