"""Machine-readable no-side-effect checks: dependencies, host, permissions and memory."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import importlib.util,os,platform,stat,sys
from ...model.gguf.memory import assess_memory
from ...model.gguf.service import load_approved_manifest

@dataclass(frozen=True,slots=True)
class DoctorCheck:
    name:str
    passed:bool
    reason:str

@dataclass(frozen=True,slots=True)
class DoctorReport:
    state:str
    checks:tuple[DoctorCheck,...]
    model_sha:str|None
    os_name:str


def doctor(*,model_root:str|Path|None=None,state_dir:str|Path|None=None,
           require_gguf:bool=False)->DoctorReport:
    checks=[];model_sha=None
    checks.append(DoctorCheck('python-baseline',sys.version_info>=(3,11),sys.version.split()[0]))
    checks.append(DoctorCheck('platform-native-custody',platform.system()=='Linux',platform.system()))
    checks.append(DoctorCheck('native-llama-binding',importlib.util.find_spec('llama_cpp') is not None,
                              'optional binding; required for GGUF'))
    if state_dir is not None:
        p=Path(state_dir)
        safe=p.is_dir() and not p.is_symlink() and not p.stat().st_mode&0o077
        checks.append(DoctorCheck('private-state-directory',bool(safe),'0700 and not symlinked'))
    if model_root is not None:
        try:
            manifest=load_approved_manifest(model_root)
            model_sha=manifest.model_sha256
            mem=assess_memory(manifest)
            checks.append(DoctorCheck('model-manifest',True,'operator-provided digest-pinned shard inventory'))
            checks.append(DoctorCheck('memory-capacity',mem.accepted,mem.reason))
        except Exception as exc:
            checks.append(DoctorCheck('model-manifest',False,str(exc)[:240]))
    if not require_gguf:
        # Native JSON-checkpoint serving is available independently of llama_cpp.
        required={'python-baseline'}|({'private-state-directory'} if state_dir is not None else set())
    else:
        required={'python-baseline','platform-native-custody','native-llama-binding','model-manifest','memory-capacity'}
        if state_dir is not None:required.add('private-state-directory')
    passed=all(c.passed for c in checks if c.name in required)
    return DoctorReport('preflight-passed-not-live-tested' if passed else 'blocked',tuple(checks),model_sha,platform.system())
