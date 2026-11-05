"""Identity-authenticated model slot records, with explicit lifecycle state."""
from __future__ import annotations
from .canonical import canonical, parse, digest
from .contracts import Reservation, AdmissionCorrupt, integer, sha256, CapacityPolicy


def create_record(policy: CapacityPolicy, reservation: Reservation,
                  principal: dict, slot: int, sequence: int, *, state: str = 'active') -> dict:
    integer(slot, 'slot', 0, policy.slots - 1)
    integer(sequence, 'sequence', 1, 2**63 - 1)
    if state not in ('active', 'released'):
        raise AdmissionCorrupt('unknown capacity receipt lifecycle')
    base = {'version': 1, 'policy_sha256': digest(policy.record()),
            'reservation': reservation.record(), 'process': principal,
            'slot': slot, 'sequence': sequence, 'state': state}
    return dict(base, receipt_sha256=digest(base))


def parse_record(raw: bytes, policy: CapacityPolicy, slot: int) -> dict:
    data = parse(raw)
    expected = {'version','policy_sha256','reservation','process','slot','sequence','state','receipt_sha256'}
    if set(data) != expected or type(data['version']) is not int or data['version'] != 1:
        raise AdmissionCorrupt('invalid capacity receipt shape')
    recorded_hash = sha256(data['receipt_sha256'],'capacity receipt')
    if digest({k:v for k,v in data.items() if k!='receipt_sha256'}) != recorded_hash:
        raise AdmissionCorrupt('model capacity receipt changed')
    if data['policy_sha256'] != digest(policy.record()) or data['slot'] != slot or type(data['slot']) is not int:
        raise AdmissionCorrupt('model capacity policy/slot mismatch')
    proc = data['process']
    if type(proc) is not dict or set(proc) != {'uid','pid','boot_id','start_tick'}:
        raise AdmissionCorrupt('malformed capacity owner process')
    integer(proc['uid'],'process UID',0,2**32-1)
    integer(proc['pid'],'process PID',1,2**31-1)
    integer(proc['start_tick'],'process start tick',1,2**63-1)
    if not isinstance(proc['boot_id'],str) or len(proc['boot_id']) != 36:
        raise AdmissionCorrupt('invalid process boot identity')
    reservation = data['reservation']
    if type(reservation) is not dict or set(reservation) != {'model_sha256','principal_sha256','manifest_sha256','reserve_bytes'}:
        raise AdmissionCorrupt('model capacity reservation is malformed')
    try:
        Reservation(**reservation)
    except TypeError as exc:
        raise AdmissionCorrupt('invalid reservation shape') from exc
    integer(data['sequence'],'capacity sequence',1,2**63-1)
    if data['state'] not in ('active','released'):
        raise AdmissionCorrupt('unknown model occupancy state')
    return data


def encode_record(value: dict) -> bytes:
    return canonical(value)
