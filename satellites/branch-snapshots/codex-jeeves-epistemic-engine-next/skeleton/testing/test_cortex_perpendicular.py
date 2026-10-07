"""Perpendicular cut — era alias, like-title bind, seven axes, laws."""
from __future__ import annotations

from urllib.parse import urlparse

from skeleton.cortex.era_bind import HOUSE_ERA, house_era, resolve
from skeleton.cortex.laws import LawError, check
from skeleton.cortex.perpendicular import AXES, cut
from skeleton.cortex.refs import lookup
from skeleton.forge.eras import compile_era, era_pack
from skeleton.testing.test_cortex_deck import _Dummy


def test_house_era_aliases_cozy_and_soulslike():
    assert house_era("cozy") == "cozy_wholesome"
    assert house_era("soulslike") == "soulslike"
    assert house_era("extraction") == "extraction_now"
    assert "cozy" in HOUSE_ERA


def test_era_pack_accepts_ref_era_cozy():
    pack = era_pack("cozy")
    assert pack["era"] == "cozy_wholesome"
    compiled = compile_era("cozy")
    assert compiled["era"] == "cozy_wholesome"
    assert compiled["primary_dps"] > 0


def test_resolve_like_elden_ring_is_soulslike_pointer():
    card = resolve("like Elden Ring")
    assert card["hit"] == 1
    assert card["title"] == "Elden Ring"
    assert card["era"] == "soulslike"
    assert card["pack_era"] == "soulslike"
    assert card["stored_prose"] == 0
    assert card["citation"]
    steam_host = (urlparse(card.get("url") or "").hostname or "").lower()
    assert steam_host == "store.steampowered.com" or steam_host.endswith(
        ".store.steampowered.com"
    )


def test_resolve_stardew_is_cozy_wholesome():
    card = resolve("like Stardew Valley")
    assert card["title"] == "Stardew Valley"
    assert card["era"] == "cozy_wholesome"
    assert card["pack"]["era"] == "cozy_wholesome"


def test_cut_seven_axes_on_dummy():
    neo = _Dummy()
    card = cut(neo, "like Elden Ring", rounds=2)
    assert card["kind"] == "perpendicular"
    assert set(card["axes"]) == set(AXES)
    assert card["hit"] == 1
    assert card["era"] == "soulslike"
    assert card["stored_prose"] == 0
    assert card["law"] == "ok"
    assert card["improved"] == 1
    assert card["G"] >= 1.0
    assert card["citation"]
    assert lookup("Elden Ring")["appid"] == 1245620


def test_cut_without_like_does_not_ascend():
    neo = _Dummy()
    card = cut(neo, "plan tensor ttk lattice")
    assert card["improved"] == 0
    assert card["axes"]["ascend"]["ok"] == 0
    assert card["stored_prose"] == 0


def test_laws_still_reject_prose_and_secrets():
    try:
        check({"description": "a copied blurb"})
        assert False, "prose must raise"
    except LawError as exc:
        assert exc.law == "no-third-party-prose"
    try:
        check({"pat": "must-not-store"})
        assert False, "secrets must raise"
    except LawError as exc:
        assert exc.law == "no-secrets"
