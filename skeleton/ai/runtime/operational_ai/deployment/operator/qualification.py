"""No release certification from source presence, simulated models or stale CI."""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any
_SHA=re.compile(r'^[0-9a-f]{40}$')

@dataclass(frozen=True,slots=True)
class Gate:
    name:str
    head_sha:str
    conclusion:str
    evidence_id:str

    def __post_init__(self):
        if not _SHA.fullmatch(self.head_sha):raise ValueError('CI gate must bind 40-char exact head SHA')
        if not self.name or len(self.name)>128 or not self.evidence_id:
            raise ValueError('CI gate identity and evidence required')
        if self.conclusion not in {'success','failure','cancelled','skipped','pending','neutral'}:
            raise ValueError('invalid CI conclusion')

@dataclass(frozen=True,slots=True)
class ReleaseEvidence:
    source_sha:str
    native_model_smoke:dict|None
    mandatory_gates:tuple[Gate,...]
    independent_signoff:bool=False
    installed_device_verified:bool=False
    backup_restore_drill:bool=False
    training_data_rights_verified:bool=False

@dataclass(frozen=True,slots=True)
class ReleaseDecision:
    qualified:bool
    blockers:tuple[str,...]
    source_sha:str

REQUIRED=('Merge Readiness','Backend Quality','App Foundation E2E','Sealed Context Guard',
          'Workflow Input Security','Artifact Policy','Malware Gate','Repository Hygiene',
          'Secret Scanning','Dependency Review')


def release_decision(evidence:ReleaseEvidence)->ReleaseDecision:
    if not _SHA.fullmatch(evidence.source_sha):raise ValueError('release needs exact git head SHA')
    blockers=[]
    if not evidence.native_model_smoke or evidence.native_model_smoke.get('status')!='native-generation-observed':
        blockers.append('no-real-native-generation-smoke')
    names={gate.name:gate for gate in evidence.mandatory_gates}
    if len(names)!=len(evidence.mandatory_gates):blockers.append('duplicate-gate-evidence')
    for name in REQUIRED:
        gate=names.get(name)
        if gate is None:blockers.append('missing:'+name)
        elif gate.head_sha!=evidence.source_sha:blockers.append('stale:'+name)
        elif gate.conclusion!='success':blockers.append('not-success:'+name)
    if not evidence.independent_signoff:blockers.append('independent-verification-missing')
    if not evidence.installed_device_verified:blockers.append('target-device-not-qualified')
    if not evidence.backup_restore_drill:blockers.append('restore-not-demonstrated')
    if not evidence.training_data_rights_verified:blockers.append('model-data-rights-not-verified')
    return ReleaseDecision(not blockers,tuple(blockers),evidence.source_sha)
