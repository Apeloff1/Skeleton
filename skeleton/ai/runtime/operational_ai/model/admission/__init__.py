"""Crash-safe, per-Unix-principal admission for native model images."""
from .contracts import (AdmissionError,AdmissionBusy,AdmissionCorrupt,
                        AdmissionUnsupported,CapacityPolicy,Reservation)
from .broker import CapacityBroker,ModelCapacityLease
__all__=['AdmissionError','AdmissionBusy','AdmissionCorrupt','AdmissionUnsupported',
         'CapacityPolicy','Reservation','CapacityBroker','ModelCapacityLease']

# Preserve the single-model concurrency interface when this package shadows
# the historic ``model/admission.py`` module in Python import resolution.
from .inference import InferenceAdmission
__all__.append("InferenceAdmission")
