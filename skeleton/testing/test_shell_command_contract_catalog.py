"""Explicit regression matrix for every standard command contract."""

from __future__ import annotations

import pytest

from skeleton.shells.contracts.catalog import catalog_statistics, standard_catalog, standard_contracts
from skeleton.shells.contracts.core import ContractExecutionPolicy, ContractViolation, RiskTier, ToolEffect
from skeleton.shells.contracts.intent import CommandIntent, CommandIntentStep, ContractPlanner
from skeleton.shells.contracts.profiles import developer_policy, infrastructure_review_policy, read_only_policy


def test_standard_catalog_has_broad_surface():
    stats = catalog_statistics()
    assert stats.commands >= 50
    assert stats.verbs >= 90
    assert stats.flags >= 100
    assert stats.critical_risk > 0
    assert stats.network_commands > 0
    assert stats.destructive_commands > 0


def test_standard_contract_names_are_unique():
    values = standard_contracts()
    names = [item.logical_name for item in values]
    assert len(names) == len(set(names))


def test_read_only_policy_rejects_write():
    catalog = standard_catalog()
    decision = catalog.resolve("git").require(("add", "file.txt"))
    guarded = read_only_policy().inspect(decision)
    assert not guarded.allowed


def test_developer_policy_accepts_low_risk_read():
    catalog = standard_catalog()
    decision = catalog.resolve("git").require(("status",))
    guarded = developer_policy().inspect(decision)
    assert guarded.allowed


def test_infrastructure_policy_requires_approval_for_apply():
    catalog = standard_catalog()
    decision = catalog.resolve("terraform").require(("apply",))
    guarded = infrastructure_review_policy().inspect(decision, approved=False)
    assert not guarded.allowed
    assert guarded.requires_approval
    approved = infrastructure_review_policy().inspect(decision, approved=True)
    assert approved.allowed


def test_planner_aggregates_effects_and_risk():
    catalog = standard_catalog()
    planner = ContractPlanner(catalog, infrastructure_review_policy())
    intent = CommandIntent(
        (
            CommandIntentStep("git", ("status",)),
            CommandIntentStep("terraform", ("validate",)),
        ),
        principal="test",
    )
    plan = planner.plan(intent)
    assert plan.allowed
    assert ToolEffect.READ in plan.effects
    assert len(plan.plan_digest) == 64



def test_git_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("git")
    decision = contract.validate(("status",))
    assert decision.allowed, decision.reason
    assert decision.command == "git"
    assert decision.normalized_args == ("status",)

def test_git_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("git")
    decision = contract.validate(("status", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_git_nul_argument_is_rejected():
    contract = standard_catalog().resolve("git")
    decision = contract.validate(("status", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_gh_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("gh")
    decision = contract.validate(("pr", "status"))
    assert decision.allowed, decision.reason
    assert decision.command == "gh"
    assert decision.normalized_args == ("pr", "status")

def test_gh_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("gh")
    decision = contract.validate(("pr", "status", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_gh_nul_argument_is_rejected():
    contract = standard_catalog().resolve("gh")
    decision = contract.validate(("pr", "status", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_jj_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("jj")
    decision = contract.validate(("status",))
    assert decision.allowed, decision.reason
    assert decision.command == "jj"
    assert decision.normalized_args == ("status",)

def test_jj_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("jj")
    decision = contract.validate(("status", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_jj_nul_argument_is_rejected():
    contract = standard_catalog().resolve("jj")
    decision = contract.validate(("status", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_hg_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("hg")
    decision = contract.validate(("status",))
    assert decision.allowed, decision.reason
    assert decision.command == "hg"
    assert decision.normalized_args == ("status",)

def test_hg_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("hg")
    decision = contract.validate(("status", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_hg_nul_argument_is_rejected():
    contract = standard_catalog().resolve("hg")
    decision = contract.validate(("status", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_svn_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("svn")
    decision = contract.validate(("status",))
    assert decision.allowed, decision.reason
    assert decision.command == "svn"
    assert decision.normalized_args == ("status",)

def test_svn_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("svn")
    decision = contract.validate(("status", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_svn_nul_argument_is_rejected():
    contract = standard_catalog().resolve("svn")
    decision = contract.validate(("status", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_python_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("python")
    decision = contract.validate(("script.py",))
    assert decision.allowed, decision.reason
    assert decision.command == "python"
    assert decision.normalized_args == ("script.py",)

def test_python_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("python")
    decision = contract.validate(("script.py", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_python_nul_argument_is_rejected():
    contract = standard_catalog().resolve("python")
    decision = contract.validate(("script.py", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_pytest_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("pytest")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "pytest"
    assert decision.normalized_args == ()

def test_pytest_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("pytest")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_pytest_nul_argument_is_rejected():
    contract = standard_catalog().resolve("pytest")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_ruff_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("ruff")
    decision = contract.validate(("check",))
    assert decision.allowed, decision.reason
    assert decision.command == "ruff"
    assert decision.normalized_args == ("check",)

def test_ruff_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("ruff")
    decision = contract.validate(("check", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_ruff_nul_argument_is_rejected():
    contract = standard_catalog().resolve("ruff")
    decision = contract.validate(("check", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_mypy_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("mypy")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "mypy"
    assert decision.normalized_args == ()

def test_mypy_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("mypy")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_mypy_nul_argument_is_rejected():
    contract = standard_catalog().resolve("mypy")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_uv_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("uv")
    decision = contract.validate(("run", "python"))
    assert decision.allowed, decision.reason
    assert decision.command == "uv"
    assert decision.normalized_args == ("run", "python")

def test_uv_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("uv")
    decision = contract.validate(("run", "python", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_uv_nul_argument_is_rejected():
    contract = standard_catalog().resolve("uv")
    decision = contract.validate(("run", "python", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_pip_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("pip")
    decision = contract.validate(("list",))
    assert decision.allowed, decision.reason
    assert decision.command == "pip"
    assert decision.normalized_args == ("list",)

def test_pip_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("pip")
    decision = contract.validate(("list", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_pip_nul_argument_is_rejected():
    contract = standard_catalog().resolve("pip")
    decision = contract.validate(("list", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_coverage_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("coverage")
    decision = contract.validate(("report",))
    assert decision.allowed, decision.reason
    assert decision.command == "coverage"
    assert decision.normalized_args == ("report",)

def test_coverage_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("coverage")
    decision = contract.validate(("report", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_coverage_nul_argument_is_rejected():
    contract = standard_catalog().resolve("coverage")
    decision = contract.validate(("report", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_node_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("node")
    decision = contract.validate(("file.js",))
    assert decision.allowed, decision.reason
    assert decision.command == "node"
    assert decision.normalized_args == ("file.js",)

def test_node_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("node")
    decision = contract.validate(("file.js", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_node_nul_argument_is_rejected():
    contract = standard_catalog().resolve("node")
    decision = contract.validate(("file.js", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_npm_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("npm")
    decision = contract.validate(("test",))
    assert decision.allowed, decision.reason
    assert decision.command == "npm"
    assert decision.normalized_args == ("test",)

def test_npm_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("npm")
    decision = contract.validate(("test", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_npm_nul_argument_is_rejected():
    contract = standard_catalog().resolve("npm")
    decision = contract.validate(("test", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_npx_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("npx")
    decision = contract.validate(("eslint",))
    assert decision.allowed, decision.reason
    assert decision.command == "npx"
    assert decision.normalized_args == ("eslint",)

def test_npx_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("npx")
    decision = contract.validate(("eslint", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_npx_nul_argument_is_rejected():
    contract = standard_catalog().resolve("npx")
    decision = contract.validate(("eslint", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_pnpm_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("pnpm")
    decision = contract.validate(("test",))
    assert decision.allowed, decision.reason
    assert decision.command == "pnpm"
    assert decision.normalized_args == ("test",)

def test_pnpm_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("pnpm")
    decision = contract.validate(("test", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_pnpm_nul_argument_is_rejected():
    contract = standard_catalog().resolve("pnpm")
    decision = contract.validate(("test", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_yarn_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("yarn")
    decision = contract.validate(("test",))
    assert decision.allowed, decision.reason
    assert decision.command == "yarn"
    assert decision.normalized_args == ("test",)

def test_yarn_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("yarn")
    decision = contract.validate(("test", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_yarn_nul_argument_is_rejected():
    contract = standard_catalog().resolve("yarn")
    decision = contract.validate(("test", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_eslint_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("eslint")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "eslint"
    assert decision.normalized_args == ()

def test_eslint_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("eslint")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_eslint_nul_argument_is_rejected():
    contract = standard_catalog().resolve("eslint")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_prettier_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("prettier")
    decision = contract.validate(("file.js",))
    assert decision.allowed, decision.reason
    assert decision.command == "prettier"
    assert decision.normalized_args == ("file.js",)

def test_prettier_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("prettier")
    decision = contract.validate(("file.js", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_prettier_nul_argument_is_rejected():
    contract = standard_catalog().resolve("prettier")
    decision = contract.validate(("file.js", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_vite_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("vite")
    decision = contract.validate(("build",))
    assert decision.allowed, decision.reason
    assert decision.command == "vite"
    assert decision.normalized_args == ("build",)

def test_vite_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("vite")
    decision = contract.validate(("build", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_vite_nul_argument_is_rejected():
    contract = standard_catalog().resolve("vite")
    decision = contract.validate(("build", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_cargo_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("cargo")
    decision = contract.validate(("check",))
    assert decision.allowed, decision.reason
    assert decision.command == "cargo"
    assert decision.normalized_args == ("check",)

def test_cargo_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("cargo")
    decision = contract.validate(("check", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_cargo_nul_argument_is_rejected():
    contract = standard_catalog().resolve("cargo")
    decision = contract.validate(("check", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_rustc_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("rustc")
    decision = contract.validate(("main.rs",))
    assert decision.allowed, decision.reason
    assert decision.command == "rustc"
    assert decision.normalized_args == ("main.rs",)

def test_rustc_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("rustc")
    decision = contract.validate(("main.rs", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_rustc_nul_argument_is_rejected():
    contract = standard_catalog().resolve("rustc")
    decision = contract.validate(("main.rs", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_go_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("go")
    decision = contract.validate(("test",))
    assert decision.allowed, decision.reason
    assert decision.command == "go"
    assert decision.normalized_args == ("test",)

def test_go_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("go")
    decision = contract.validate(("test", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_go_nul_argument_is_rejected():
    contract = standard_catalog().resolve("go")
    decision = contract.validate(("test", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_make_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("make")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "make"
    assert decision.normalized_args == ()

def test_make_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("make")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_make_nul_argument_is_rejected():
    contract = standard_catalog().resolve("make")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_cmake_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("cmake")
    decision = contract.validate(("configure",))
    assert decision.allowed, decision.reason
    assert decision.command == "cmake"
    assert decision.normalized_args == ("configure",)

def test_cmake_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("cmake")
    decision = contract.validate(("configure", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_cmake_nul_argument_is_rejected():
    contract = standard_catalog().resolve("cmake")
    decision = contract.validate(("configure", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_ninja_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("ninja")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "ninja"
    assert decision.normalized_args == ()

def test_ninja_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("ninja")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_ninja_nul_argument_is_rejected():
    contract = standard_catalog().resolve("ninja")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_gcc_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("gcc")
    decision = contract.validate(("main.c",))
    assert decision.allowed, decision.reason
    assert decision.command == "gcc"
    assert decision.normalized_args == ("main.c",)

def test_gcc_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("gcc")
    decision = contract.validate(("main.c", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_gcc_nul_argument_is_rejected():
    contract = standard_catalog().resolve("gcc")
    decision = contract.validate(("main.c", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_clang_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("clang")
    decision = contract.validate(("main.c",))
    assert decision.allowed, decision.reason
    assert decision.command == "clang"
    assert decision.normalized_args == ("main.c",)

def test_clang_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("clang")
    decision = contract.validate(("main.c", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_clang_nul_argument_is_rejected():
    contract = standard_catalog().resolve("clang")
    decision = contract.validate(("main.c", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_rg_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("rg")
    decision = contract.validate(("needle",))
    assert decision.allowed, decision.reason
    assert decision.command == "rg"
    assert decision.normalized_args == ("needle",)

def test_rg_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("rg")
    decision = contract.validate(("needle", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_rg_nul_argument_is_rejected():
    contract = standard_catalog().resolve("rg")
    decision = contract.validate(("needle", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_grep_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("grep")
    decision = contract.validate(("needle",))
    assert decision.allowed, decision.reason
    assert decision.command == "grep"
    assert decision.normalized_args == ("needle",)

def test_grep_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("grep")
    decision = contract.validate(("needle", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_grep_nul_argument_is_rejected():
    contract = standard_catalog().resolve("grep")
    decision = contract.validate(("needle", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_find_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("find")
    decision = contract.validate((".",))
    assert decision.allowed, decision.reason
    assert decision.command == "find"
    assert decision.normalized_args == (".",)

def test_find_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("find")
    decision = contract.validate((".", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_find_nul_argument_is_rejected():
    contract = standard_catalog().resolve("find")
    decision = contract.validate((".", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_ls_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("ls")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "ls"
    assert decision.normalized_args == ()

def test_ls_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("ls")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_ls_nul_argument_is_rejected():
    contract = standard_catalog().resolve("ls")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_cat_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("cat")
    decision = contract.validate(("file",))
    assert decision.allowed, decision.reason
    assert decision.command == "cat"
    assert decision.normalized_args == ("file",)

def test_cat_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("cat")
    decision = contract.validate(("file", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_cat_nul_argument_is_rejected():
    contract = standard_catalog().resolve("cat")
    decision = contract.validate(("file", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_head_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("head")
    decision = contract.validate(("file",))
    assert decision.allowed, decision.reason
    assert decision.command == "head"
    assert decision.normalized_args == ("file",)

def test_head_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("head")
    decision = contract.validate(("file", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_head_nul_argument_is_rejected():
    contract = standard_catalog().resolve("head")
    decision = contract.validate(("file", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_tail_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("tail")
    decision = contract.validate(("file",))
    assert decision.allowed, decision.reason
    assert decision.command == "tail"
    assert decision.normalized_args == ("file",)

def test_tail_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("tail")
    decision = contract.validate(("file", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_tail_nul_argument_is_rejected():
    contract = standard_catalog().resolve("tail")
    decision = contract.validate(("file", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_sort_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("sort")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "sort"
    assert decision.normalized_args == ()

def test_sort_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("sort")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_sort_nul_argument_is_rejected():
    contract = standard_catalog().resolve("sort")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_wc_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("wc")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "wc"
    assert decision.normalized_args == ()

def test_wc_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("wc")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_wc_nul_argument_is_rejected():
    contract = standard_catalog().resolve("wc")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_diff_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("diff")
    decision = contract.validate(("a", "b"))
    assert decision.allowed, decision.reason
    assert decision.command == "diff"
    assert decision.normalized_args == ("a", "b")

def test_diff_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("diff")
    decision = contract.validate(("a", "b", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_diff_nul_argument_is_rejected():
    contract = standard_catalog().resolve("diff")
    decision = contract.validate(("a", "b", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_jq_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("jq")
    decision = contract.validate((".",))
    assert decision.allowed, decision.reason
    assert decision.command == "jq"
    assert decision.normalized_args == (".",)

def test_jq_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("jq")
    decision = contract.validate((".", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_jq_nul_argument_is_rejected():
    contract = standard_catalog().resolve("jq")
    decision = contract.validate((".", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_sqlite3_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("sqlite3")
    decision = contract.validate(("db.sqlite",))
    assert decision.allowed, decision.reason
    assert decision.command == "sqlite3"
    assert decision.normalized_args == ("db.sqlite",)

def test_sqlite3_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("sqlite3")
    decision = contract.validate(("db.sqlite", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_sqlite3_nul_argument_is_rejected():
    contract = standard_catalog().resolve("sqlite3")
    decision = contract.validate(("db.sqlite", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_tar_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("tar")
    decision = contract.validate(("archive.tar",))
    assert decision.allowed, decision.reason
    assert decision.command == "tar"
    assert decision.normalized_args == ("archive.tar",)

def test_tar_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("tar")
    decision = contract.validate(("archive.tar", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_tar_nul_argument_is_rejected():
    contract = standard_catalog().resolve("tar")
    decision = contract.validate(("archive.tar", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_zip_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("zip")
    decision = contract.validate(("out.zip",))
    assert decision.allowed, decision.reason
    assert decision.command == "zip"
    assert decision.normalized_args == ("out.zip",)

def test_zip_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("zip")
    decision = contract.validate(("out.zip", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_zip_nul_argument_is_rejected():
    contract = standard_catalog().resolve("zip")
    decision = contract.validate(("out.zip", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_unzip_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("unzip")
    decision = contract.validate(("archive.zip",))
    assert decision.allowed, decision.reason
    assert decision.command == "unzip"
    assert decision.normalized_args == ("archive.zip",)

def test_unzip_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("unzip")
    decision = contract.validate(("archive.zip", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_unzip_nul_argument_is_rejected():
    contract = standard_catalog().resolve("unzip")
    decision = contract.validate(("archive.zip", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_curl_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("curl")
    decision = contract.validate(("https://example.invalid",))
    assert decision.allowed, decision.reason
    assert decision.command == "curl"
    assert decision.normalized_args == ("https://example.invalid",)

def test_curl_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("curl")
    decision = contract.validate(("https://example.invalid", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_curl_nul_argument_is_rejected():
    contract = standard_catalog().resolve("curl")
    decision = contract.validate(("https://example.invalid", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_wget_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("wget")
    decision = contract.validate(("https://example.invalid",))
    assert decision.allowed, decision.reason
    assert decision.command == "wget"
    assert decision.normalized_args == ("https://example.invalid",)

def test_wget_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("wget")
    decision = contract.validate(("https://example.invalid", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_wget_nul_argument_is_rejected():
    contract = standard_catalog().resolve("wget")
    decision = contract.validate(("https://example.invalid", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_psql_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("psql")
    decision = contract.validate(())
    assert decision.allowed, decision.reason
    assert decision.command == "psql"
    assert decision.normalized_args == ()

def test_psql_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("psql")
    decision = contract.validate(("--definitely-not-a-real-flag",))
    assert not decision.allowed
    assert decision.reason

def test_psql_nul_argument_is_rejected():
    contract = standard_catalog().resolve("psql")
    decision = contract.validate(("\\x00bad",))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_docker_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("docker")
    decision = contract.validate(("version",))
    assert decision.allowed, decision.reason
    assert decision.command == "docker"
    assert decision.normalized_args == ("version",)

def test_docker_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("docker")
    decision = contract.validate(("version", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_docker_nul_argument_is_rejected():
    contract = standard_catalog().resolve("docker")
    decision = contract.validate(("version", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_podman_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("podman")
    decision = contract.validate(("version",))
    assert decision.allowed, decision.reason
    assert decision.command == "podman"
    assert decision.normalized_args == ("version",)

def test_podman_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("podman")
    decision = contract.validate(("version", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_podman_nul_argument_is_rejected():
    contract = standard_catalog().resolve("podman")
    decision = contract.validate(("version", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_kubectl_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("kubectl")
    decision = contract.validate(("get", "pods"))
    assert decision.allowed, decision.reason
    assert decision.command == "kubectl"
    assert decision.normalized_args == ("get", "pods")

def test_kubectl_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("kubectl")
    decision = contract.validate(("get", "pods", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_kubectl_nul_argument_is_rejected():
    contract = standard_catalog().resolve("kubectl")
    decision = contract.validate(("get", "pods", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_helm_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("helm")
    decision = contract.validate(("template", "chart"))
    assert decision.allowed, decision.reason
    assert decision.command == "helm"
    assert decision.normalized_args == ("template", "chart")

def test_helm_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("helm")
    decision = contract.validate(("template", "chart", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_helm_nul_argument_is_rejected():
    contract = standard_catalog().resolve("helm")
    decision = contract.validate(("template", "chart", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason

def test_terraform_representative_invocation_is_accepted():
    contract = standard_catalog().resolve("terraform")
    decision = contract.validate(("validate",))
    assert decision.allowed, decision.reason
    assert decision.command == "terraform"
    assert decision.normalized_args == ("validate",)

def test_terraform_unknown_flag_is_rejected():
    contract = standard_catalog().resolve("terraform")
    decision = contract.validate(("validate", "--definitely-not-a-real-flag"))
    assert not decision.allowed
    assert decision.reason

def test_terraform_nul_argument_is_rejected():
    contract = standard_catalog().resolve("terraform")
    decision = contract.validate(("validate", "\\x00bad"))
    assert not decision.allowed
    assert "NUL" in decision.reason
