"""Async execution owners for privileged canonical tool adapters.

Policy objects normalize and deny unsafe requests. These owners are the sole
execution boundary for subprocess, database, network, and artifact side effects
used by the backend compatibility registry. Application code injects ports and
feature switches; it does not implement the privileged I/O body itself.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import os
import subprocess
import tempfile
from typing import Any, Callable, Mapping

from skeleton.skills.tool_adapters.policy import (
    ArtifactAdapterPolicy,
    DatabaseAdapterPolicy,
    NetworkEgressPolicy,
    SandboxAdapterPolicy,
    ToolAdapterDenied,
)


DatabaseProvider = Callable[[], Any]
ExecutionEnabled = Callable[[], bool]
DisabledResponse = Callable[[str], dict[str, Any]]


@dataclass(slots=True)
class AsyncSandboxCompileAdapter:
    """Own bounded compiler subprocess execution behind sandbox policy."""

    policy: SandboxAdapterPolicy = field(default_factory=SandboxAdapterPolicy)
    execution_enabled: ExecutionEnabled = lambda: True
    disabled_response: DisabledResponse = lambda name: {
        "ok": False,
        "disabled": True,
        "error": f"{name} is disabled",
    }

    async def execute(self, params: Mapping[str, Any]) -> dict[str, Any]:
        if not self.execution_enabled():
            return dict(self.disabled_response("Tool compile execution"))

        scoped = self.policy.compile_request(params)
        language = scoped["language"]
        code = scoped["code"]
        timeout_seconds = float(scoped["timeout_seconds"])
        max_output_bytes = int(scoped["max_output_bytes"])
        max_memory_mb = int(scoped["max_memory_mb"])

        suffix_map = {
            "c": ".c",
            "cpp": ".cpp",
            "cxx": ".cpp",
            "go": ".go",
            "rust": ".rs",
        }
        command_map = {
            "c": lambda src, out: ["gcc", src, "-o", out],
            "cpp": lambda src, out: ["g++", src, "-o", out],
            "cxx": lambda src, out: ["g++", src, "-o", out],
            "go": lambda src, out: ["go", "build", "-o", out, src],
            "rust": lambda src, out: ["rustc", src, "-o", out],
        }

        def _run_compile() -> dict[str, Any]:
            with tempfile.TemporaryDirectory() as directory:
                source = os.path.join(
                    directory,
                    f"src{suffix_map[language]}",
                )
                output = os.path.join(directory, "a.out")
                with open(source, "w", encoding="utf-8") as handle:
                    handle.write(code)

                preexec_fn = None
                if os.name == "posix":

                    def _limits() -> None:
                        import resource

                        memory_bytes = max_memory_mb * 1024 * 1024
                        resource.setrlimit(
                            resource.RLIMIT_AS,
                            (memory_bytes, memory_bytes),
                        )
                        cpu_seconds = max(1, int(timeout_seconds) + 1)
                        resource.setrlimit(
                            resource.RLIMIT_CPU,
                            (cpu_seconds, cpu_seconds),
                        )

                    preexec_fn = _limits

                try:
                    with (
                        tempfile.TemporaryFile() as stdout_file,
                        tempfile.TemporaryFile() as stderr_file,
                    ):
                        process = subprocess.Popen(
                            command_map[language](source, output),
                            stdout=stdout_file,
                            stderr=stderr_file,
                            preexec_fn=preexec_fn,
                        )
                        try:
                            exit_code = process.wait(timeout=timeout_seconds)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                            return {
                                "ok": False,
                                "error": "compile timed out",
                            }

                        def _tail(file_obj) -> str:
                            size = file_obj.seek(0, os.SEEK_END)
                            file_obj.seek(
                                max(0, size - max_output_bytes),
                                os.SEEK_SET,
                            )
                            return file_obj.read().decode(
                                "utf-8",
                                errors="replace",
                            )

                        return {
                            "ok": exit_code == 0,
                            "stdout": _tail(stdout_file),
                            "stderr": _tail(stderr_file),
                            "exit_code": exit_code,
                        }
                except FileNotFoundError:
                    return {"ok": False, "error": "toolchain_missing"}

        return await asyncio.to_thread(_run_compile)


@dataclass(slots=True)
class AsyncDatabaseQueryAdapter:
    """Own bounded database reads behind collection/operator policy."""

    database_provider: DatabaseProvider
    policy: DatabaseAdapterPolicy = field(default_factory=DatabaseAdapterPolicy)

    async def execute(self, params: Mapping[str, Any]) -> dict[str, Any]:
        scoped = self.policy.query_request(params)
        database = self.database_provider()
        collection = scoped["collection"]
        rows = await (
            database[collection]
            .find(scoped["filter"], scoped["project"])
            .limit(scoped["limit"])
            .to_list(length=scoped["limit"])
        )
        return {
            "ok": True,
            "collection": collection,
            "rows": rows,
            "count": len(rows),
        }


@dataclass(slots=True)
class AsyncNetworkSearchAdapter:
    """Own bounded public search egress and result sanitization."""

    policy: NetworkEgressPolicy = field(default_factory=NetworkEgressPolicy)

    async def execute(self, params: Mapping[str, Any]) -> dict[str, Any]:
        scoped = self.policy.search_request(params)
        query = scoped["query"]
        max_results = int(scoped["max_results"])
        kind = scoped["kind"]

        try:
            from ddgs import DDGS
        except Exception:
            return {"ok": False, "error": "ddgs_not_installed"}

        def _search() -> list[Any]:
            with DDGS() as client:
                if kind == "news":
                    return list(
                        client.news(query, max_results=max_results)
                    )
                if kind == "images":
                    return list(
                        client.images(query, max_results=max_results)
                    )
                return list(client.text(query, max_results=max_results))

        try:
            results = await asyncio.to_thread(_search)
            clean: list[dict[str, str]] = []
            for raw in results:
                if not isinstance(raw, Mapping):
                    continue
                normalized = self.policy.sanitize_result(raw)
                if normalized is not None:
                    clean.append(normalized)
                if len(clean) >= max_results:
                    break
            return {
                "ok": True,
                "query": query,
                "kind": kind,
                "results": clean,
                "count": len(clean),
            }
        except ToolAdapterDenied:
            raise
        except Exception:
            return {"ok": False, "error": "web_search_failed"}


@dataclass(slots=True)
class AsyncArtifactPackageAdapter:
    """Own build lookup, package execution, bounds, persistence, and cleanup."""

    database_provider: DatabaseProvider
    package_builder: Any
    policy: ArtifactAdapterPolicy = field(default_factory=ArtifactAdapterPolicy)
    execution_enabled: ExecutionEnabled = lambda: True
    disabled_response: DisabledResponse = lambda name: {
        "ok": False,
        "disabled": True,
        "error": f"{name} is disabled",
    }

    async def execute(self, params: Mapping[str, Any]) -> dict[str, Any]:
        if not self.execution_enabled():
            return dict(self.disabled_response("Tool binary packaging"))

        scoped = self.policy.package_request(params)
        build_id = scoped["build_id"]
        database = self.database_provider()
        document = await database.galaxy_builds.find_one(
            {"build_id": build_id},
            {"_id": 0},
        )
        if not document:
            return {
                "ok": False,
                "error": f"build_id not found: {build_id}",
            }

        raw_output = await self.package_builder.package_build(
            document,
            kinds=scoped["kinds"],
        )
        output = dict(raw_output)
        artifacts = output.get("artifacts", [])
        if not isinstance(artifacts, list):
            return {"ok": False, "error": "invalid_artifact_result"}

        oversized: list[str] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            size_bytes = int(artifact.get("size_bytes") or 0)
            if size_bytes > int(scoped["max_output_bytes"]):
                oversized.append(
                    str(artifact.get("artifact_id") or "unknown")
                )
                self._remove_artifact_path(artifact)
            else:
                artifact["retention_days"] = scoped["retention_days"]

        if oversized:
            return {
                "ok": False,
                "error": "artifact_too_large",
                "artifacts_rejected": oversized,
            }

        try:
            for artifact in artifacts:
                if not isinstance(artifact, Mapping):
                    continue
                artifact_id = artifact.get("artifact_id")
                if not isinstance(artifact_id, str) or not artifact_id:
                    continue
                await database.build_artifacts.update_one(
                    {"artifact_id": artifact_id},
                    {"$set": dict(artifact)},
                    upsert=True,
                )
        except Exception:
            # Preserve legacy compatibility: packaging success remains usable
            # when optional metadata projection is temporarily unavailable.
            pass

        return {"ok": True, **output}

    def compensate_result(self, result: Mapping[str, Any] | None) -> None:
        if result is None:
            return
        artifacts = result.get("artifacts", [])
        if not isinstance(artifacts, list):
            return
        for artifact in artifacts:
            if isinstance(artifact, Mapping):
                self._remove_artifact_path(artifact)

    @staticmethod
    def _remove_artifact_path(artifact: Mapping[str, Any]) -> None:
        path = artifact.get("path")
        if not isinstance(path, str):
            return
        try:
            os.remove(path)
        except (FileNotFoundError, OSError):
            pass


__all__ = [
    "AsyncArtifactPackageAdapter",
    "AsyncDatabaseQueryAdapter",
    "AsyncNetworkSearchAdapter",
    "AsyncSandboxCompileAdapter",
]
