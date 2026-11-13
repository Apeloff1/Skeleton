"""Read-only health sampling from underlying native model and durable spine."""
from ..core.errors import Integrity

def inspect(spine,backend):
    if not callable(getattr(backend,'health',None)):raise Integrity('no native health evidence')
    h=backend.health()
    if h.get('model_sha256')!=spine.identity.model_sha256:raise Integrity('health model changed')
    if h.get('tokenizer_sha256')!=spine.identity.tokenizer_sha256:raise Integrity('health tokenizer changed')
    return {'model':h.get('status'),'spine':spine.health(),
            'release_accepted':False,'schema':'agent.health-observation.v1'}
