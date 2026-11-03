"""Localization HTML escaping, duplicate locale rejection and source leases."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.jeeves.worlds.localization import (
    propose_localization, prove_localization, render_localization_html,
)
from skeleton.jeeves.worlds.world_canon import CanonError, propose


def fixture():
    world = propose(world_id="harbor", premise="An original harbor",
                    protagonist="Mara", region="Glass Bay", goal="Reach the archive")
    locale = {"tag": "fr",
              "scenes": [{"id": row["id"], "title": row["title"],
                          "narrative": row["narrative"]}
                         for row in sorted(world["scenes"], key=lambda row: row["id"])],
              "choices": [{"id": row["id"], "label": row["label"]}
                          for row in sorted(world["choices"], key=lambda row: row["id"])],
              "endings": [{"scene": row["scene"], "label": row["label"]}
                          for row in sorted(world["endings"], key=lambda row: row["scene"])]}
    return world, propose_localization(world, prompt="Reviewed original edition",
                                        locale=locale)


def test_hostile_markup_is_inert_json_and_textcontent():
    world, source = fixture()
    source["locales"][0]["scenes"][0]["title"] = "<script>alert('x')</script>"
    source["approved"] = True
    source["review_note"] = "Reviewed original content"
    page = render_localization_html(source, world)
    assert b"<script>alert" not in page
    assert b"\\u003cscript" in page
    assert b"textContent" in page
    assert b"connect-src 'none'" in page


def test_duplicate_locale_and_missing_translation_rejected():
    world, source = fixture()
    bad = deepcopy(source)
    bad["locales"].append(deepcopy(bad["locales"][0]))
    with pytest.raises(CanonError) as exc:
        prove_localization(bad, world)
    assert exc.value.code == "localization_noncanonical_locales"
    bad = deepcopy(source)
    bad["locales"][0]["endings"].clear()
    with pytest.raises(CanonError) as exc:
        prove_localization(bad, world)
    assert exc.value.code == "localization_ending_coverage"
