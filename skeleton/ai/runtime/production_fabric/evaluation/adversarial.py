"""Adversarial unsafe-path, authority and malformed-JSON probes, no side effects."""
from ..contracts.canonical import loads
from ..contracts.errors import FabricError
from ..security.pathguard import relative_path

def run() -> dict:
    probes = [lambda: loads('{"a":1,"a":2}'), lambda: loads('{"v":NaN}'), lambda: relative_path('../private'), lambda: relative_path('a\\b'), lambda: relative_path('/etc/passwd')]
    failures = []
    for index, probe in enumerate(probes):
        try:
            probe()
        except FabricError:
            continue
        failures.append(index)
    return {'status': 'pass' if not failures else 'fail', 'rejected': len(probes) - len(failures), 'total': len(probes), 'unblocked_probes': failures}
