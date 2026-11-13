"""Transactional inference flight ledger, fenced against process crashes.

This ledger never performs inference. Every durable state transition, audit
entry and outbound event is atomic in the authoritative SpineDatabase.
"""
from __future__ import annotations
from hashlib import sha256
import json
from .contracts import FlightSpec, FlightPolicy, FlightBusy, FlightConflict, Ticket
from .clock import BootClock
from . import schema, events, policy, controls, lifecycle
from ..execution_spine.contracts import Identity, canonical, identifier, hexdigest
from ..execution_spine.principal import require_session


SELECT=('job_id,principal,session,request_id,signature,request_sha256,prompt,seed,'
        'temperature,priority,state,worker,owner_fence,lease_boot,lease_until_ns,'
        'created_ns,updated_ns,started_ns,finished_ns,receipt_json,receipt_sha256,'
        'hold_reason,cancel_requested')
COLUMNS=('job_id','principal','session','request_id','signature','request_sha256',
         'prompt','seed','temperature','priority','state','worker','owner_fence',
         'lease_boot','lease_until_ns','created_ns','updated_ns','started_ns',
         'finished_ns','receipt_json','receipt_sha256','hold_reason','cancel_requested')


def _row(row)->dict:
    if row is None:raise FlightConflict('flight job not found')
    return dict(zip(COLUMNS,row,strict=True))


def _visible(job:dict)->dict:
    return {key:job[key] for key in ('job_id','session','request_id','priority','state',
            'owner_fence','created_ns','updated_ns','started_ns','finished_ns',
            'hold_reason','cancel_requested')}


def _receipt(job:dict,result:dict,identity:Identity)->bytes:
    if not isinstance(result,dict):raise FlightConflict('authoritative model receipt required')
    expected={'session':job['session'],'request_id':job['request_id'],
              'request_sha256':job['request_sha256'],'model_sha256':identity.model_sha256,
              'tokenizer_sha256':identity.tokenizer_sha256,'principal':identity.key()}
    if any(result.get(key)!=value for key,value in expected.items()):
        raise FlightConflict('model receipt identity does not match queued intent')
    output=hexdigest(result.get('output_sha256'),'model output')
    revision=result.get('revision')
    if type(revision)is not int or revision<1:raise FlightConflict('invalid model revision')
    material={'schema':'skeleton.ai.flight-result.v1','job_id':job['job_id'],
              'session':job['session'],'request_id':job['request_id'],
              'revision':revision,'request_sha256':job['request_sha256'],
              'output_sha256':output,'model_sha256':identity.model_sha256,
              'tokenizer_sha256':identity.tokenizer_sha256}
    return canonical(material,ceiling=4096)


class FlightLedger:
    """All public methods are owner-bound, bounded and transactionally serialized.

    The callable native inference engine is intentionally outside this class.
    A worker must transition claimed -> running before calling the model.
    Only unstarted *claimed* tickets may be safely returned to the queue.
    """

    def __init__(self,db,identity:Identity,*,settings:FlightPolicy|None=None,clock:BootClock|None=None):
        if not isinstance(identity,Identity):raise FlightConflict('principal identity required')
        self.db=db;self.identity=identity
        self.settings=settings if settings is not None else FlightPolicy()
        if not isinstance(self.settings,FlightPolicy):raise FlightConflict('invalid flight policy')
        self.clock=clock or BootClock()
        schema.install(db)

    def _get(self,conn,job_id:str)->dict:
        identifier(job_id,'job')
        row=_row(conn.execute('SELECT '+SELECT+' FROM ai_flight_jobs WHERE job_id=?',(job_id,)).fetchone())
        if row['principal']!=self.identity.key():raise FlightConflict('job belongs to a different principal')
        return row

    def inspect(self,job_id:str,*,events_check:bool=True)->dict:
        with self.db.snapshot() as conn:
            job=self._get(conn,job_id)
            if events_check:lifecycle.verify(events.inspect(conn,job_id),job['state'])
            record=_visible(job)
            if job['state']=='completed':
                raw=job['receipt_json']
                if raw is None or sha256(raw).hexdigest()!=job['receipt_sha256']:
                    raise FlightConflict('stored flight result is corrupt')
                record['result']=json.loads(raw)
            return record

    def _submit_locked(self,conn,spec:FlightSpec,stamp)->dict:
        if not isinstance(spec,FlightSpec):raise FlightConflict('invalid queued task')
        if spec.identity!=self.identity:raise FlightConflict('submission principal mismatch')
        bound=spec.request().bound_digest()
        require_session(conn,self.identity,spec.session)
        existing=conn.execute('SELECT '+SELECT+' FROM ai_flight_jobs WHERE job_id=? OR (session=? AND request_id=?)',
                              (spec.job_id,spec.session,spec.request_id)).fetchone()
        if existing:
            old=_row(existing)
            if (old['job_id']!=spec.job_id or old['request_id']!=spec.request_id or
                old['principal']!=self.identity.key() or
                old['signature']!=spec.fingerprint() or old['request_sha256']!=bound or
                old['prompt']!=spec.prompt.encode('utf8')):
                raise FlightConflict('queued request key reused with different authority or content')
            lifecycle.verify(events.inspect(conn,spec.job_id),old['state'])
            return _visible(old)|{'replayed':True}
        policy.enforce(conn,self.identity.key(),self.settings)
        conn.execute('''INSERT INTO ai_flight_jobs
            (job_id,principal,session,request_id,signature,request_sha256,prompt,seed,
             temperature,priority,state,created_ns,updated_ns)
            VALUES (?,?,?,?,?,?,?,?,?,?,'queued',?,?)''',
            (spec.job_id,self.identity.key(),spec.session,spec.request_id,spec.fingerprint(),
             bound,spec.prompt.encode('utf8'),spec.seed,float(spec.temperature),
             spec.priority,stamp.wall,stamp.wall))
        events.append(conn,spec.job_id,'submitted',
                      {'principal':self.identity.key(),'request_sha256':bound,'priority':spec.priority})
        return _visible(self._get(conn,spec.job_id))|{'replayed':False}

    def submit(self,spec:FlightSpec)->dict:
        stamp=self.clock.stamp()
        with self.db.transaction() as conn:
            return self._submit_locked(conn,spec,stamp)

    def claim(self,worker:str)->Ticket|None:
        identifier(worker,'worker')
        stamp=self.clock.stamp()
        with self.db.transaction() as conn:
            controls.require_running(conn)
            policy.capacity(conn,self.settings)
            # Bounded overfetch protects against an unbounded scan; principal ownership
            # is checked before picking a candidate so a worker cannot adopt another tenant.
            rows=conn.execute("""SELECT job_id,principal,priority,created_ns FROM ai_flight_jobs
                WHERE state='queued' AND principal=? AND NOT EXISTS (
                    SELECT 1 FROM ai_flight_jobs running WHERE running.session=ai_flight_jobs.session
                    AND running.state IN ('claimed','running'))
                ORDER BY priority DESC,created_ns ASC,job_id ASC LIMIT ?""",
                (self.identity.key(),self.settings.max_probe)).fetchall()
            if not rows:return None
            active={p:c for p,c in conn.execute("""SELECT principal,COUNT(*) FROM ai_flight_jobs
                WHERE state IN ('claimed','running') GROUP BY principal""").fetchall()}
            # Select least-active principal first, preserve priority then FIFO inside that tier.
            selected=min(rows,key=lambda r:(active.get(r[1],0),-r[2],r[3],r[0]))
            job_id=selected[0]
            new_until=stamp.tick+self.settings.lease_ms*1_000_000
            result=conn.execute("""UPDATE ai_flight_jobs SET state='claimed',worker=?,owner_fence=owner_fence+1,
                lease_boot=?,lease_until_ns=?,updated_ns=? WHERE job_id=? AND state='queued'""",
                (worker,stamp.boot,new_until,stamp.wall,job_id))
            if result.rowcount!=1:raise FlightBusy('competing claim changed queue state')
            ticket=self._ticket(self._get(conn,job_id))
            events.append(conn,job_id,'claimed',{'worker':worker,'fence':ticket.fence,'boot':stamp.boot})
            return ticket

    @staticmethod
    def _priority(conn,job_id):
        return conn.execute('SELECT priority FROM ai_flight_jobs WHERE job_id=?',(job_id,)).fetchone()[0]

    @staticmethod
    def _created(conn,job_id):
        return conn.execute('SELECT created_ns FROM ai_flight_jobs WHERE job_id=?',(job_id,)).fetchone()[0]

    @staticmethod
    def _ticket(job):
        return Ticket(job['job_id'],job['worker'],job['owner_fence'],job['lease_boot'],job['lease_until_ns'])

    def _verify_ticket(self,job,ticket:Ticket,stamp,*,states:tuple[str,...]):
        if (not isinstance(ticket,Ticket) or job['job_id']!=ticket.job_id or
            job['worker']!=ticket.worker or job['owner_fence']!=ticket.fence or
            job['lease_boot']!=ticket.boot or job['lease_until_ns']!=ticket.expires_ns):
            raise FlightConflict('stale or unrelated worker ticket')
        if job['state'] not in states:raise FlightConflict('job is not in a permitted execution state')
        if stamp.boot!=ticket.boot or stamp.tick>=ticket.expires_ns:
            raise FlightConflict('claim lost or crossed boot/deadline fence')

    def start(self,ticket:Ticket)->dict:
        stamp=self.clock.stamp()
        with self.db.transaction() as conn:
            job=self._get(conn,ticket.job_id)
            self._verify_ticket(job,ticket,stamp,states=('claimed',))
            if job['cancel_requested']:raise FlightConflict('job cancelled before model start')
            running=conn.execute("SELECT COUNT(*) FROM ai_flight_jobs WHERE state='running'").fetchone()[0]
            if running>=self.settings.max_running:raise FlightBusy('inference running ceiling')
            conn.execute("UPDATE ai_flight_jobs SET state='running',started_ns=?,updated_ns=? WHERE job_id=?",
                         (stamp.wall,stamp.wall,ticket.job_id))
            events.append(conn,ticket.job_id,'model-started',{'fence':ticket.fence,'worker':ticket.worker})
            return _visible(self._get(conn,ticket.job_id))

    def heartbeat(self,ticket:Ticket)->Ticket:
        stamp=self.clock.stamp()
        with self.db.transaction() as conn:
            job=self._get(conn,ticket.job_id)
            self._verify_ticket(job,ticket,stamp,states=('claimed','running'))
            expires=stamp.tick+self.settings.lease_ms*1_000_000
            conn.execute('UPDATE ai_flight_jobs SET lease_until_ns=?,updated_ns=? WHERE job_id=?',
                         (expires,stamp.wall,ticket.job_id))
            events.append(conn,ticket.job_id,'heartbeat',{'fence':ticket.fence,'worker':ticket.worker})
            return Ticket(ticket.job_id,ticket.worker,ticket.fence,ticket.boot,expires)

    def finish(self,ticket:Ticket,result:dict,*,spine)->dict:
        # Public commit API must not trust caller-supplied model claims.
        # Read an already committed receipt from the authoritative execution
        # spine, without calling inference and without nesting SQLite writers.
        if spine.identity!=self.identity:raise FlightConflict('receipt principal mismatch')
        spec=self.request_for(ticket.job_id)
        canonical_receipt=spine.replay(spec.session,spec.request_id,spec.prompt,
                                      seed=spec.seed,temperature=spec.temperature)
        if canonical_receipt is None:
            raise FlightConflict('no committed canonical model receipt')
        if _receipt({'job_id':spec.job_id,'session':spec.session,
                     'request_id':spec.request_id,
                     'request_sha256':spec.request().bound_digest()},
                    result,self.identity) != _receipt({
                     'job_id':spec.job_id,'session':spec.session,
                     'request_id':spec.request_id,
                     'request_sha256':spec.request().bound_digest()},
                    canonical_receipt,self.identity):
            raise FlightConflict('submitted result disagrees with canonical model receipt')
        stamp=self.clock.stamp()
        with self.db.transaction() as conn:
            job=self._get(conn,ticket.job_id)
            self._verify_ticket(job,ticket,stamp,states=('running',))
            raw=_receipt(job,canonical_receipt,self.identity)
            conn.execute("""UPDATE ai_flight_jobs SET state='completed',receipt_json=?,receipt_sha256=?,
                lease_until_ns=NULL,finished_ns=?,updated_ns=? WHERE job_id=?""",
                (raw,sha256(raw).hexdigest(),stamp.wall,stamp.wall,ticket.job_id))
            events.append(conn,ticket.job_id,'completed',{'receipt_sha256':sha256(raw).hexdigest()})
            return _visible(self._get(conn,ticket.job_id))|{'result':json.loads(raw)}

    def fail(self,ticket:Ticket,reason:str)->dict:
        identifier(reason,'failure class')
        stamp=self.clock.stamp()
        with self.db.transaction() as conn:
            job=self._get(conn,ticket.job_id)
            if (job['owner_fence']!=ticket.fence or job['worker']!=ticket.worker or
                job['lease_boot']!=ticket.boot or job['state'] not in ('claimed','running')):
                raise FlightConflict('cannot fail task from unowned ticket')
            conn.execute("""UPDATE ai_flight_jobs SET state='held',hold_reason=?,finished_ns=?,
                 lease_until_ns=NULL,updated_ns=? WHERE job_id=?""",
                 (reason,stamp.wall,stamp.wall,ticket.job_id))
            events.append(conn,ticket.job_id,'held',{'reason':reason,'fence':ticket.fence})
            return _visible(self._get(conn,ticket.job_id))

    def cancel(self,job_id:str)->dict:
        stamp=self.clock.stamp()
        with self.db.transaction() as conn:
            job=self._get(conn,job_id)
            if job['state'] in ('completed','held','cancelled'):return _visible(job)
            if job['state']=='running':
                if job['cancel_requested']:return _visible(job)
                conn.execute('UPDATE ai_flight_jobs SET cancel_requested=1,updated_ns=? WHERE job_id=?',(stamp.wall,job_id))
                events.append(conn,job_id,'cancel-requested',{'fence':job['owner_fence']})
            else:
                conn.execute("""UPDATE ai_flight_jobs SET state='cancelled',cancel_requested=1,
                    lease_until_ns=NULL,finished_ns=?,updated_ns=? WHERE job_id=?""",
                    (stamp.wall,stamp.wall,job_id))
                events.append(conn,job_id,'cancelled',{'fence':job['owner_fence']})
            return _visible(self._get(conn,job_id))

    def pending(self,*,limit:int=128)->tuple[dict,...]:
        if type(limit)is not int or not 1<=limit<=4096:raise FlightConflict('invalid inspection bound')
        with self.db.snapshot() as conn:
            rows=conn.execute('SELECT '+SELECT+" FROM ai_flight_jobs WHERE principal=? AND state IN ('queued','claimed','running') ORDER BY created_ns,job_id LIMIT ?",(self.identity.key(),limit+1)).fetchall()
            if len(rows)>limit:raise FlightBusy('pending inventory larger than operator review ceiling')
            return tuple(_visible(_row(row)) for row in rows)

    def request_for(self,job_id:str)->FlightSpec:
        with self.db.snapshot() as conn:
            job=self._get(conn,job_id)
            return FlightSpec(self.identity,job['job_id'],job['session'],job['request_id'],
                              job['prompt'].decode('utf8'),job['seed'],job['temperature'],job['priority'])

    def state_count(self)->dict[str,int]:
        with self.db.snapshot() as conn:
            return {state:conn.execute('SELECT COUNT(*) FROM ai_flight_jobs WHERE principal=? AND state=?',
                                       (self.identity.key(),state)).fetchone()[0]
                    for state in ('queued','claimed','running','completed','held','cancelled')}
