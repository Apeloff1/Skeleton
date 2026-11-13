"""review_ready: independent-review quality and evidence boundary."""
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
PROFILE=read_profile("review_ready")
__all__=("PROFILE",)
