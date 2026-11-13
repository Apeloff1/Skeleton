"""Fail-closed operator preflight and release evidence for offline AI."""
from .doctor import doctor,DoctorReport
from .qualification import Gate,ReleaseEvidence,release_decision
from .startup import activate_gguf_operator,Activation
__all__=['doctor','DoctorReport','Gate','ReleaseEvidence','release_decision','activate_gguf_operator','Activation']
