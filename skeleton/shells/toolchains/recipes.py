"""Named multi-command recipes over logical shell contracts.

Recipes contain only logical command identities. They do not bind executable
paths and cannot bypass the normal ShellExecutor authority boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from skeleton.shells.toolchains.all import DEFAULT_CATALOG


@dataclass(frozen=True)
class ToolchainStep:
    contract: str
    required: bool = True
    stop_on_failure: bool = True

    def __post_init__(self) -> None:
        DEFAULT_CATALOG.get(self.contract)


@dataclass(frozen=True)
class ToolchainRecipe:
    name: str
    steps: tuple[ToolchainStep, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("recipe name is required")
        if not self.steps:
            raise ValueError("recipe requires at least one step")
        object.__setattr__(self, "steps", tuple(self.steps))

    def contract_names(self) -> tuple[str, ...]:
        return tuple(step.contract for step in self.steps)


class RecipeCatalog:
    def __init__(self, recipes: Iterable[ToolchainRecipe] = ()) -> None:
        self._recipes: dict[str, ToolchainRecipe] = {}
        for recipe in recipes:
            self.register(recipe)

    def register(self, recipe: ToolchainRecipe, *, replace: bool = False) -> None:
        if recipe.name in self._recipes and not replace:
            raise ValueError(f"recipe already registered: {recipe.name}")
        self._recipes[recipe.name] = recipe

    def get(self, name: str) -> ToolchainRecipe:
        try:
            return self._recipes[name]
        except KeyError as exc:
            raise KeyError(f"unknown toolchain recipe: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._recipes))

    def snapshot(self) -> Mapping[str, ToolchainRecipe]:
        return MappingProxyType(dict(self._recipes))


RECIPES = (
    ToolchainRecipe(
        name="python.verify",
        steps=(
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.mypy"),
            ToolchainStep("py.pytest"),
            ToolchainStep("py.coverage_report"),
        ),
        description="Verify python sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="python.preflight",
        steps=(
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.mypy"),
            ToolchainStep("py.pytest"),
        ),
        description="Run python preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="python_fast.verify",
        steps=(
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.pytest_collect"),
            ToolchainStep("py.pytest"),
        ),
        description="Verify python_fast sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="python_fast.preflight",
        steps=(
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.pytest_collect"),
        ),
        description="Run python_fast preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="node.verify",
        steps=(
            ToolchainStep("node.eslint_check"),
            ToolchainStep("node.prettier_check"),
            ToolchainStep("node.tsc_check"),
            ToolchainStep("node.vitest_run"),
        ),
        description="Verify node sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="node.preflight",
        steps=(
            ToolchainStep("node.eslint_check"),
            ToolchainStep("node.prettier_check"),
            ToolchainStep("node.tsc_check"),
        ),
        description="Run node preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="rust.verify",
        steps=(
            ToolchainStep("rust.fmt_check"),
            ToolchainStep("rust.clippy"),
            ToolchainStep("rust.test"),
        ),
        description="Verify rust sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="rust.preflight",
        steps=(
            ToolchainStep("rust.fmt_check"),
            ToolchainStep("rust.clippy"),
        ),
        description="Run rust preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="go.verify",
        steps=(
            ToolchainStep("go.fmt_check"),
            ToolchainStep("go.vet"),
            ToolchainStep("go.test"),
        ),
        description="Verify go sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="go.preflight",
        steps=(
            ToolchainStep("go.fmt_check"),
            ToolchainStep("go.vet"),
        ),
        description="Run go preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="jvm.verify",
        steps=(
            ToolchainStep("jvm.gradle_check"),
            ToolchainStep("jvm.gradle_test"),
        ),
        description="Verify jvm sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="jvm.preflight",
        steps=(
            ToolchainStep("jvm.gradle_check"),
        ),
        description="Run jvm preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="dotnet.verify",
        steps=(
            ToolchainStep("dotnet.format_check"),
            ToolchainStep("dotnet.build"),
            ToolchainStep("dotnet.test"),
        ),
        description="Verify dotnet sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="dotnet.preflight",
        steps=(
            ToolchainStep("dotnet.format_check"),
            ToolchainStep("dotnet.build"),
        ),
        description="Run dotnet preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="cmake.verify",
        steps=(
            ToolchainStep("build.cmake_configure"),
            ToolchainStep("build.cmake_build"),
            ToolchainStep("build.ctest"),
        ),
        description="Verify cmake sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="cmake.preflight",
        steps=(
            ToolchainStep("build.cmake_configure"),
            ToolchainStep("build.cmake_build"),
        ),
        description="Run cmake preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="bazel.verify",
        steps=(
            ToolchainStep("build.bazel_build"),
            ToolchainStep("build.bazel_test"),
        ),
        description="Verify bazel sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="bazel.preflight",
        steps=(
            ToolchainStep("build.bazel_build"),
        ),
        description="Run bazel preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="git_review.verify",
        steps=(
            ToolchainStep("git.status"),
            ToolchainStep("git.diff"),
            ToolchainStep("git.log"),
        ),
        description="Verify git_review sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="git_review.preflight",
        steps=(
            ToolchainStep("git.status"),
            ToolchainStep("git.diff"),
        ),
        description="Run git_review preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="container_review.verify",
        steps=(
            ToolchainStep("container.docker_ps"),
            ToolchainStep("container.docker_images"),
            ToolchainStep("container.docker_stats_once"),
        ),
        description="Verify container_review sources with deterministic logical contracts.",
    ),
    ToolchainRecipe(
        name="container_review.preflight",
        steps=(
            ToolchainStep("container.docker_ps"),
            ToolchainStep("container.docker_images"),
        ),
        description="Run container_review preflight checks before expensive execution.",
    ),
    ToolchainRecipe(
        name="polyglot.core.verify",
        steps=(
            ToolchainStep("git.status"),
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.pytest"),
            ToolchainStep("node.eslint_check"),
            ToolchainStep("node.tsc_check"),
            ToolchainStep("rust.clippy"),
            ToolchainStep("rust.test"),
            ToolchainStep("go.vet"),
            ToolchainStep("go.test"),
        ),
        description="Cross-language verification for core repositories.",
    ),
    ToolchainRecipe(
        name="polyglot.format.verify",
        steps=(
            ToolchainStep("py.ruff_format_check"),
            ToolchainStep("node.prettier_check"),
            ToolchainStep("rust.fmt_check"),
            ToolchainStep("go.fmt_check"),
            ToolchainStep("dotnet.format_check"),
        ),
        description="Cross-language formatting verification without writes.",
    ),
    ToolchainRecipe(
        name="polyglot.test",
        steps=(
            ToolchainStep("py.pytest"),
            ToolchainStep("node.vitest_run"),
            ToolchainStep("rust.test"),
            ToolchainStep("go.test"),
            ToolchainStep("jvm.gradle_test"),
            ToolchainStep("dotnet.test"),
        ),
        description="Cross-language test suite.",
    ),
    ToolchainRecipe(
        name="repository.review",
        steps=(
            ToolchainStep("git.status"),
            ToolchainStep("git.diff"),
            ToolchainStep("git.diff_word"),
            ToolchainStep("git.log"),
            ToolchainStep("git.ls_files"),
        ),
        description="Read-only repository review.",
    ),
    ToolchainRecipe(
        name="repository.integrity",
        steps=(
            ToolchainStep("git.status"),
            ToolchainStep("git.diff"),
            ToolchainStep("git.check_ignore"),
            ToolchainStep("git.check_attr"),
            ToolchainStep("posix.sha256sum"),
        ),
        description="Repository and path integrity inspection.",
    ),
    ToolchainRecipe(
        name="container.observe",
        steps=(
            ToolchainStep("container.docker_ps"),
            ToolchainStep("container.docker_images"),
            ToolchainStep("container.docker_stats_once"),
            ToolchainStep("container.docker_system_df"),
        ),
        description="Read-only Docker runtime observation.",
    ),
    ToolchainRecipe(
        name="filesystem.observe",
        steps=(
            ToolchainStep("posix.pwd"),
            ToolchainStep("posix.ls"),
            ToolchainStep("posix.du"),
            ToolchainStep("posix.df"),
            ToolchainStep("posix.stat"),
        ),
        description="Read-only workspace observation.",
    ),
    ToolchainRecipe(
        name="python.security",
        steps=(
            ToolchainStep("py.bandit_scan"),
            ToolchainStep("py.pip_audit"),
            ToolchainStep("py.pytest"),
        ),
        description="Python static security and regression checks.",
    ),
    ToolchainRecipe(
        name="rust.security",
        steps=(
            ToolchainStep("rust.cargo_audit"),
            ToolchainStep("rust.cargo_deny_check"),
            ToolchainStep("rust.test"),
        ),
        description="Rust dependency and regression checks.",
    ),
    ToolchainRecipe(
        name="go.security",
        steps=(
            ToolchainStep("go.govulncheck"),
            ToolchainStep("go.vet"),
            ToolchainStep("go.test"),
        ),
        description="Go vulnerability, vet, and test checks.",
    ),
    ToolchainRecipe(
        name="node.quality",
        steps=(
            ToolchainStep("node.eslint_check"),
            ToolchainStep("node.prettier_check"),
            ToolchainStep("node.tsc_check"),
            ToolchainStep("node.npm_audit"),
            ToolchainStep("node.vitest_run"),
        ),
        description="JavaScript quality and dependency checks.",
    ),
    ToolchainRecipe(
        name="dotnet.quality",
        steps=(
            ToolchainStep("dotnet.format_check"),
            ToolchainStep("dotnet.build"),
            ToolchainStep("dotnet.test"),
        ),
        description=".NET format, build, and test checks.",
    ),
    ToolchainRecipe(
        name="jvm.quality",
        steps=(
            ToolchainStep("jvm.checkstyle"),
            ToolchainStep("jvm.spotbugs"),
            ToolchainStep("jvm.gradle_check"),
            ToolchainStep("jvm.gradle_test"),
        ),
        description="JVM static analysis and test checks.",
    ),
    ToolchainRecipe(
        name="assurance.001.python",
        steps=(
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.mypy"),
            ToolchainStep("py.pytest"),
            ToolchainStep("py.coverage_report"),
        ),
        description="Assurance recipe 1 for python with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.002.python_fast",
        steps=(
            ToolchainStep("py.pytest_collect"),
            ToolchainStep("py.pytest"),
            ToolchainStep("py.ruff_check"),
        ),
        description="Assurance recipe 2 for python_fast with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.003.node",
        steps=(
            ToolchainStep("node.tsc_check"),
            ToolchainStep("node.vitest_run"),
            ToolchainStep("node.eslint_check"),
            ToolchainStep("node.prettier_check"),
        ),
        description="Assurance recipe 3 for node with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.004.rust",
        steps=(
            ToolchainStep("rust.fmt_check"),
            ToolchainStep("rust.clippy"),
            ToolchainStep("rust.test"),
        ),
        description="Assurance recipe 4 for rust with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.005.go",
        steps=(
            ToolchainStep("go.vet"),
            ToolchainStep("go.test"),
            ToolchainStep("go.fmt_check"),
        ),
        description="Assurance recipe 5 for go with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.006.jvm",
        steps=(
            ToolchainStep("jvm.gradle_test"),
            ToolchainStep("jvm.gradle_check"),
        ),
        description="Assurance recipe 6 for jvm with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.007.dotnet",
        steps=(
            ToolchainStep("dotnet.format_check"),
            ToolchainStep("dotnet.build"),
            ToolchainStep("dotnet.test"),
        ),
        description="Assurance recipe 7 for dotnet with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.008.cmake",
        steps=(
            ToolchainStep("build.cmake_build"),
            ToolchainStep("build.ctest"),
            ToolchainStep("build.cmake_configure"),
        ),
        description="Assurance recipe 8 for cmake with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.009.bazel",
        steps=(
            ToolchainStep("build.bazel_build"),
            ToolchainStep("build.bazel_test"),
        ),
        description="Assurance recipe 9 for bazel with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.010.git_review",
        steps=(
            ToolchainStep("git.status"),
            ToolchainStep("git.diff"),
            ToolchainStep("git.log"),
        ),
        description="Assurance recipe 10 for git_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.011.container_review",
        steps=(
            ToolchainStep("container.docker_images"),
            ToolchainStep("container.docker_stats_once"),
            ToolchainStep("container.docker_ps"),
        ),
        description="Assurance recipe 11 for container_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.012.python",
        steps=(
            ToolchainStep("py.coverage_report"),
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.mypy"),
            ToolchainStep("py.pytest"),
        ),
        description="Assurance recipe 12 for python with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.013.python_fast",
        steps=(
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.pytest_collect"),
            ToolchainStep("py.pytest"),
        ),
        description="Assurance recipe 13 for python_fast with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.014.node",
        steps=(
            ToolchainStep("node.prettier_check"),
            ToolchainStep("node.tsc_check"),
            ToolchainStep("node.vitest_run"),
            ToolchainStep("node.eslint_check"),
        ),
        description="Assurance recipe 14 for node with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.015.rust",
        steps=(
            ToolchainStep("rust.test"),
            ToolchainStep("rust.fmt_check"),
            ToolchainStep("rust.clippy"),
        ),
        description="Assurance recipe 15 for rust with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.016.go",
        steps=(
            ToolchainStep("go.fmt_check"),
            ToolchainStep("go.vet"),
            ToolchainStep("go.test"),
        ),
        description="Assurance recipe 16 for go with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.017.jvm",
        steps=(
            ToolchainStep("jvm.gradle_check"),
            ToolchainStep("jvm.gradle_test"),
        ),
        description="Assurance recipe 17 for jvm with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.018.dotnet",
        steps=(
            ToolchainStep("dotnet.test"),
            ToolchainStep("dotnet.format_check"),
            ToolchainStep("dotnet.build"),
        ),
        description="Assurance recipe 18 for dotnet with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.019.cmake",
        steps=(
            ToolchainStep("build.cmake_configure"),
            ToolchainStep("build.cmake_build"),
            ToolchainStep("build.ctest"),
        ),
        description="Assurance recipe 19 for cmake with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.020.bazel",
        steps=(
            ToolchainStep("build.bazel_test"),
            ToolchainStep("build.bazel_build"),
        ),
        description="Assurance recipe 20 for bazel with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.021.git_review",
        steps=(
            ToolchainStep("git.log"),
            ToolchainStep("git.status"),
            ToolchainStep("git.diff"),
        ),
        description="Assurance recipe 21 for git_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.022.container_review",
        steps=(
            ToolchainStep("container.docker_ps"),
            ToolchainStep("container.docker_images"),
            ToolchainStep("container.docker_stats_once"),
        ),
        description="Assurance recipe 22 for container_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.023.python",
        steps=(
            ToolchainStep("py.pytest"),
            ToolchainStep("py.coverage_report"),
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.mypy"),
        ),
        description="Assurance recipe 23 for python with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.024.python_fast",
        steps=(
            ToolchainStep("py.pytest"),
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.pytest_collect"),
        ),
        description="Assurance recipe 24 for python_fast with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.025.node",
        steps=(
            ToolchainStep("node.eslint_check"),
            ToolchainStep("node.prettier_check"),
            ToolchainStep("node.tsc_check"),
            ToolchainStep("node.vitest_run"),
        ),
        description="Assurance recipe 25 for node with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.026.rust",
        steps=(
            ToolchainStep("rust.clippy"),
            ToolchainStep("rust.test"),
            ToolchainStep("rust.fmt_check"),
        ),
        description="Assurance recipe 26 for rust with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.027.go",
        steps=(
            ToolchainStep("go.test"),
            ToolchainStep("go.fmt_check"),
            ToolchainStep("go.vet"),
        ),
        description="Assurance recipe 27 for go with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.028.jvm",
        steps=(
            ToolchainStep("jvm.gradle_test"),
            ToolchainStep("jvm.gradle_check"),
        ),
        description="Assurance recipe 28 for jvm with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.029.dotnet",
        steps=(
            ToolchainStep("dotnet.build"),
            ToolchainStep("dotnet.test"),
            ToolchainStep("dotnet.format_check"),
        ),
        description="Assurance recipe 29 for dotnet with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.030.cmake",
        steps=(
            ToolchainStep("build.ctest"),
            ToolchainStep("build.cmake_configure"),
            ToolchainStep("build.cmake_build"),
        ),
        description="Assurance recipe 30 for cmake with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.031.bazel",
        steps=(
            ToolchainStep("build.bazel_build"),
            ToolchainStep("build.bazel_test"),
        ),
        description="Assurance recipe 31 for bazel with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.032.git_review",
        steps=(
            ToolchainStep("git.diff"),
            ToolchainStep("git.log"),
            ToolchainStep("git.status"),
        ),
        description="Assurance recipe 32 for git_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.033.container_review",
        steps=(
            ToolchainStep("container.docker_stats_once"),
            ToolchainStep("container.docker_ps"),
            ToolchainStep("container.docker_images"),
        ),
        description="Assurance recipe 33 for container_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.034.python",
        steps=(
            ToolchainStep("py.mypy"),
            ToolchainStep("py.pytest"),
            ToolchainStep("py.coverage_report"),
            ToolchainStep("py.ruff_check"),
        ),
        description="Assurance recipe 34 for python with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.035.python_fast",
        steps=(
            ToolchainStep("py.pytest_collect"),
            ToolchainStep("py.pytest"),
            ToolchainStep("py.ruff_check"),
        ),
        description="Assurance recipe 35 for python_fast with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.036.node",
        steps=(
            ToolchainStep("node.vitest_run"),
            ToolchainStep("node.eslint_check"),
            ToolchainStep("node.prettier_check"),
            ToolchainStep("node.tsc_check"),
        ),
        description="Assurance recipe 36 for node with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.037.rust",
        steps=(
            ToolchainStep("rust.fmt_check"),
            ToolchainStep("rust.clippy"),
            ToolchainStep("rust.test"),
        ),
        description="Assurance recipe 37 for rust with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.038.go",
        steps=(
            ToolchainStep("go.vet"),
            ToolchainStep("go.test"),
            ToolchainStep("go.fmt_check"),
        ),
        description="Assurance recipe 38 for go with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.039.jvm",
        steps=(
            ToolchainStep("jvm.gradle_check"),
            ToolchainStep("jvm.gradle_test"),
        ),
        description="Assurance recipe 39 for jvm with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.040.dotnet",
        steps=(
            ToolchainStep("dotnet.format_check"),
            ToolchainStep("dotnet.build"),
            ToolchainStep("dotnet.test"),
        ),
        description="Assurance recipe 40 for dotnet with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.041.cmake",
        steps=(
            ToolchainStep("build.cmake_build"),
            ToolchainStep("build.ctest"),
            ToolchainStep("build.cmake_configure"),
        ),
        description="Assurance recipe 41 for cmake with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.042.bazel",
        steps=(
            ToolchainStep("build.bazel_test"),
            ToolchainStep("build.bazel_build"),
        ),
        description="Assurance recipe 42 for bazel with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.043.git_review",
        steps=(
            ToolchainStep("git.status"),
            ToolchainStep("git.diff"),
            ToolchainStep("git.log"),
        ),
        description="Assurance recipe 43 for git_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.044.container_review",
        steps=(
            ToolchainStep("container.docker_images"),
            ToolchainStep("container.docker_stats_once"),
            ToolchainStep("container.docker_ps"),
        ),
        description="Assurance recipe 44 for container_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.045.python",
        steps=(
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.mypy"),
            ToolchainStep("py.pytest"),
            ToolchainStep("py.coverage_report"),
        ),
        description="Assurance recipe 45 for python with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.046.python_fast",
        steps=(
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.pytest_collect"),
            ToolchainStep("py.pytest"),
        ),
        description="Assurance recipe 46 for python_fast with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.047.node",
        steps=(
            ToolchainStep("node.tsc_check"),
            ToolchainStep("node.vitest_run"),
            ToolchainStep("node.eslint_check"),
            ToolchainStep("node.prettier_check"),
        ),
        description="Assurance recipe 47 for node with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.048.rust",
        steps=(
            ToolchainStep("rust.test"),
            ToolchainStep("rust.fmt_check"),
            ToolchainStep("rust.clippy"),
        ),
        description="Assurance recipe 48 for rust with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.049.go",
        steps=(
            ToolchainStep("go.fmt_check"),
            ToolchainStep("go.vet"),
            ToolchainStep("go.test"),
        ),
        description="Assurance recipe 49 for go with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.050.jvm",
        steps=(
            ToolchainStep("jvm.gradle_test"),
            ToolchainStep("jvm.gradle_check"),
        ),
        description="Assurance recipe 50 for jvm with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.051.dotnet",
        steps=(
            ToolchainStep("dotnet.test"),
            ToolchainStep("dotnet.format_check"),
            ToolchainStep("dotnet.build"),
        ),
        description="Assurance recipe 51 for dotnet with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.052.cmake",
        steps=(
            ToolchainStep("build.cmake_configure"),
            ToolchainStep("build.cmake_build"),
            ToolchainStep("build.ctest"),
        ),
        description="Assurance recipe 52 for cmake with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.053.bazel",
        steps=(
            ToolchainStep("build.bazel_build"),
            ToolchainStep("build.bazel_test"),
        ),
        description="Assurance recipe 53 for bazel with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.054.git_review",
        steps=(
            ToolchainStep("git.log"),
            ToolchainStep("git.status"),
            ToolchainStep("git.diff"),
        ),
        description="Assurance recipe 54 for git_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.055.container_review",
        steps=(
            ToolchainStep("container.docker_ps"),
            ToolchainStep("container.docker_images"),
            ToolchainStep("container.docker_stats_once"),
        ),
        description="Assurance recipe 55 for container_review with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.056.python",
        steps=(
            ToolchainStep("py.coverage_report"),
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.mypy"),
            ToolchainStep("py.pytest"),
        ),
        description="Assurance recipe 56 for python with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.057.python_fast",
        steps=(
            ToolchainStep("py.pytest"),
            ToolchainStep("py.ruff_check"),
            ToolchainStep("py.pytest_collect"),
        ),
        description="Assurance recipe 57 for python_fast with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.058.node",
        steps=(
            ToolchainStep("node.prettier_check"),
            ToolchainStep("node.tsc_check"),
            ToolchainStep("node.vitest_run"),
            ToolchainStep("node.eslint_check"),
        ),
        description="Assurance recipe 58 for node with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.059.rust",
        steps=(
            ToolchainStep("rust.clippy"),
            ToolchainStep("rust.test"),
            ToolchainStep("rust.fmt_check"),
        ),
        description="Assurance recipe 59 for rust with stable ordered gates.",
    ),
    ToolchainRecipe(
        name="assurance.060.go",
        steps=(
            ToolchainStep("go.test"),
            ToolchainStep("go.fmt_check"),
            ToolchainStep("go.vet"),
        ),
        description="Assurance recipe 60 for go with stable ordered gates.",
    ),
)

DEFAULT_RECIPES = RecipeCatalog(RECIPES)
