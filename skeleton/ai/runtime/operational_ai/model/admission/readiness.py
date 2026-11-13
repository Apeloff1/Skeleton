"""Minimal provenance-only gate for model workers and independent operators."""
from __future__ import annotations
from .broker import CapacityBroker, ModelCapacityLease
from .contracts import AdmissionCorrupt


def inspect_lease(lease:ModelCapacityLease,backend)->dict:
    live=lease.assert_live()
    pinned=lease._entry['reservation']
    if (getattr(backend,'model_digest',None)!=pinned['model_sha256']
        or not isinstance(getattr(backend,'tokenizer_digest',None),str)):
        raise AdmissionCorrupt('observed worker model differs from reserved checkpoint')
    return {'status':'model-occupancy-verified-not-native-inference-proven',
            'model_sha256':pinned['model_sha256'],
            'manifest_sha256':pinned['manifest_sha256'],
            'principal_sha256':pinned['principal_sha256'],
            'slot':live['slot'],'sequence':live['sequence']}
