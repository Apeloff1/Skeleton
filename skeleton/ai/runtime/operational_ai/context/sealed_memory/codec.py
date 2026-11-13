"""AEAD authenticated associated data binds every memory write to source and revision."""
from __future__ import annotations
from hashlib import sha256
import json,os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .keys import KeyMaterial,MemoryKeyError


def aad(tenant:str,user:str,model:str,source_id:str,revision:int,source_sha:str,epoch:int)->bytes:
    return json.dumps([tenant,user,model,source_id,revision,source_sha,epoch],
                      ensure_ascii=False,separators=(',',':')).encode('utf-8')


def seal(plaintext:bytes,key:bytes,associated_data:bytes)->tuple[bytes,bytes]:
    if not isinstance(plaintext,bytes) or len(plaintext)>262144:
        raise MemoryKeyError('plaintext record exceeds encryption bound')
    if not isinstance(key,bytes) or len(key)!=32:raise MemoryKeyError('invalid memory encryption key')
    nonce=os.urandom(12)
    return nonce,AESGCM(key).encrypt(nonce,plaintext,associated_data)


def open_sealed(nonce:bytes,ciphertext:bytes,key:bytes,associated_data:bytes)->bytes:
    if not isinstance(nonce,bytes) or len(nonce)!=12 or len(ciphertext)>262160:
        raise MemoryKeyError('malformed sealed memory record')
    try:return AESGCM(key).decrypt(nonce,ciphertext,associated_data)
    except Exception as exc:raise MemoryKeyError('memory authentication failed; no partial plaintext') from exc
