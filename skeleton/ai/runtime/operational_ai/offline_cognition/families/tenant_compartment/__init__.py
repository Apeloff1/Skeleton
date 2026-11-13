"""tenant_compartment: domain-scoped offline AI operational execution."""
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
PROFILE=read_profile("tenant_compartment")
__all__=("PROFILE",)
