import pytest

from skeleton.ai.game_builder.localization import (
    LocalizedGame, MessageError, SourceString, check_placeholders, extract_strings, format_message,
    is_rtl, plural_category, text_direction, wrap_bidi,
)
from skeleton.ai.game_builder.localization.plurals import PDI, RLI

PLAN = {"title": "Forge Quest", "seed": 7, "levels": [
    {"id": "cave", "name": "Dark Cave", "description": "You have {count, plural, one {# coin} other {# coins}}."},
    {"id": "Gate 2", "name": "Gate", "objective": "Open the gate, {player}."}],
    "items": [{"slug": "sword", "name": "Sword", "damage": 4}]}


def game():
    return LocalizedGame(extract_strings(PLAN, "plan"), "en")


def test_extract_rejects_cyclic_deep_and_unbounded_structures():
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(ValueError, match="cyclic"):
        extract_strings({"choices": cyclic})
    deep = {"text": "safe"}
    for _ in range(40):
        deep = {"node": deep}
    with pytest.raises(ValueError, match="budget"):
        extract_strings(deep)
    with pytest.raises(ValueError, match="budget"):
        extract_strings({"choices": [None] * 10_001})
    with pytest.raises(ValueError, match="message bound"):
        extract_strings({"text": "a" * 4097})


def test_extract_stable_keys_and_skips_non_text():
    keys = [s.key for s in extract_strings(PLAN, "plan")]
    assert keys == sorted(keys)
    assert "plan.levels.cave.description" in keys and "plan.levels.gate_2.objective" in keys
    assert "plan.items.sword.name" in keys and "plan.title" in keys
    assert not any("seed" in k or "damage" in k for k in keys)
    rev = dict(PLAN, levels=list(reversed(PLAN["levels"])))
    assert [s.key for s in extract_strings(rev, "plan")] == keys


@pytest.mark.parametrize("loc,n,cat", [
    ("en", 1, "one"), ("en", 0, "other"), ("en", "1.0", "other"), ("fr", 0, "one"), ("fr", 1.5, "one"),
    ("ar", 0, "zero"), ("ar", 2, "two"), ("ar", 105, "few"), ("ar", 111, "many"), ("ar", 100, "other"),
    ("ru", 21, "one"), ("ru", 22, "few"), ("ru", 12, "many"), ("ru", "1.5", "other"),
    ("pl", 1, "one"), ("pl", 22, "few"), ("pl", 25, "many"), ("cs", 3, "few"), ("cy", 6, "many"),
    ("ja", 1, "other"), ("nb-NO", 1, "one"), ("xx", 1, "other"), ("he", 2, "two")])
def test_plural_categories(loc, n, cat):
    assert plural_category(loc, n) == cat


def test_format_plural_select_exact_and_escapes():
    msg = "{g, select, female {She has} other {They have}} {n, plural, =0 {nothing} one {# gem} other {# gems}} '{'x'}'"
    assert format_message(msg, {"g": "female", "n": 1}, "en") == "She has 1 gem {x}"
    assert format_message(msg, {"g": "x", "n": 0}, "en") == "They have nothing {x}"
    assert format_message(msg, {"g": "x", "n": 3}, "en") == "They have 3 gems {x}"
    with pytest.raises(MessageError):
        format_message(msg, {"g": "x"}, "en")
    with pytest.raises(MessageError):
        format_message("{n, plural, one {x}}", {"n": 1}, "en")
    with pytest.raises(MessageError):
        format_message("{n, plural, other {#}}", {"n": "3"}, "en")


def test_placeholder_checks():
    src = "Hi {player}, {n, plural, one {# coin} other {# coins}}"
    assert check_placeholders(src, "Salut {player}, {n, plural, one {# pièce} other {# pièces}}", "fr") == []
    assert any("missing placeholder {player}" in p for p in check_placeholders(src, "Salut {n, plural, other {#}}"))
    assert any("unknown" in p for p in check_placeholders(src, "{player}{n, plural, other {#}}{x}"))
    assert any("used as" in p for p in check_placeholders(src, "{player} {n}"))
    assert any("lacks ar" in p for p in check_placeholders(src, "{player} {n, plural, one {a} other {b}}", "ar"))
    assert any("does not parse" in p for p in check_placeholders(src, "{player"))


def test_rtl_and_bidi():
    assert is_rtl("ar") and is_rtl("he-IL") and is_rtl("ur") and is_rtl("pa-Arab")
    assert not is_rtl("en") and not is_rtl("az-Latn") and text_direction("fa") == "rtl"
    assert wrap_bidi("x", "ar") == f"{RLI}x{PDI}"
    assert format_message("مرحبا {p}", {"p": "Bob"}, "ar") == f"مرحبا \u2068Bob{PDI}"


def test_resolve_fallback_chain_and_stale():
    g = game()
    src = g.sources["plan.levels.gate_2.objective"]
    g.table("fr").set(src, "Ouvre la porte, {player}.", reviewed=True)
    assert g.format("plan.levels.gate_2.objective", "fr-CA", {"player": "Ada"}) == "Ouvre la porte, Ada."
    r = g.resolve("plan.levels.gate_2.objective", "fr-CA")
    assert r.locale == "fr" and r.fallback and r.direction == "ltr"
    assert g.resolve("plan.title", "fr").locale == "en"
    with pytest.raises(MessageError):
        g.table("fr").set(src, "Ouvre la porte.")
    g.update_sources([SourceString(s.key, s.text + "!" if s.key == src.key else s.text) for s in g.sources.values()])
    assert g.resolve(src.key, "fr").locale == "en"
    assert g.resolve(src.key, "fr", allow_stale=True).stale


def test_audit_missing_stale_unreviewed_orphan():
    g = game()
    src = g.sources["plan.title"]
    g.table("ar").set(src, "مهمة الحدادة", reviewed=True)
    g.table("ar").entries["old.key"] = g.table("ar").entries["plan.title"]
    issues = {(i.key, i.code) for i in g.audit(["ar"])}
    assert ("plan.items.sword.name", "missing") in issues and ("old.key", "orphan") in issues
    assert ("plan.title", "missing") not in issues
    g.update_sources([SourceString("plan.title", "Forge Quest II")] + [s for s in g.sources.values() if s.key != "plan.title"])
    assert ("plan.title", "stale") in {(i.key, i.code) for i in g.audit(["ar"])}


class FakeProvider:
    name = "fake"

    def translate(self, source, source_locale, target_locale):
        if "plural" in source.text:
            return "{oops}"  # broken output must be rejected
        return f"[{target_locale}] {source.text}"


def test_provider_fill_is_unreviewed_and_validated():
    g = game()
    filled = g.fill_missing(FakeProvider(), "de")
    assert "plan.levels.cave.description" not in filled and "plan.title" in filled
    assert g.table("de").entries["plan.title"].reviewed is False
    assert g.fill_missing(FakeProvider(), "de") == []
    with pytest.raises(TypeError):
        g.fill_missing(object(), "de")


def test_json_roundtrip():
    g = game()
    g.table("ar").set(g.sources["plan.title"], "مهمة", reviewed=True)
    g2 = LocalizedGame.from_json(g.to_json())
    assert g2.to_json() == g.to_json() and g2.table("ar").direction == "rtl"
    with pytest.raises(ValueError):
        LocalizedGame.from_json('{"schema": "nope"}')
