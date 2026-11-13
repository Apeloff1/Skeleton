"""token_limit: domain-scoped offline AI operational execution."""
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
PROFILE=read_profile("token_limit")
__all__=("PROFILE",)
