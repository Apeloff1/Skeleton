"""Immutable protocol advertisement for background scheduling."""
from __future__ import annotations
VERSION='skeleton.ai.native-flight-worker.v1'

def capabilities()->dict:
    return {'schema':VERSION,'mode':'automatic-single-backend',
            'native_model_fallback':'refused','concurrent_model_calls':1,
            'lease_recovery':'operator-only','unsafe_reexecution':'held',
            'network':'loopback-bearer','remote_provider':'not-available',
            'model_quality':'not-certified'}
