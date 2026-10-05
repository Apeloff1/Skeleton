from __future__ import annotations
import unicodedata
from skeleton.contracts.canonical import canonical_json_bytes

def test_unicode_is_utf8_preserved_not_ascii_escaped():
 raw=canonical_json_bytes({"text":"Ω雪🙂"})
 assert "Ω雪🙂".encode() in raw
 assert b"\\u03a9" not in raw

def test_unicode_normalization_is_not_silently_collapsed():
 composed="é";decomposed=unicodedata.normalize("NFD",composed)
 assert composed!=decomposed
 assert canonical_json_bytes({"text":composed})!=canonical_json_bytes({"text":decomposed})
