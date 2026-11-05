"""snapshot_plan: domain-scoped offline AI operational execution."""
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
PROFILE=read_profile("snapshot_plan")
__all__=("PROFILE",)
