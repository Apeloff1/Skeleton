"""gpu_pressure: domain-scoped offline AI operational execution."""
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
PROFILE=read_profile("gpu_pressure")
__all__=("PROFILE",)
