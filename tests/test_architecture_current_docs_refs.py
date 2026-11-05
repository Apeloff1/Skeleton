"""docs/architecture/current/*.md must only reference modules/symbols that exist."""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "current"
REF = re.compile(r"^- `([a-z_][\w.]*):([A-Za-z_]\w*)`\s*$", re.M)
PAGES = sorted(p for p in DOCS.glob("*.md") if p.name != "README.md")


def _refs():
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        section = text.split("## References", 1)
        assert len(section) == 2, f"{page.name} has no References section"
        for mod, sym in REF.findall(section[1]):
            yield pytest.param(mod, sym, id=f"{page.stem}:{mod}:{sym}")


def test_every_page_has_references():
    assert len(PAGES) == 6
    for page in PAGES:
        tail = page.read_text(encoding="utf-8").split("## References", 1)[-1]
        assert REF.search(tail), page.name


def test_readme_links_every_page():
    readme = (DOCS / "README.md").read_text(encoding="utf-8")
    for page in PAGES:
        assert f"({page.name})" in readme, page.name


@pytest.mark.parametrize("module,symbol", list(_refs()))
def test_reference_exists(module, symbol):
    mod = importlib.import_module(module)
    assert hasattr(mod, symbol), f"{module} has no attribute {symbol}"
