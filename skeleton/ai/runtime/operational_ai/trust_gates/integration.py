"""Opt-in real-service preflight, not an inference/mock implementation."""
from .engine import validate

def preflight_turn(*,actor,request_id,seed,temperature,max_output_tokens,context_window,
                   queue_depth,queue_ceiling,now_ns,deadline_ns):
    return (
        validate("actor",{"tenant":actor.tenant,"user":actor.user,
              "request_id":request_id,"model_sha":actor.model_digest,
              "tokenizer_sha":actor.tokenizer_digest,"scope":actor.tenant+":"+actor.user,
              "rights":["inference"]}),
        validate("sampling",{"request_id":request_id,"temperature":temperature,"top_p":1.0,
              "max_output":max_output_tokens,"context_window":context_window,
              "seed":seed,"repetition_penalty":1.0}),
        validate("admission",{"tenant":actor.tenant,"deadline_ns":deadline_ns,
              "now_ns":now_ns,"queue_depth":queue_depth,"queue_ceiling":queue_ceiling,
              "requested_tokens":max_output_tokens,"token_ceiling":context_window}),
    )
