"""Composed admission pipeline: traffic class + concurrency + degradation."""
from enum import Enum
class Admission(str,Enum): ACCEPT="accept"; SHED="shed"; READ_ONLY="read_only"
def decide(*,background_allowed:bool, read_only:bool, active:int, limit:int, background:bool)->Admission:
    if active < 0 or limit <= 0: raise ValueError("invalid concurrency bounds")
    if read_only: return Admission.READ_ONLY
    if background and not background_allowed: return Admission.SHED
    if active>=limit: return Admission.SHED
    return Admission.ACCEPT
