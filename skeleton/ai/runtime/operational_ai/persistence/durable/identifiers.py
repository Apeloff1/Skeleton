"""Tenant-safe, log-safe operation identifiers; never concatenated into SQL."""
from __future__ import annotations
import re
from .database import DurableError
VALID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')

def valid_id(value:object,name:str='id')->str:
    if not isinstance(value,str) or not VALID.fullmatch(value):
        raise DurableError(f'invalid {name}')
    return value

def scope(tenant:str,owner:str,operation:str)->tuple[str,str,str]:
    return(valid_id(tenant,'tenant'),valid_id(owner,'owner'),valid_id(operation,'operation'))
