"""Complete encrypted-at-rest-history is external; this stores hash-chain custody."""
from __future__ import annotations
from hashlib import sha256
import hmac,json,sqlite3,threading
from .contracts import Span,ContextError,ID

class ContextArchive:
    """Integrity and scope ledger, not a substitute for encrypted conversation state."""
    def __init__(self,path:str=':memory:',integrity_key:bytes=b''):
        if not isinstance(integrity_key,bytes) or len(integrity_key)<32:
            raise ContextError('operator supplied archive HMAC key required')
        self._key=integrity_key;self._lock=threading.RLock()
        self._db=sqlite3.connect(path,isolation_level=None,check_same_thread=False)
        self._db.execute('CREATE TABLE IF NOT EXISTS archive(tenant TEXT,user TEXT,session TEXT,seq INTEGER,span_id TEXT,revision INTEGER,trust TEXT,content_digest TEXT,prior TEXT,mac TEXT,PRIMARY KEY(tenant,user,session,seq),UNIQUE(tenant,user,session,span_id,revision))')

    def _mac(self,row:dict)->str:
        return hmac.new(self._key,json.dumps(row,sort_keys=True,separators=(',',':')).encode(),sha256).hexdigest()

    def append(self,tenant:str,user:str,session:str,span:Span)->int:
        if any(not ID.fullmatch(x) for x in (tenant,user,session)):
            raise ContextError('invalid archive scope')
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                records=self._db.execute('SELECT seq,span_id,revision,trust,content_digest,prior,mac FROM archive WHERE tenant=? AND user=? AND session=? ORDER BY seq',(tenant,user,session)).fetchall()
                prior='0'*64
                for seq,sid,revision,trust,content,stored_prior,mac in records:
                    row={'tenant':tenant,'user':user,'session':session,'seq':seq,'span_id':sid,'revision':revision,'trust':trust,'content_digest':content,'prior':stored_prior}
                    if stored_prior!=prior or not hmac.compare_digest(self._mac(row),mac):
                        raise ContextError('archive HMAC chain broken')
                    prior=mac
                seq=len(records)+1
                record={'tenant':tenant,'user':user,'session':session,'seq':seq,'span_id':span.span_id,'revision':span.revision,'trust':span.trust,'content_digest':span.digest,'prior':prior}
                self._db.execute('INSERT INTO archive VALUES (?,?,?,?,?,?,?,?,?,?)',(tenant,user,session,seq,span.span_id,span.revision,span.trust,span.digest,prior,self._mac(record)))
                self._db.execute('COMMIT');return seq
            except BaseException:
                self._db.execute('ROLLBACK');raise

    def verify(self,tenant:str,user:str,session:str)->tuple[int,str]:
        with self._lock:
            rows=self._db.execute('SELECT seq,span_id,revision,trust,content_digest,prior,mac FROM archive WHERE tenant=? AND user=? AND session=? ORDER BY seq',(tenant,user,session)).fetchall()
        prior='0'*64
        for n,(seq,sid,revision,trust,content,stored,mac) in enumerate(rows,1):
            rec={'tenant':tenant,'user':user,'session':session,'seq':seq,'span_id':sid,'revision':revision,'trust':trust,'content_digest':content,'prior':stored}
            if seq!=n or stored!=prior or not hmac.compare_digest(self._mac(rec),mac):
                raise ContextError('archive chain invalid')
            prior=mac
        return len(rows),prior

    def close(self):self._db.close()
