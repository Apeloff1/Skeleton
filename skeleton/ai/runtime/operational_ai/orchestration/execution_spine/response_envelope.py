"""Versioned, bounded client receipts; model text is never an execution directive."""
from __future__ import annotations
from .contracts import canonical,Identity,SpineError,identifier,hexdigest

_SCHEMA='spine.api.receipt.v1'
def render(identity:Identity,receipt:dict)->bytes:
    if not isinstance(receipt,dict):raise SpineError('invalid receipt')
    required={'session','request_id','revision','output_sha256','model_sha256','tokenizer_sha256','replayed'}
    if not required.issubset(receipt):raise SpineError('receipt missing required fields')
    if receipt['model_sha256']!=identity.model_sha256 or receipt['tokenizer_sha256']!=identity.tokenizer_sha256:
        raise SpineError('receipt not bound to current model')
    identifier(receipt['session'],'session');identifier(receipt['request_id'],'request')
    hexdigest(receipt['output_sha256'],'output')
    if type(receipt['revision'])is not int or receipt['revision']<1:raise SpineError('invalid response revision')
    if type(receipt['replayed'])is not bool:raise SpineError('invalid replay marker')
    return canonical({'schema':_SCHEMA,'identity':identity.key(),
        'session':receipt['session'],'request_id':receipt['request_id'],
        'revision':receipt['revision'],'output_sha256':receipt['output_sha256'],
        'model_sha256':identity.model_sha256,'replayed':receipt['replayed']},ceiling=8192)
