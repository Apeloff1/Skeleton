"""CLDR cardinal plural categories and right-to-left helpers.

Rules follow CLDR cardinal plural rules for integer and decimal operands
(n, i, v, f) for the listed language families. Unknown languages fall back to
the "other"-only rule rather than guessing.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

PLURAL_CATEGORIES = ("zero", "one", "two", "few", "many", "other")
_RTL_LANGS = frozenset({"ar", "he", "fa", "ur", "ps", "sd", "yi", "dv", "ug", "ckb"})
_RTL_SCRIPTS = frozenset({"Arab", "Hebr", "Thaa", "Syrc", "Nkoo", "Adlm"})
LRI, RLI, FSI, PDI = "\u2066", "\u2067", "\u2068", "\u2069"


def _operands(n: int | float | Decimal | str) -> tuple[Decimal, int, int, int]:
    d = Decimal(str(n)).copy_abs()
    if not d.is_finite():
        raise ValueError("plural operand must be finite")
    s = format(d, "f")
    frac = s.split(".", 1)[1] if "." in s else ""
    return d, int(d), len(frac), int(frac) if frac else 0


def _en(n, i, v, f): return "one" if i == 1 and v == 0 else "other"
def _fr(n, i, v, f): return "one" if i in (0, 1) else ("many" if v == 0 and i != 0 and i % 1_000_000 == 0 else "other")
def _none(n, i, v, f): return "other"


def _ar(n, i, v, f):
    if v:
        return "other"
    m = i % 100
    return ("zero" if i == 0 else "one" if i == 1 else "two" if i == 2
            else "few" if 3 <= m <= 10 else "many" if 11 <= m <= 99 else "other")


def _he(n, i, v, f):
    if i == 1 and v == 0:
        return "one"
    return "two" if i == 2 and v == 0 else "other"


def _slavic_east(n, i, v, f):  # ru, uk, be
    if v:
        return "other"
    m10, m100 = i % 10, i % 100
    if m10 == 1 and m100 != 11:
        return "one"
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return "few"
    return "many"


def _pl(n, i, v, f):
    if v:
        return "other"
    if i == 1:
        return "one"
    m10, m100 = i % 10, i % 100
    return "few" if 2 <= m10 <= 4 and not 12 <= m100 <= 14 else "many"


def _cs(n, i, v, f):  # cs, sk
    if v:
        return "many"
    return "one" if i == 1 else "few" if 2 <= i <= 4 else "other"


def _ga(n, i, v, f):
    if n != i or v:
        return "other"
    return "one" if i == 1 else "two" if i == 2 else "few" if 3 <= i <= 6 else "many" if 7 <= i <= 10 else "other"


def _cy(n, i, v, f):
    if v:
        return "other"
    return {0: "zero", 1: "one", 2: "two", 3: "few", 6: "many"}.get(i, "other")


def _pt(n, i, v, f): return "one" if i in (0, 1) else "other"
def _hi(n, i, v, f): return "one" if i == 0 or n == 1 else "other"


_RULES: dict[str, Callable[..., str]] = {
    **dict.fromkeys(("en", "de", "nl", "sv", "nb", "nn", "no", "da", "fi", "et", "it", "es", "ca",
                     "el", "hu", "tr", "bg"), _en),
    "fr": _fr, "pt": _pt, "hi": _hi, "bn": _hi, "fa": _hi,
    **dict.fromkeys(("ja", "zh", "ko", "th", "vi", "id", "ms", "yue"), _none),
    "ar": _ar, "he": _he, "iw": _he,
    **dict.fromkeys(("ru", "uk", "be"), _slavic_east), "pl": _pl, "cs": _cs, "sk": _cs,
    "ga": _ga, "cy": _cy,
}


def _language(locale: str) -> str:
    return locale.replace("_", "-").split("-", 1)[0].lower()


def plural_category(locale: str, n: int | float | Decimal | str) -> str:
    nn, i, v, f = _operands(n)
    return _RULES.get(_language(locale), _none)(nn, i, v, f)


def categories_for(locale: str) -> frozenset[str]:
    """Categories a translation must cover (probed over 0..1000 and decimals; rare
    large-number forms such as French "many" for millions fall back to "other")."""
    rule = _RULES.get(_language(locale), _none)
    out = {rule(*_operands(k)) for k in range(0, 1_001)}
    out |= {rule(*_operands(x)) for x in ("0.5", "1.5")}
    return frozenset(out)


def is_rtl(locale: str) -> bool:
    parts = locale.replace("_", "-").split("-")
    if any(len(p) == 4 and p.title() in _RTL_SCRIPTS for p in parts[1:]):
        return True
    if any(len(p) == 4 and p.isalpha() for p in parts[1:]):
        return False  # explicit non-RTL script, e.g. az-Latn
    return parts[0].lower() in _RTL_LANGS


def text_direction(locale: str) -> str:
    return "rtl" if is_rtl(locale) else "ltr"


def wrap_bidi(value: str, locale: str | None = None) -> str:
    """Isolate an interpolated value so it can't reorder surrounding text (UAX #9)."""
    opener = FSI if locale is None else (RLI if is_rtl(locale) else LRI)
    return f"{opener}{value}{PDI}"
