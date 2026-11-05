"""No-proxy, no-redirect loopback client for the real operational AI HTTP API."""
from __future__ import annotations
import http.client
import json
from .contracts import token,safe_json,canonical,refuse
from .operations import get

class LaptopClient:
    def __init__(self,*,host="127.0.0.1",port=8765,bearer,timeout=15.0):
        if host!="127.0.0.1":
            refuse("only literal IPv4 loopback is supported by this client")
        if type(port) is not int or not 1<=port<=65535:
            refuse("invalid loopback service port")
        if type(timeout) not in (int,float) or not 1<=timeout<=120:
            refuse("invalid request timeout")
        self._host=host;self._port=port
        self._bearer=token(bearer);self._timeout=float(timeout)

    @property
    def address(self):
        return (self._host,self._port)

    def request(self,operation,payload):
        get(operation)
        if type(payload) is not dict:
            refuse("client payload must be object")
        body=canonical({"operation":operation,"payload":payload},ceiling=65536)
        conn=http.client.HTTPConnection(self._host,self._port,timeout=self._timeout)
        try:
            conn.request("POST","/v1/operations",body=body,
                         headers={"Content-Type":"application/json",
                                  "Authorization":"Bearer "+self._bearer,
                                  "Accept":"application/json",
                                  "Host":f"{self._host}:{self._port}"})
            response=conn.getresponse()
            if response.status!=200:
                refuse("local AI request was not accepted")
            content_length=response.getheader("Content-Length")
            if content_length is None or not content_length.isdecimal() or not 0<int(content_length)<=262144:
                refuse("bounded response content length required")
            if response.getheader("Content-Type","").split(";")[0]!="application/json":
                refuse("unexpected response media type")
            raw=response.read(262145)
            if len(raw)!=int(content_length):
                refuse("response framing mismatch")
            envelope=safe_json(raw,ceiling=262144)
            if type(envelope) is not dict or set(envelope)!={"status","result"}:
                refuse("unexpected response envelope")
            if envelope["status"]!="ok" or type(envelope["result"]) is not dict:
                refuse("local AI operation failed")
            return envelope["result"]
        finally:
            conn.close()

    def create(self):
        return self.request("create",{})

    def turn(self,session_id,request_id,prompt,*,seed=0,temperature=0.8):
        return self.request("turn",{"session_id":session_id,
                "request_id":request_id,"prompt":prompt,
                "seed":seed,"temperature":temperature})

    def replay(self,session_id,request_id,prompt,*,seed=0,temperature=0.8):
        return self.request("replay",{"session_id":session_id,
                "request_id":request_id,"prompt":prompt,
                "seed":seed,"temperature":temperature})

    def history(self,session_id):
        return self.request("history",{"session_id":session_id})
