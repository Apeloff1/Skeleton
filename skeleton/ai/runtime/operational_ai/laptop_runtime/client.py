"""No-proxy, no-redirect loopback client for the real operational AI HTTP API."""
from __future__ import annotations
import http.client
import json
import threading
from .contracts import token,safe_json,canonical,refuse,identifier,identity_hash,exact
from .operations import get
from .result_protocol import verify_turn_receipt

class LaptopClient:
    def __init__(self,*,host="127.0.0.1",port=8765,bearer,timeout=15.0,
                 expected_model_sha256=None,expected_tokenizer_sha256=None):
        if host!="127.0.0.1":
            refuse("only literal IPv4 loopback is supported by this client")
        if type(port) is not int or not 1<=port<=65535:
            refuse("invalid loopback service port")
        if type(timeout) not in (int,float) or not 1<=timeout<=120:
            refuse("invalid request timeout")
        self._host=host;self._port=port
        self._bearer=token(bearer);self._timeout=float(timeout)
        if (expected_model_sha256 is None)!=(expected_tokenizer_sha256 is None):
            refuse("model and tokenizer must be pinned together")
        self._expected=None if expected_model_sha256 is None else (
            identity_hash(expected_model_sha256),
            identity_hash(expected_tokenizer_sha256),
        )
        self._pinned=None
        self._custody=threading.RLock()

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
            # Do not let an intermediary or malicious loopback process
            # smuggle differently framed replies into the native client.
            for name in ("Content-Length","Content-Type"):
                if len(response.msg.get_all(name,[]))!=1:
                    refuse("ambiguous local native response framing")
            if (response.getheader("Transfer-Encoding") is not None
                    or response.getheader("Content-Encoding") is not None):
                refuse("unsupported local native response encoding")
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

    def _check_identity(self):
        report=self.request("identity",{})
        exact(report,("identity","release_certified"))
        if report["release_certified"] is not False:
            refuse("native service must not claim a release pass")
        principal=report["identity"]
        exact(principal,("tenant","subject","model_sha256","tokenizer_sha256"))
        record=(identifier(principal["tenant"],"tenant"),
                identifier(principal["subject"],"subject"),
                identity_hash(principal["model_sha256"]),
                identity_hash(principal["tokenizer_sha256"]))
        if self._expected is not None and record[2:]!=self._expected:
            refuse("native model differs from independently expected source")
        if self._pinned is None:self._pinned=record
        elif self._pinned!=record:refuse("native model or owner changed")
        return record

    def identity(self):
        with self._custody:
            record=self._check_identity()
            return {"tenant":record[0],"subject":record[1],
                    "model_sha256":record[2],"tokenizer_sha256":record[3],
                    "release_certified":False}

    def create(self):
        with self._custody:
            principal=self._check_identity()
            result=self.request("create",{})
            exact(result,("session_id","model_sha256"))
            identifier(result["session_id"],"session")
            if identity_hash(result["model_sha256"])!=principal[2]:
                refuse("created session belongs to another model")
            self._check_identity()
            return result

    def turn(self,session_id,request_id,prompt,*,seed=0,temperature=0.8):
        with self._custody:
            principal=self._check_identity()
            result=self.request("turn",{"session_id":session_id,
                    "request_id":request_id,"prompt":prompt,
                    "seed":seed,"temperature":temperature})
            exact(result,("receipt",))
            verified=verify_turn_receipt(result["receipt"],
                model_sha256=principal[2],tokenizer_sha256=principal[3])
            self._check_identity()
            return {"receipt":verified}

    def replay(self,session_id,request_id,prompt,*,seed=0,temperature=0.8):
        with self._custody:
            principal=self._check_identity()
            result=self.request("replay",{"session_id":session_id,
                    "request_id":request_id,"prompt":prompt,
                    "seed":seed,"temperature":temperature})
            exact(result,("replay","found"))
            if type(result["found"]) is not bool:refuse("invalid replay status")
            if result["found"]:
                verified=verify_turn_receipt(result["replay"],
                    model_sha256=principal[2],tokenizer_sha256=principal[3])
                if verified["replayed"] is not True:
                    refuse("native replay lacks committed receipt marker")
            elif result["replay"] is not None:
                refuse("missing replay cannot include native output")
            self._check_identity()
            return result

    def history(self,session_id):
        session=identifier(session_id,"session")
        with self._custody:
            self._check_identity()
            result=self.request("history",{"session_id":session})
            exact(result,("session_id","messages"))
            if result["session_id"]!=session or type(result["messages"]) is not list:
                refuse("native transcript session identity mismatch")
            if len(result["messages"])>128:
                refuse("native transcript exceeds bounded history")
            self._check_identity()
            return result
