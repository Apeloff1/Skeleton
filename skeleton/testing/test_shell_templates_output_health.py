from pathlib import Path
import sys
import pytest

from skeleton.shells.arguments import ValueConstraint
from skeleton.shells.health import inspect_policy
from skeleton.shells.output import combined_summary, render_output
from skeleton.shells.runner import ShellPolicy, ShellResult
from skeleton.shells.templates import CommandTemplate, TemplateCatalog, TemplateSlot


def test_template_substitutes_only_declared_whole_token_slots(tmp_path):
    template = CommandTemplate(
        "compile",
        "python",
        ("-m", "{module}", "{target}"),
        slots={
            "module": TemplateSlot("module", ValueConstraint(choices=frozenset({"compileall"}))),
            "target": TemplateSlot("target", ValueConstraint(pattern=r"[A-Za-z0-9_./-]+")),
        },
        allow_cwd_override=True,
    )
    command = template.build({"module": "compileall", "target": "."}, cwd=tmp_path)
    assert command.args == ("-m", "compileall", ".")


def test_template_rejects_unknown_slot_value():
    template = CommandTemplate("t", "python", ("{x}",), slots={"x": TemplateSlot("x")})
    with pytest.raises(ValueError):
        template.build({"x": "a", "y": "b"})


def test_template_rejects_invalid_slot_constraint():
    template = CommandTemplate(
        "t", "python", ("{x}",), slots={"x": TemplateSlot("x", ValueConstraint(choices=frozenset({"safe"})))}
    )
    with pytest.raises(ValueError):
        template.build({"x": "unsafe"})


def test_template_rejects_undeclared_reference():
    with pytest.raises(ValueError):
        CommandTemplate("t", "python", ("{missing}",), slots={})


def test_template_rejects_unused_slot():
    with pytest.raises(ValueError):
        CommandTemplate("t", "python", ("fixed",), slots={"x": TemplateSlot("x")})


def test_template_cwd_override_is_explicit():
    template = CommandTemplate("t", "python", (), slots={})
    with pytest.raises(ValueError):
        template.build({}, cwd="/tmp")


def test_template_catalog_default_denies_unknown():
    catalog = TemplateCatalog()
    with pytest.raises(KeyError):
        catalog.get("missing")


def test_output_view_redacts_and_tails():
    result = ShellResult("python", 0, b"prefix Bearer top-secret suffix", b"", accepted=True)
    view = render_output(result, max_chars=12, mode="tail")
    assert "top-secret" not in view.text
    assert view.truncated


def test_output_view_head_mode():
    result = ShellResult("python", 0, b"abcdefghijk", b"", accepted=True)
    view = render_output(result, max_chars=5, mode="head")
    assert view.text == "abcde"


def test_combined_summary_has_no_raw_secret():
    result = ShellResult("python", 1, b"token=abc", b"password=xyz", accepted=False)
    summary = combined_summary(result)
    rendered = repr(summary)
    assert "abc" not in rendered
    assert "xyz" not in rendered


def test_health_report_healthy_for_python_and_tmp_path(tmp_path):
    policy = ShellPolicy(executables={"python": str(Path(sys.executable).resolve())}, cwd_roots=(tmp_path,))
    report = inspect_policy(policy)
    assert report.healthy
    assert report.executable_count == 1


def test_health_report_notes_environment_inheritance(tmp_path):
    policy = ShellPolicy(
        executables={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(tmp_path,),
        allowed_env=frozenset({"LANG"}),
        inherited_env=frozenset({"LANG"}),
    )
    report = inspect_policy(policy)
    assert any(f.code == "environment_inheritance" for f in report.findings)
