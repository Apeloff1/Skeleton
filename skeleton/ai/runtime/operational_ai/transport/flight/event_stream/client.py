"""Bounded loopback SSE client; exact cursor resume, no automatic model calls."""
from __future__ import annotations
import http.client
import json
import re
from urllib.parse import quote
from .contracts import StreamError,identifier,bounded
from .query import parse_path

_ID=re.compile(r'^v1\.[1-9][0-9]{0,3}\.[0-9a-f]{64}\.[0-9a-f]{64}$')

def parse_stream(raw:bytes,*,max_bytes:int=262144)->tuple[dict,...]:
    if type(raw) is not bytes or len(raw)>max_bytes:
        raise StreamError('stream response exceeds bound')
    try:text=raw.decode('ascii','strict')
    except UnicodeError as exc:raise StreamError('non-ASCII stream frame') from exc
    if not text.endswith('\n\n'):
        raise StreamError('incomplete stream frame')
    result=[]
    for item in text.split('\n\n'):
        if not item or item.startswith(':'):continue
        rows=item.split('\n'); keys={}
        for row in rows:
            if row.startswith(':'):continue
            if ': ' not in row:raise StreamError('invalid SSE field framing')
            key,value=row.split(': ',1)
            if key not in ('id','event','data') or key in keys:
                raise StreamError('unknown or duplicate SSE field')
            keys[key]=value
        if set(keys) not in ({'event','data'},{'id','event','data'}):
            raise StreamError('missing required SSE fields')
        if keys['event'] not in ('transition','checkpoint'):
            raise StreamError('unexpected event type')
        if 'id' in keys and _ID.fullmatch(keys['id']) is None:
            raise StreamError('invalid event resume cursor')
        try:payload=json.loads(keys['data'])
        except ValueError as exc:raise StreamError('invalid event JSON') from exc
        if type(payload)is not dict:raise StreamError('SSE payload must be a JSON object')
        result.append({'type':keys['event'],'cursor':keys.get('id'),'data':payload})
    if not result or result[-1]['type']!='checkpoint' or any(e['type']=='checkpoint' for e in result[:-1]):
        raise StreamError('event stream is missing a unique final checkpoint')
    return tuple(result)

def get_events(*,host:str='127.0.0.1',port:int,token:str,job_id:str,
               cursor:str|None=None,limit:int=32,wait_ms:int=0,timeout:float=8.0)->tuple[dict,...]:
    if host not in ('127.0.0.1','::1') or type(port)is not int or not 1<=port<=65535:
        raise StreamError('client only supports literal local loopback')
    identifier(job_id);bounded(limit,1,64,'client limit');bounded(wait_ms,0,2000,'client poll')
    if type(token)is not str or not 32<=len(token)<=512:
        raise StreamError('private API credential required')
    if cursor is not None and (_ID.fullmatch(cursor) is None):
        raise StreamError('invalid resume cursor')
    if type(timeout) not in (float,int) or not 2<=timeout<=30:
        raise StreamError('invalid finite client timeout')
    query=f'?limit={limit}&wait_ms={wait_ms}'
    if cursor:query+='&cursor='+quote(cursor,safe='.')
    path=f'/v2/jobs/{job_id}/events'+query
    parse_path(path)
    connection=http.client.HTTPConnection(host,port,timeout=float(timeout))
    try:
        connection.request('GET',path,headers={'Host':f'{host}:{port}',
            'Authorization':'Bearer '+token,'Accept':'text/event-stream'})
        response=connection.getresponse()
        size=response.getheader('Content-Length')
        if response.status!=200:
            raise StreamError('local event transport rejected request')
        if response.getheader('Content-Type')!='text/event-stream; charset=utf-8':
            raise StreamError('local event response has unexpected media type')
        if size is None or not size.isascii() or not size.isdecimal() or not 1<=int(size)<=262144:
            raise StreamError('invalid event stream response size')
        raw=response.read(int(size)+1)
        if len(raw)!=int(size):
            raise StreamError('incomplete event stream response')
        return parse_stream(raw)
    finally:connection.close()
