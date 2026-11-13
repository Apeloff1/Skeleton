"""Localization data layer for builder games.

Builds on ``skeleton.contracts.localization`` (LocaleId, LocaleFallbackPolicy)
and extends the demo runtime in ``advanced_localization_runtime`` with: string
extraction from plans/forge data, CLDR-style plurals for many languages,
plural/gender message syntax, placeholder checks, RTL handling, a pluggable
offline translation-provider Protocol, and missing/stale audits.
No UI, routes, network calls or engine export.
"""
from .catalog import (
    AuditIssue, LocaleTable, LocalizedGame, SourceString, TranslationProvider, extract_strings,
    source_hash,
)
from .messages import MessageError, check_placeholders, format_message, parse_message
from .plurals import PLURAL_CATEGORIES, is_rtl, plural_category, text_direction, wrap_bidi

__all__ = [
    "AuditIssue", "LocaleTable", "LocalizedGame", "SourceString", "TranslationProvider",
    "extract_strings", "source_hash", "MessageError", "check_placeholders", "format_message",
    "parse_message", "PLURAL_CATEGORIES", "is_rtl", "plural_category", "text_direction", "wrap_bidi",
]
