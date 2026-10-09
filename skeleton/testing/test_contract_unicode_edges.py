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


def test_unpaired_unicode_surrogates_are_rejected_for_values_and_keys():
 import pytest
 from skeleton.contracts.canonical import CanonicalContractError
 for payload in ({"text":"\\ud800"},{"\\udc00":"text"},{"nested":[{"bad":"\\udfff"}]}):
  # Escaped literals above are intentionally converted to literal codepoints.
  text = next(iter(payload)) if len(payload)==1 else ""
  with pytest.raises(CanonicalContractError,match="Unicode surrogate"):
   canonical_json_bytes(payload)

def test_legitimate_unicode_emoji_remains_portable():
 assert canonical_json_bytes({"text":"😀"})==b'{"text":"😀"}'

def test_cyclic_and_excessively_nested_payloads_fail_closed():
 import pytest
 from skeleton.contracts.canonical import CanonicalContractError
 cycle=[]
 cycle.append(cycle)
 with pytest.raises(CanonicalContractError,match="cyclic"):
  canonical_json_bytes({"nested":cycle})
 too_deep=0
 for _ in range(66):
  too_deep=[too_deep]
 with pytest.raises(CanonicalContractError,match="depth"):
  canonical_json_bytes(too_deep)
 assert canonical_json_bytes({"a":[{"b":"value"}]})
