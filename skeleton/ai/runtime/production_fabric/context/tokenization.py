"""Deterministic lexical index tokenizer; not a model-specific token-count oracle."""
import re
from ..contracts.errors import ContractError
_WORD = re.compile("[^\\W_]+(?:'[^\\W_]+)?", re.UNICODE)

def terms(text: str, *, limit: int=100000) -> list[str]:
    if not isinstance(text, str) or len(text) > 1000000 or (not 1 <= limit <= 100000):
        raise ContractError('invalid lexical input')
    result = [m.group(0).casefold() for m in _WORD.finditer(text)]
    if len(result) > limit:
        raise ContractError('lexical token ceiling exceeded')
    return result

def rough_tokens(text: str) -> int:
    """Conservative local planning estimate; never assert exact tokenizer parity."""
    if not isinstance(text, str):
        raise ContractError('text required')
    return max(len(terms(text)), (len(text.encode('utf-8')) + 2) // 3)
