"""Exact-origin regression for CodeQL URL-substring alerts #147 and #286."""
from __future__ import annotations

import ast
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load_helper(relative: str, name: str):
    # Load only the pure URL predicate. In particular do not execute the
    # legacy smoke script: it performs live HTTP requests in its main guard.
    path = REPO / relative
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        stmt for stmt in tree.body
        if isinstance(stmt, ast.FunctionDef) and stmt.name == name
    )
    env = {"urlsplit": urlsplit}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), env)
    return env[name]


@pytest.fixture(scope="module")
def build_predicate():
    return _load_helper(
        "backend/tests/test_final_build.py", "_trusted_build_download_url"
    )


@pytest.fixture(scope="module")
def rust_predicate():
    return _load_helper(
        "tests/legacy_root/backend_test_review_2026_05.py",
        "_trusted_rust_official_url",
    )


def test_cdn_admits_canonical_download_link(build_predicate):
    assert build_predicate("https://cdn.galaxy.studio/builds/game123/1.0/linux.zip")


@pytest.mark.parametrize("url", [
    "http://cdn.galaxy.studio/builds/game/linux.zip",
    "//cdn.galaxy.studio/builds/game/linux.zip",
    "https://cdn.galaxy.studio.attacker.test/builds/game.zip",
    "https://evil.test/?next=https://cdn.galaxy.studio/builds/game.zip",
    "https://someone@cdn.galaxy.studio/builds/game.zip",
    "https://someone:secret@cdn.galaxy.studio/builds/game.zip",
    "https://cdn.galaxy.studio:443/builds/game.zip",
    "https://cdn.galaxy.studio:444/builds/game.zip",
    "https://cdn.galaxy.studio/builds/game.zip?next=evil",
    "https://cdn.galaxy.studio/builds/game.zip#fragment",
    "https://cdn.galaxy.studio//builds/game.zip",
    "https://cdn.galaxy.studio/builds/../etc/passwd",
    "https://cdn.galaxy.studio\\@evil.test/builds/game.zip",
    "\nhttps://cdn.galaxy.studio/builds/game.zip",
    "https://cdn.galaxy.studio/builds/game.zip\r\n",
    "https://cdn.galaxy.studio",
    "",
    None,
    5,
])
def test_cdn_rejects_deceptive_noncanonical_origins(build_predicate, url):
    assert build_predicate(url) is False


@pytest.mark.parametrize("url", [
    "https://doc.rust-lang.org/book/",
    "https://rust-lang.org/learn",
    "https://www.rust-lang.org/tools/install",
])
def test_docs_allows_only_canonical_https_rust_origins(rust_predicate, url):
    assert rust_predicate(url) is True


@pytest.mark.parametrize("url", [
    "http://doc.rust-lang.org/book/",
    "https://doc.rust-lang.org.attacker.test/book/",
    "https://evil.test/docs/doc.rust-lang.org/book",
    "https://attacker@doc.rust-lang.org/book",
    "https://attacker:secret@doc.rust-lang.org/book",
    "https://doc.rust-lang.org:443/book/",
    "https://doc.rust-lang.org:5000/book/",
    "https://doc.rust-lang.org/book/#foo",
    "https://doc.rust-lang.org\\@evil.test/book/",
    "//doc.rust-lang.org/book",
    "\t\nhttps://doc.rust-lang.org/book",
    "https://doc.rust-lang.org",
    "",
    [],
])
def test_docs_denies_credentialed_or_redirected_origins(rust_predicate, url):
    assert rust_predicate(url) is False
