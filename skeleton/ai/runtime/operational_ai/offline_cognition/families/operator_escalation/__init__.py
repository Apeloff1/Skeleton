"""operator_escalation: guarded offline plan boundary."""
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
PROFILE=read_profile("operator_escalation")
__all__=("PROFILE",)
