"""Retain original transcript; project only a bounded suffix for the model."""
from ..contracts.errors import ContractError
from .tokenization import rough_tokens

def project(turns: list[dict], *, budget: int=8000) -> dict:
    if not isinstance(turns, list) or len(turns) > 100000 or type(budget) is not int or (budget < 64):
        raise ContractError('invalid context window')
    selected = []
    spent = 0
    for turn in reversed(turns):
        if not isinstance(turn, dict) or set(turn) != {'role', 'text', 'trust'} or turn['role'] not in {'user', 'assistant', 'tool'} or (turn['trust'] not in {'trusted', 'untrusted'}):
            raise ContractError('invalid conversation turn')
        cost = rough_tokens(turn['text'])
        if spent + cost > budget:
            break
        spent += cost
        selected.append(dict(turn))
    return {'turns': list(reversed(selected)), 'retained_count': len(turns), 'projected_count': len(selected), 'estimated_tokens': spent, 'full_history_mutated': False}
