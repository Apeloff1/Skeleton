"""No-redirect, literal-loopback JSON client for the private native API."""
from __future__ import annotations
from hashlib import sha256
import http.client
import json
from ...authority.canonical import ContractViolation,canonical_bytes


class FlightClientError(RuntimeError):
    pass


class FlightClient:
    def __init__(self,*,port:int,token:str,timeout:float=30):
        if type(port)is not int or not 1<=port<=65535:
            raise FlightClientError('literal loopback port required')
        if type(token)is not str or not 32<=len(token)<=512 or not token.isascii():
            raise FlightClientError('independently provisioned bearer required')
        if type(timeout)not in (int,float) or not 1<=timeout<=120:
            raise FlightClientError('invalid bounded local HTTP timeout')
        self.port=port;self.token=token;self.timeout=float(timeout)

    def request(self,operation:str,payload:dict)->dict:
        from .contracts import validate_payload
        validate_payload(operation,payload)
        raw=canonical_bytes({'operation':operation,'payload':payload},ceiling=65536)
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=self.timeout)
        try:
            conn.request('POST','/v2/operations',body=raw,headers={
                'Host':f'127.0.0.1:{self.port}',
                'Authorization':'Bearer '+self.token,
                'Content-Type':'application/json',
                'Content-Length':str(len(raw)),
                'Connection':'close'})
            resp=conn.getresponse()
            received=resp.read(262145)
            if len(received)>262144:
                raise FlightClientError('native API response exceeded size bound')
            if resp.status not in (200,400,401,403,404,409,413,415,500):
                raise FlightClientError('unexpected native API response code')
            def unique(pairs):
                item={}
                for key,value in pairs:
                    if key in item:raise FlightClientError('duplicate native API response field')
                    item[key]=value
                return item
            def reject_constant(value):raise FlightClientError('nonfinite native API response')
            try:value=json.loads(received,object_pairs_hook=unique,parse_constant=reject_constant)
            except (ValueError,UnicodeError) as exc:
                raise FlightClientError('native API response is not JSON') from exc
            if type(value)is not dict or set(value)!={'status','result'}:
                raise FlightClientError('native API envelope mismatch')
            if resp.status!=200:
                raise FlightClientError(f'native API operation rejected ({resp.status})')
            return value['result']
        except (OSError,http.client.HTTPException) as exc:
            raise FlightClientError('local native AI service unavailable') from exc
        finally:
            conn.close()
