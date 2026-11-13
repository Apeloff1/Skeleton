"""Explicit live model qualification: no fixture or static inventory credit."""
from __future__ import annotations
from .contracts import DaemonHeld

def require_live_probe(report:dict)->dict:
    if not isinstance(report,dict):raise DaemonHeld('native probe report missing')
    if (report.get('status')!='verified-native-generation' or
        report.get('model_calls')!=1 or
        type(report.get('generated_tokens'))is not int or
        report['generated_tokens']<1 or
        report.get('fixture') is not False):
        raise DaemonHeld('live native generation evidence required')
    model=report.get('model_sha256')
    if not isinstance(model,str) or len(model)!=64 or any(c not in '0123456789abcdef' for c in model):
        raise DaemonHeld('native model digest required')
    return {'status':'live-generation-evidence-present','model_sha256':model,
            'claim':'probe-only-not-release-certification'}
