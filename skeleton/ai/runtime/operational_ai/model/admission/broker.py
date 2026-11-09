"""Process-shared, kernel-fenced model RAM reservation broker.

A slot's flock remains held for the entire model lifetime, including the
inference child when pass_fds is used. The metadata is observational: losing a
kernel lock is what releases capacity, not a PID guess or wall-clock timeout.
Each claim serializes against the global registry and sums ACTIVE allocations.
"""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import threading
import time
from typing import Iterator
from .contracts import (AdmissionError, AdmissionBusy, AdmissionCorrupt,
                        CapacityPolicy, Reservation)
from .canonical import canonical, parse
from .paths import (verified_dir, create_default_root, open_file, read_file,
                    write_file)
from .record import create_record, parse_record, encode_record
from .proc import current_identity


class ModelCapacityLease:
    """Own the exclusive kernel lock until **all** native workers exit."""

    def __init__(self, broker: 'CapacityBroker', file_fd: int,
                 entry: dict, slot: int, proof: dict):
        self._broker = broker
        self._fd = file_fd
        self._entry = entry
        self.slot = slot
        self.proof = proof
        self._owner_pid = os.getpid()
        self._closed = False
        self._lock = threading.Lock()

    @property
    def fd(self) -> int:
        if self._closed or self._owner_pid != os.getpid():
            raise AdmissionError('capacity lease is no longer owned')
        return self._fd

    @property
    def active(self) -> bool:
        return not self._closed and self._owner_pid == os.getpid()

    def assert_live(self) -> dict:
        """Verify the original kernel-held lease and exact private receipt."""
        if not self.active:
            raise AdmissionError('model admission ownership was released')
        with self._broker._guard():
            stored = parse_record(read_file(self._fd), self._broker.policy, self.slot)
            if stored != self._entry or stored['state'] != 'active':
                raise AdmissionCorrupt('admitted model custody has changed')
            # Inspect a separate open description: a holder must remain busy.
            name = f'model-slot-{self.slot:02d}.lock'
            other = open_file(self._broker._root_fd, name)
            try:
                try:
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    fcntl.flock(other, fcntl.LOCK_UN)
                    raise AdmissionCorrupt('model slot kernel fence was lost')
            finally:
                os.close(other)
            return {'status':'kernel-slot-held','slot':self.slot,
                    'model_sha256':self._entry['reservation']['model_sha256'],
                    'sequence':self._entry['sequence']}

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._owner_pid != os.getpid():
                # After fork the child must never write the parent's receipt.
                os.close(self._fd)
                return
            try:
                with self._broker._guard():
                    raw = read_file(self._fd)
                    if not raw or parse_record(raw, self._broker.policy, self.slot) != self._entry:
                        raise AdmissionCorrupt('model slot changed during live occupancy')
                    released = create_record(
                        self._broker.policy, Reservation(**self._entry['reservation']),
                        self._entry['process'], self.slot, self._entry['sequence'],
                        state='released')
                    write_file(self._fd, encode_record(released))
            finally:
                # A failed custody check leaves invalid metadata to block future
                # claims, but must not strand a successful kernel release.
                # close(), not LOCK_UN: an isolated inference child may hold
                # the inherited open-file description. Explicit LOCK_UN would
                # revoke its kernel fence even while native code still runs.
                os.close(self._fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class CapacityBroker:
    """One Unix principal, a bounded number of model slots, and a hard budget."""

    def __init__(self, root: Path | str | None = None,
                 policy: CapacityPolicy | None = None):
        if not hasattr(fcntl, 'flock'):
            raise AdmissionError('kernel shared model locks unavailable')
        self.policy = policy if policy is not None else CapacityPolicy()
        if not isinstance(self.policy, CapacityPolicy):
            raise AdmissionError('invalid model policy')
        self.root = Path(root) if root is not None else create_default_root()
        self._root_fd = verified_dir(self.root)
        self._admin_fd = None
        self._mutex = threading.RLock()
        self._closed = False
        try:
            self._admin_fd = open_file(self._root_fd, 'admin.lock', create=True)
            with self._guard():
                self._admit_policy()
        except BaseException:
            self.close()
            raise

    def _admit_policy(self) -> None:
        try:
            fd = open_file(self._root_fd, 'policy.json', create=False)
        except FileNotFoundError:
            # First-writer initialization runs under the administrative lock.
            fd = open_file(self._root_fd, 'policy.json', create=True)
            try:
                if read_file(fd):
                    raise AdmissionCorrupt('unexpected first-use capacity policy')
                write_file(fd, canonical(self.policy.record()))
            finally:
                os.close(fd)
            return
        try:
            stored = CapacityPolicy.parse(parse(read_file(fd)))
            if stored != self.policy:
                raise AdmissionCorrupt('model capacity policy drift requires operator migration')
        finally:
            os.close(fd)

    @contextmanager
    def _guard(self, *, deadline_ms: int = 10_000) -> Iterator[None]:
        if self._closed or self._admin_fd is None:
            raise AdmissionError('model broker is already closed')
        with self._mutex:
            until = time.monotonic_ns() + deadline_ms * 1_000_000
            while True:
                try:
                    fcntl.flock(self._admin_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic_ns() >= until:
                        raise AdmissionBusy('capacity registry is administratively busy') from exc
                    time.sleep(.01)
            try:
                yield
            finally:
                fcntl.flock(self._admin_fd, fcntl.LOCK_UN)

    def _scan(self, *, create: bool) -> list[tuple[int,int,bool,dict | None]]:
        """Return fd, occupied state, validated record; free slot locks held."""
        result = []
        try:
            for slot in range(self.policy.slots):
                name = f'model-slot-{slot:02d}.lock'
                try:
                    fd = open_file(self._root_fd, name, create=create)
                except FileNotFoundError:
                    result.append((slot, -1, False, None))
                    continue
                try:
                    occupied = False
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        occupied = True
                    raw = read_file(fd)
                    entry = parse_record(raw, self.policy, slot) if raw else None
                    if occupied and (entry is None or entry['state'] != 'active'):
                        raise AdmissionCorrupt('occupied model slot has no active ownership receipt')
                    # If free, an old active record means the owner died. A
                    # kernel lock being available proves the process *holding*
                    # the allocation is gone, even if the old PID was reused.
                    result.append((slot, fd, occupied, entry))
                except BaseException:
                    os.close(fd)
                    raise
            return result
        except BaseException:
            self._release_scan(result)
            raise

    @staticmethod
    def _release_scan(scanned: list[tuple[int,int,bool,dict | None]], *,
                      keep_fd: int | None = None) -> None:
        for _, fd, occupied, _ in scanned:
            if fd < 0 or fd == keep_fd:
                continue
            if not occupied:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def inspect(self) -> dict:
        """No state mutation, PID liveness guessing, or self-certification."""
        with self._guard():
            self._admit_policy()
            slots = self._scan(create=False)
            try:
                active = []
                orphaned = []
                for index, _, occupied, entry in slots:
                    if occupied and entry:
                        active.append({'slot': index, 'reserve_bytes': entry['reservation']['reserve_bytes'],
                            'model_sha256': entry['reservation']['model_sha256'],
                            'principal_sha256': entry['reservation']['principal_sha256'],
                            'pid': entry['process']['pid'], 'sequence': entry['sequence']})
                    elif entry and entry['state'] == 'active':
                        orphaned.append(index)
                committed = sum(x['reserve_bytes'] for x in active)
                if committed > self.policy.budget_bytes:
                    raise AdmissionCorrupt('live model occupancy exceeds capacity budget')
                return {'status': 'kernel-lock-verified-not-oom-certification',
                    'policy': self.policy.record(), 'active': active, 'orphaned_slots': orphaned,
                    'remaining_bytes': self.policy.budget_bytes - committed,
                    'occupied_slots': len(active), 'free_slots': self.policy.slots - len(active)}
            finally:
                self._release_scan(slots)

    def acquire(self, reservation: Reservation, *,
                check_headroom: bool = True) -> ModelCapacityLease:
        """Reserve capacity before loading any native model or subprocess."""
        if not isinstance(reservation, Reservation):
            raise AdmissionError('fully pinned model resource reservation required')
        with self._guard():
            self._admit_policy()
            slots = self._scan(create=True)
            keep_fd = None
            try:
                active = [entry for _,_,occupied,entry in slots if occupied and entry]
                used = sum(entry['reservation']['reserve_bytes'] for entry in active)
                if used > self.policy.budget_bytes:
                    raise AdmissionCorrupt('live model budget overcommitted')
                if used + reservation.reserve_bytes > self.policy.budget_bytes:
                    raise AdmissionBusy('aggregate model memory budget exhausted')
                vacant = next(((index,fd,entry) for index,fd,occupied,entry in slots
                               if not occupied and fd >= 0), None)
                if vacant is None:
                    raise AdmissionBusy('no independent model activation slot available')
                if check_headroom:
                    from .headroom import check
                    pressure = check(self.policy, reservation)
                else:
                    # Private test-only entry point remains explicit and cannot
                    # be used by the production startup, which never disables it.
                    pressure = {'status': 'headroom-not-measured-test-only'}
                index, fd, old = vacant
                sequence = old['sequence'] + 1 if old else 1
                principal = current_identity()
                entry = create_record(self.policy,reservation,principal,index,sequence)
                write_file(fd,encode_record(entry))
                keep_fd = fd
                return ModelCapacityLease(self,fd,entry,index,pressure)
            finally:
                self._release_scan(slots,keep_fd=keep_fd)

    def close(self) -> None:
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            if self._admin_fd is not None:
                os.close(self._admin_fd)
                self._admin_fd = None
            os.close(self._root_fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
