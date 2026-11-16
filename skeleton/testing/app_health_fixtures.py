"""Complete source-test health evidence; never contacts a live service."""
from skeleton.app.health import ProbeResult, readiness_targets
from skeleton.app.assembly import load_manifest


def fixture_probes(*,manifest=None,full=False,public_url_overrides=None,ok=True,**_):
    return tuple(ProbeResult(role,url,ok,200 if ok else 503,"fixture")
                 for role,url in readiness_targets(manifest or load_manifest(),full=full,
                     public_url_overrides=public_url_overrides).items())
