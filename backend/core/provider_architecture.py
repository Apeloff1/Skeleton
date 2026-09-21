"""Backend compatibility exports for the shared provider construction contract.

Repository-wide provider acknowledgement is owned by
`skeleton.provider_contract`. Backend code imports this historical module name
for compatibility, but there is only one implementation of receipt validation.
"""

from skeleton.provider_contract import (
    ProviderArchitectureError,
    ProviderArchitectureReceipt,
    load_provider_architecture,
    locate_contract_root,
)

__all__ = [
    "ProviderArchitectureError",
    "ProviderArchitectureReceipt",
    "load_provider_architecture",
    "locate_contract_root",
]
