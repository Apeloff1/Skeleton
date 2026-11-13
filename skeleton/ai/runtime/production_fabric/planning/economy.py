"""Atomic resource trades with integer prices and no creation of unearned value."""
from ..contracts.errors import ContractError, ConflictError

def exchange(wallet: dict[str, int], *, spend: dict[str, int], receive: dict[str, int], max_balance: int=10 ** 12) -> dict[str, int]:
    if not isinstance(wallet, dict) or not all((isinstance(v, int) and 0 <= v <= max_balance for v in wallet.values())):
        raise ContractError('invalid inventory')
    for amounts in (spend, receive):
        if not isinstance(amounts, dict) or not amounts or any((type(v) is not int or not 0 <= v <= max_balance for v in amounts.values())):
            raise ContractError('invalid trade amount')
    result = dict(wallet)
    for key, n in spend.items():
        if result.get(key, 0) < n:
            raise ConflictError('insufficient trade balance')
        result[key] -= n
    for key, n in receive.items():
        if result.get(key, 0) + n > max_balance:
            raise ContractError('balance ceiling exceeded')
        result[key] = result.get(key, 0) + n
    return result
