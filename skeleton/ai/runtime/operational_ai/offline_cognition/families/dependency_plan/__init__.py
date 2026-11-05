"""dependency_plan: guarded offline plan boundary."""
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
PROFILE=read_profile("dependency_plan")
__all__=("PROFILE",)
