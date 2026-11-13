"""passage_rerank: operator-bound source and model scope."""
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
PROFILE=read_profile("passage_rerank")
__all__=("PROFILE",)
