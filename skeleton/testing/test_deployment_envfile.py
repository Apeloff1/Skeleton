"""Dotenv parse/render/redaction and atomic 0600 writes."""

from __future__ import annotations

import os
import stat

import pytest

from skeleton.deployment.envfile import (
    MASK,
    EnvFileError,
    is_secret_key,
    load_env_file,
    parse_env_text,
    redact_env,
    redact_uri,
    render_env,
    write_env_file,
)


def test_parses_comments_blank_lines_and_export() -> None:
    text = """
# comment
export A=1
B = two
C=three # trailing comment
D=four#not-a-comment
"""
    assert parse_env_text(text) == {"A": "1", "B": "two", "C": "three", "D": "four#not-a-comment"}


def test_double_quoted_escapes_and_trailing_comment() -> None:
    parsed = parse_env_text('A="line\\nnext \\"q\\" \\$HOME \\\\ \\t"  # c')
    assert parsed["A"] == 'line\nnext "q" $HOME \\ \t'


def test_unknown_escape_is_preserved_literally() -> None:
    assert parse_env_text('A="a\\zb"')["A"] == "a\\zb"


def test_single_quoted_is_literal() -> None:
    assert parse_env_text("A='$x \\n # y'")["A"] == "$x \\n # y"


def test_interpolation_is_not_expanded() -> None:
    assert parse_env_text("A=${HOME}/x")["A"] == "${HOME}/x"


def test_later_keys_win() -> None:
    assert parse_env_text("A=1\nA=2") == {"A": "2"}


def test_empty_values() -> None:
    assert parse_env_text('A=\nB=""\nC=\'\'') == {"A": "", "B": "", "C": ""}


@pytest.mark.parametrize(
    "text,message",
    [
        ("JUSTAKEY", "expected KEY=value"),
        ("1BAD=x", "invalid variable name"),
        ('A="open', "unterminated double-quoted"),
        ("A='open", "unterminated single-quoted"),
        ('A="x" junk', "unexpected text"),
        ("A='x' junk", "unexpected text"),
    ],
)
def test_malformed_lines_report_line_numbers(text: str, message: str) -> None:
    with pytest.raises(EnvFileError, match=message) as info:
        parse_env_text("OK=1\n" + text, source="f.env")
    assert info.value.line == 2
    assert str(info.value).startswith("f.env:2:")


@pytest.mark.parametrize(
    "value",
    ["plain", "", "with space", 'qu"ote', "dollar$sign", "multi\nline", "tab\there", "back\\slash",
     "hash #x", "ünïcödé", "a=b", "*", "mongodb://u:p@h:27017/db?x=1"],
)
def test_render_parse_round_trip(value: str) -> None:
    mapping = {"KEY": value}
    assert parse_env_text(render_env(mapping)) == mapping


def test_render_keeps_order_and_header() -> None:
    text = render_env({"B": "1", "A": "2"}, header="line one\nline two")
    lines = text.splitlines()
    assert lines[:3] == ["# line one", "# line two", ""]
    assert lines[3:] == ["B=1", "A=2"]


def test_render_rejects_invalid_names() -> None:
    with pytest.raises(EnvFileError):
        render_env({"not valid": "x"})


def test_render_can_redact() -> None:
    text = render_env({"SKL_ENGINE_SERVICE_TOKEN": "s" * 40, "X": "y"}, redact=True)
    assert "s" * 40 not in text
    assert MASK in text


def test_write_env_file_is_atomic_and_private(tmp_path) -> None:
    target = tmp_path / "nested" / "skeleton.env"
    write_env_file(target, {"A": "1", "SKL_ENGINE_SERVICE_TOKEN": "t" * 40}, header="hdr")
    assert load_env_file(target) == {"A": "1", "SKL_ENGINE_SERVICE_TOKEN": "t" * 40}
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert [p.name for p in target.parent.iterdir()] == ["skeleton.env"]  # no temp leftovers


def test_write_env_file_replaces_existing(tmp_path) -> None:
    target = tmp_path / "e.env"
    target.write_text("OLD=1\n", encoding="utf-8")
    write_env_file(target, {"NEW": "2"})
    assert load_env_file(target) == {"NEW": "2"}


def test_write_env_file_cleans_temp_on_failure(tmp_path) -> None:
    with pytest.raises(EnvFileError):
        write_env_file(tmp_path / "e.env", {"bad key": "x"})
    assert list(tmp_path.iterdir()) == []


def test_load_missing_file_raises_env_file_error(tmp_path) -> None:
    with pytest.raises(EnvFileError, match="cannot read"):
        load_env_file(tmp_path / "missing.env")


@pytest.mark.parametrize("key", ["SKL_ENGINE_SERVICE_TOKEN", "OPENAI_API_KEY", "DB_PASSWORD",
                                 "SKELETON_GITHUB_CLIENT_SECRET", "aws_credential_file"])
def test_secret_keys(key: str) -> None:
    assert is_secret_key(key)


@pytest.mark.parametrize("key", ["SKL_SERVER_PORT", "SKL_MONGO_URI", "HOME"])
def test_non_secret_keys(key: str) -> None:
    assert not is_secret_key(key)


def test_redact_env_masks_secrets_and_uri_passwords() -> None:
    redacted = redact_env({
        "SKL_ENGINE_SERVICE_TOKEN": "abc",
        "EMPTY_TOKEN": "",
        "SKL_MONGO_URI": "mongodb://user:hunter2@db:27017/x",
        "PLAIN_URI": "mongodb://db:27017",
        "CUSTOM": "visible",
        "OTHER": "hidden",
    }, extra_secret_keys=["other"])
    assert redacted["SKL_ENGINE_SERVICE_TOKEN"] == MASK
    assert redacted["EMPTY_TOKEN"] == ""
    assert "hunter2" not in redacted["SKL_MONGO_URI"]
    assert redacted["SKL_MONGO_URI"].startswith("mongodb://user:")
    assert redacted["PLAIN_URI"] == "mongodb://db:27017"
    assert redacted["CUSTOM"] == "visible"
    assert redacted["OTHER"] == MASK


def test_redact_uri_variants() -> None:
    assert redact_uri("https://example.org/x") == "https://example.org/x"
    assert redact_uri("mongodb://onlyuser@h") == "mongodb://onlyuser@h"
    assert redact_uri("mongodb://u:p@h1,h2/db?rs=a") == f"mongodb://u:{MASK}@h1,h2/db?rs=a"
