"""Explicit operator-only release reconciliation after verified process death.

Free kernel locks, not PID reuse or stale wall-clock timestamps, are proof an
allocation is no longer held. The release receipt is updated only on approval.
No model or queue request is retried, and no live lease is touched.
"""
from __future__ import annotations
from .broker import CapacityBroker
from .contracts import AdmissionCorrupt, AdmissionError, Reservation, integer
from .record import create_record, encode_record
from .paths import write_file


def reconcile_orphans(broker: CapacityBroker, *, approved: bool = False,
                      maximum: int = 8) -> dict:
    if approved is not True:
        raise AdmissionError('independent operator approval required for orphan reconciliation')
    integer(maximum, 'reconciliation ceiling', 1, 32)
    with broker._guard():
        broker._admit_policy()
        scanned=broker._scan(create=False)
        reviewed=[]
        fixed=[]
        try:
            for index, fd, occupied, prior in scanned:
                if prior is not None and not occupied and prior['state']=='active':
                    reviewed.append((index,fd,prior))
            if len(reviewed)>maximum:
                raise AdmissionError('orphan reconciliation batch limit exceeded')
            for index, fd, prior in reviewed:
                replacement=create_record(broker.policy,Reservation(**prior['reservation']),
                    prior['process'], index, prior['sequence'], state='released')
                write_file(fd,encode_record(replacement))
                fixed.append({'slot':index,'sequence':prior['sequence']})
        finally:
            broker._release_scan(scanned)
        return {'status':'operator-reconciled-kernel-free-slot-receipts',
                'reconciled':fixed,'count':len(fixed),
                'warning':'does-not-authorize-retrying-inference'}
