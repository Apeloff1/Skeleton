"""No-live-model bootstrap policy migration, requiring independent approval."""
from __future__ import annotations
import os
from .broker import CapacityBroker
from .canonical import canonical
from .contracts import CapacityPolicy, AdmissionError
from .paths import open_file,read_file,write_file


def migrate_unused(broker:CapacityBroker,new_policy:CapacityPolicy,*,approved:bool=False)->dict:
    if approved is not True:
        raise AdmissionError('capacity policy mutation requires explicit operator authorization')
    if not isinstance(new_policy,CapacityPolicy):
        raise AdmissionError('new capacity policy must be fully validated')
    with broker._guard():
        broker._admit_policy()
        # Even a kernel-free old slot could retain an active child-process
        # ambiguity or old-policy receipt, so NEVER mutate policy after first
        # model load. Separate registries are mandatory for a real rollout.
        for index in range(broker.policy.slots):
            try:
                fd=open_file(broker._root_fd,f'model-slot-{index:02d}.lock')
            except FileNotFoundError:
                continue
            else:
                os.close(fd)
                raise AdmissionError('cannot change model policy after any model activation')
        fd=open_file(broker._root_fd,'policy.json')
        try:
            if read_file(fd)!=canonical(broker.policy.record()):
                raise AdmissionError('policy changed since migration preflight')
            write_file(fd,canonical(new_policy.record()))
        finally:
            os.close(fd)
    return {'status':'bootstrap-policy-migrated-before-first-model',
            'old':broker.policy.record(),'new':new_policy.record(),
            'warning':'reopen-new-broker-before-any-activation'}
