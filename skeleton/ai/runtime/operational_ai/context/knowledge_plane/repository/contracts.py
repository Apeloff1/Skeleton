"""Closed Git source indexing contract; no wildcard source walks."""
from __future__ import annotations
from dataclasses import dataclass
import re
from ..contracts import KnowledgeError,document_id

_COMMIT=re.compile(r'^[0-9a-f]{40}(?:[0-9a-f]{24})?$')
_ALLOWED_PREFIX=('skeleton/ai/','docs/ai/','machine/ai_')
_ALLOWED_EXT=('.py','.md','.json','.toml','.yaml','.yml','.ts','.tsx','.js','.mjs','.txt')
_FORBIDDEN_COMPONENT=('__pycache__','.git','.env','secrets','secret','private','credentials','id_rsa','node_modules','dist','cache')

class GitSourceError(KnowledgeError):
    """Source commit, blob, rights or path refused."""


def commit_sha(value:str)->str:
    if type(value) is not str or not _COMMIT.fullmatch(value):
        raise GitSourceError('full exact Git commit SHA required')
    return value


def git_path(value:str)->str:
    if (type(value)is not str or len(value)>512 or not value
        or not any(value.startswith(prefix) for prefix in _ALLOWED_PREFIX)
        or not value.endswith(_ALLOWED_EXT) or '\\' in value or '\x00' in value
        or any(p in ('','.','..') or p.lower() in _FORBIDDEN_COMPONENT
               or p.lower().startswith('.env') for p in value.split('/'))):
        raise GitSourceError('unsupported, hidden or sensitive AI Git source path')
    lowered=value.lower()
    if any(term in lowered for term in ('private_key','apikey','api_key','auth_token','passwords','.pem','.p12','.pfx')):
        raise GitSourceError('sensitive-named source is not admitted to model context')
    return value


def document_for_path(path:str)->str:
    import hashlib
    return document_id('git_'+hashlib.sha256(git_path(path).encode('utf8')).hexdigest()[:40])


@dataclass(frozen=True,slots=True)
class GitIndexItem:
    path:str
    expected_revision:int
    rights:str='operator-authored'

    def __post_init__(self):
        git_path(self.path)
        if type(self.expected_revision)is not int or not 0<=self.expected_revision<=512:
            raise GitSourceError('expected source revision required')
        if self.rights not in ('operator-authored','operator-licensed','public-domain'):
            raise GitSourceError('unsupported Git source rights')
