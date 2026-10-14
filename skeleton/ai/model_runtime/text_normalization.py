"""Deterministic bounded text normalization."""
from __future__ import annotations
import unicodedata
from .tokenization import TokenizerContractError

def normalize_text(text: str, form: str = "NFC") -> str:
    if not isinstance(text, str):
        raise TokenizerContractError("text must be a string")
    if form not in {"NONE", "NFC", "NFD", "NFKC", "NFKD"}:
        raise TokenizerContractError("unsupported normalization")
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise TokenizerContractError("invalid Unicode text") from exc
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if form != "NONE":
        text = unicodedata.normalize(form, text)
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
        raise TokenizerContractError("disallowed control character")
    return text
