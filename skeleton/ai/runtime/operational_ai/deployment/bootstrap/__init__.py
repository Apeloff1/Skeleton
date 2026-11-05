"""Explicit, local, no-clobber first-install state and secret-key provisioning."""
from .provision import ProvisionError, ProvisionReceipt, provision
__all__=['ProvisionError','ProvisionReceipt','provision']
