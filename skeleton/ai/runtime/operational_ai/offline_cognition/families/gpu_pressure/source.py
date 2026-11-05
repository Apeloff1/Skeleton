"""gpu_pressure: source — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source,extract_span
from skeleton.ai.runtime.operational_ai.offline_cognition.core.text import passages
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import identifier,refuse
def ingest(raw,*,source_id,tenant,subject,approved):
    if type(raw) is not bytes or not 1<=len(raw)<=PROFILE.byte_limit:
        refuse("source bytes exceed bounded profile")
    receipt=bind_source(raw,source_id=identifier(source_id),
                        tenant=identifier(tenant),subject=identifier(subject),approved=approved)
    if receipt.approved is not True:refuse("operator source rights missing")
    return {"source_id":receipt.source_id,"source_sha256":receipt.sha256,
            "bytes":receipt.bytes_length,"rights_independently_proved":False}
def partition(raw,*,target_words=160,overlap=24):
    if type(raw) is not bytes or not 1<=len(raw)<=PROFILE.byte_limit:
        refuse("original source bytes required")
    return passages(raw.decode("utf-8","strict"),target_words=target_words,
                    overlap=overlap,maximum_passages=PROFILE.context_limit)
def excerpt(raw,source,*,start,end,tenant,subject):
    return extract_span(raw,source,start=start,end=end,tenant=tenant,subject=subject)
