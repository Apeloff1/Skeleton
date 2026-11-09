"""Scoped connector definition/session/result contracts for VOL-161."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class ConnectorError(ValueError):pass
class Scope(str,Enum): READ="read";WRITE="write"
@dataclass(frozen=True,slots=True)
class ConnectorDefinition:
 connector_id:str;config_schema_digest:str;allowed_scopes:frozenset[Scope];page_limit:int;rate_limit:int
 def __post_init__(self):
  if not _ID.fullmatch(self.connector_id) or not _SHA.fullmatch(self.config_schema_digest):raise ConnectorError("invalid connector definition")
  if not self.allowed_scopes or self.page_limit<1 or self.rate_limit<1:raise ConnectorError("bounded connector limits required")
@dataclass(frozen=True,slots=True)
class ConnectorSession:
 session_id:str;connector_id:str;granted_scopes:frozenset[Scope];credential_ref:str
 def __post_init__(self):
  if not _ID.fullmatch(self.session_id) or not _ID.fullmatch(self.connector_id):raise ConnectorError("invalid session")
  if not self.credential_ref.startswith("secret://"):raise ConnectorError("credential must remain an opaque reference")
@dataclass(frozen=True,slots=True)
class ConnectorResult:
 session_id:str;items:tuple[object,...];next_cursor:str|None;error_code:str|None=None
def open_session(definition,session):
 if session.connector_id!=definition.connector_id or not session.granted_scopes<=definition.allowed_scopes:raise ConnectorError("scope/connector mismatch")
 return session
def validate_page(definition,result):
 if len(result.items)>definition.page_limit:raise ConnectorError("page limit exceeded")
 if result.error_code and result.items:raise ConnectorError("error result cannot contain data")
 return True
