"""Strict loopback-only AI SDK client; no implicit remote model/service fallback."""
from __future__ import annotations
import http.client
import ipaddress
import json
from ..authority.canonical import ContractViolation,canonical_bytes,load_json
from ..authority.identity import require_id


class LocalAIClient:
    def __init__(self,host:str,port:int,bearer:str,*,timeout:float=10.0):
        try:
            address=ipaddress.ip_address(host)
        except ValueError as exc:
            raise ContractViolation("client host must be a loopback IP") from exc
        if not address.is_loopback:
            raise ContractViolation("client refuses remote model services")
        if type(port) is not int or not 1<=port<=65535:
            raise ContractViolation("invalid local service port")
        if type(bearer) is not str or not 32<=len(bearer)<=512:
            raise ContractViolation("invalid caller bearer secret")
        if type(timeout) not in (float,int) or not 0<timeout<=120:
            raise ContractViolation("invalid client timeout")
        self.host=host;self.port=port;self.bearer=bearer;self.timeout=timeout

    def call(self,operation:str,payload:dict)->dict:
        require_id(operation,field="operation")
        raw=canonical_bytes({"operation":operation,"payload":payload},ceiling=65536)
        connection=http.client.HTTPConnection(self.host,self.port,timeout=self.timeout)
        try:
            connection.request("POST","/v1/operations",body=raw,headers={
                 "Authorization":"Bearer "+self.bearer,"Content-Type":"application/json",
                 "Host":f"{self.host}:{self.port}"})
            response=connection.getresponse()
            if response.getheader("Content-Length") is None:
                raise ContractViolation("local API response lacks bounded length")
            length=int(response.getheader("Content-Length"))
            if not 1<=length<=262144:
                raise ContractViolation("local API response exceeds bounded frame")
            data=response.read(length+1)
            if len(data)!=length:
                raise ContractViolation("local API response length mismatch")
            obj=load_json(data,ceiling=262144)
            if not isinstance(obj,dict) or set(obj)!={"status","result"}:
                raise ContractViolation("local API response malformed")
            if response.status!=200 or obj["status"]!="ok":
                raise ContractViolation("local AI service rejected operation")
            if not isinstance(obj["result"],dict):
                raise ContractViolation("local service result must be object")
            return obj["result"]
        finally:
            connection.close()
