"""Non-authorizing audit receipts; never confuse a recorded proposal with approval."""
from ..contracts.canonical import digest
from ..contracts.errors import ContractError

def evidence(operation: dict, decision: dict, *, authorizer: str | None=None) -> dict:
    if not isinstance(operation, dict) or not isinstance(decision, dict):
        raise ContractError('audit requires structured evidence')
    return {'operation_sha256': digest(operation), 'decision_sha256': digest(decision), 'authorizer': authorizer, 'execution_attested': False}
