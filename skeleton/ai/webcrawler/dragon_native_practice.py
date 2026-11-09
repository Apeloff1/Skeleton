"""Owner-scoped native-console exercise queue sharing Dragon's reviewed lessons.

Unlike the HTML practice path this produces source bundles appropriate for
GB/NES native ROM assembly, DOS VGA, and SDL desktop. A source bundle is NOT
a compiled ROM. No untrusted game code runs inside this web service.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from io import BytesIO
import json
import sqlite3
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo

from .dragon_native_targets import demand_target
from .dragon_native_projects import render_native_project, digest
from .dragon_game_mechanics import Mechanic
from .dragon_practice_lab import _owner, _time, DragonPracticeLab

@dataclass(frozen=True)
class NativeAttempt:
    attempt_id:str
    lesson_id:str
    owner:str
    target_id:str
    style:str
    state:str
    source_digest:str
    created_at:float
    reviewed:bool=False
    variant:int=0

class DragonNativePracticeLab:
    MAX_VARIANTS_PER_LESSON_TARGET_STYLE=8
    def __init__(self, db:sqlite3.Connection, parent:DragonPracticeLab):
        if parent.db is not db:raise ValueError("native practice must share canonical ledger")
        self.db=db
        self.parent=parent
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_native_game_attempts(
            owner TEXT NOT NULL,attempt_id TEXT NOT NULL,lesson_id TEXT NOT NULL,
            target_id TEXT NOT NULL,style TEXT NOT NULL,state TEXT NOT NULL,
            source_digest TEXT NOT NULL,project_json TEXT NOT NULL,
            created_at REAL NOT NULL,review_digest TEXT NOT NULL DEFAULT '',
            variant INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(owner,attempt_id),
            UNIQUE(owner,lesson_id,target_id,style,variant))""")
        # Migrate the branch's first-generation native table without deleting
        # its source archives, owner bindings or previously earned records.
        cols={r[1] for r in db.execute("PRAGMA table_info(dragon_native_game_attempts)")}
        if "variant" not in cols:
            db.execute("ALTER TABLE dragon_native_game_attempts RENAME TO dragon_native_game_attempts_previous")
            db.execute("""CREATE TABLE dragon_native_game_attempts(
                owner TEXT NOT NULL,attempt_id TEXT NOT NULL,lesson_id TEXT NOT NULL,
                target_id TEXT NOT NULL,style TEXT NOT NULL,state TEXT NOT NULL,
                source_digest TEXT NOT NULL,project_json TEXT NOT NULL,
                created_at REAL NOT NULL,review_digest TEXT NOT NULL DEFAULT '',
                variant INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(owner,attempt_id),
                UNIQUE(owner,lesson_id,target_id,style,variant))""")
            db.execute("""INSERT INTO dragon_native_game_attempts(
                owner,attempt_id,lesson_id,target_id,style,state,source_digest,
                project_json,created_at,review_digest,variant)
                SELECT owner,attempt_id,lesson_id,target_id,style,state,source_digest,
                       project_json,created_at,review_digest,0
                FROM dragon_native_game_attempts_previous""")
            db.execute("DROP TABLE dragon_native_game_attempts_previous")
        db.execute("""CREATE INDEX IF NOT EXISTS dragon_native_attempt_owner
            ON dragon_native_game_attempts(owner,created_at)""")
        db.commit()

    def generate(self, owner:str, *, target_id:str,style:str,
                 now:float,authorized:bool,consent:bool, design=None, source_context:dict|None=None,
                 request_id:str|None=None)->NativeAttempt:
        _owner(owner)
        _time(now)
        if not authorized or not consent:
            raise PermissionError("native practice requires live authorization and opt-in")
        demand_target(target_id)
        if design is not None:
            from .dragon_game_design import FIELDS, parse_design, GameDesign
            if not isinstance(design, GameDesign) or parse_design({k:getattr(design,k) for k in FIELDS}) != design or design.target != target_id or design.genre != style:
                raise ValueError("canonical design must match native request")
        stable_attempt = None
        if source_context is not None:
            from skeleton.ai.game_builder.contracts import canonical_digest
            from copy import deepcopy
            source_context = deepcopy(source_context)
            if (design is None or not isinstance(source_context, dict)
                    or source_context.get("schema") != "skeleton.dragon.delivery_brief.v1"
                    or source_context.get("owner") != owner
                    or source_context.get("design_digest") != design.digest
                    or source_context.get("ready_for_source_generation") is not True
                    or source_context.get("blockers") != []
                    or source_context.get("release_authorized") is not False
                    or source_context.get("training_authorized") is not False
                    or type(source_context.get("expires_at")) is not int
                    or not source_context["prepared_at"] <= now < source_context["expires_at"]
                    or canonical_digest({k:v for k,v in source_context.items() if k != "plan_digest"}) != source_context.get("plan_digest")
                    or len(json.dumps(source_context).encode()) > 64000):
                raise ValueError("current owner-bound delivery brief required")
            import re
            if not isinstance(request_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}",request_id):
                raise ValueError("bounded delivery idempotency key required")
            stable_attempt = digest([owner, "delivery", request_id])
        elif request_id is not None:
            raise ValueError("delivery key requires reviewed source context")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            if stable_attempt:
                existing = self.db.execute("SELECT lesson_id,target_id,style,state,source_digest,created_at,review_digest,variant,project_json FROM dragon_native_game_attempts WHERE owner=? AND attempt_id=?", (owner,stable_attempt)).fetchone()
                if existing:
                    stored = json.loads(existing[8])
                    if digest(stored["files"]) != existing[4] or json.loads(stored["files"].get("dragon-knowledge-brief.json", "null")) != source_context:
                        raise ValueError("delivery retry differs from committed request")
                    return NativeAttempt(stable_attempt,existing[0],owner,existing[1],existing[2],existing[3],existing[4],existing[5],bool(existing[6]),existing[7])
            day=int(now//86400)*86400
            native=self.db.execute("""SELECT COUNT(*) FROM dragon_native_game_attempts
                WHERE owner=? AND created_at>=? AND created_at<?""",
                (owner,day,day+86400)).fetchone()[0]
            old=self.db.execute("""SELECT COUNT(*) FROM dragon_practice_attempts
                WHERE owner=? AND created_at>=? AND created_at<?""",
                (owner,day,day+86400)).fetchone()[0]
            if native+old>=self.parent.policy.max_demos_per_day:
                raise ValueError("daily practice budget exhausted")
            lessons=self.db.execute("""SELECT lesson_id,title,mechanics_json
                FROM dragon_practice_lessons WHERE owner=? AND consent=1
                ORDER BY created_at,lesson_id""",(owner,)).fetchall()
            if source_context is not None:
                required_mechanics = {c["mechanic"] for c in source_context["citations"]}
                lessons = [row for row in lessons if required_mechanics.intersection(json.loads(row[2]))]
            if not lessons:raise PermissionError("no consented and verified lessons matching the design evidence")
            choices=[]
            for lesson_id,title,mechanics_json in lessons:
                count=self.db.execute("""SELECT COUNT(*) FROM dragon_native_game_attempts
                    WHERE owner=? AND lesson_id=? AND target_id=? AND style=?""",
                    (owner,lesson_id,target_id,style)).fetchone()[0]
                if count<self.MAX_VARIANTS_PER_LESSON_TARGET_STYLE:
                    choices.append((count,lesson_id,title,mechanics_json))
            if not choices:raise ValueError("native exercise variants exhausted for approved lessons")
            choices.sort(key=lambda x:(x[0],x[1]))
            variant,lesson_id,title,mechanics_json=choices[0]
            canonical=digest([owner,lesson_id,target_id,style,variant])
            project=render_native_project(
                title=design.title if design is not None else title,target_id=target_id,style=style,candidate_id=canonical,
                mechanics=tuple(Mechanic(x) for x in json.loads(mechanics_json)),
                authorized=True, design=design,
            )
            if source_context is not None:
                files = dict(project.files)
                files["dragon-knowledge-brief.json"] = json.dumps(source_context,sort_keys=True,indent=2)+"\n"
                files["dragon-game-design.json"] = json.dumps(source_context["design"],sort_keys=True,indent=2)+"\n"
                files["README.md"] += "\n## Reviewed design guidance\nSee dragon-knowledge-brief.json for source revisions, independent review and approval references. These guide the design; they do not certify generated code or grant distribution rights.\n"
                fingerprint = digest(files)
                project = replace(project, files=files, digest=fingerprint, project_id=digest([project.project_id,fingerprint]))
            project_json=json.dumps(asdict(project),sort_keys=True,
                                     separators=(",",":"),ensure_ascii=True)
            if len(project_json.encode("utf-8")) > self.parent.policy.max_artifact_bytes:
                raise ValueError("native practice artifact exceeds bounded policy")
            if len(project_json.encode())>250000:
                raise ValueError("native source payload exceeds budget")
            attempt_id=stable_attempt or digest([owner,lesson_id,project.project_id])
            self.db.execute("""INSERT INTO dragon_native_game_attempts(
                owner,attempt_id,lesson_id,target_id,style,state,source_digest,
                project_json,created_at,variant)VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (owner,attempt_id,lesson_id,target_id,style,
                 "source_generated",project.digest,project_json,now,variant))
            return NativeAttempt(attempt_id,lesson_id,owner,target_id,style,
                                 "source_generated",project.digest,now,False,variant)

    def list(self,owner:str,*,authorized:bool,limit:int=50)->tuple[NativeAttempt,...]:
        _owner(owner)
        if not authorized:raise PermissionError("native practice list requires authority")
        if not 1<=limit<=100:raise ValueError("invalid native history limit")
        rows=self.db.execute("""SELECT attempt_id,lesson_id,target_id,style,state,
            source_digest,created_at,review_digest,variant FROM dragon_native_game_attempts
            WHERE owner=? ORDER BY created_at DESC,attempt_id LIMIT ?""",
            (owner,limit)).fetchall()
        return tuple(NativeAttempt(r[0],r[1],owner,r[2],r[3],r[4],r[5],r[6],
                       bool(r[7]),r[8]) for r in rows)

    def project(self,owner:str,attempt_id:str,*,authorized:bool)->dict:
        _owner(owner)
        if not authorized:raise PermissionError("native source retrieval requires authority")
        row=self.db.execute("""SELECT source_digest,project_json
            FROM dragon_native_game_attempts
            WHERE owner=? AND attempt_id=?""",(owner,attempt_id)).fetchone()
        if row is None:raise LookupError("native game project missing")
        raw=json.loads(row[1])
        files=raw.get("files")
        if not isinstance(files,dict) or digest(files)!=row[0]:
            raise ValueError("native artifact digest mismatch")
        return raw

    def archive(self,owner:str,attempt_id:str,*,authorized:bool)->tuple[bytes,str]:
        """Deterministic ZIP bytes. Paths from built-in emitters only; no traversal."""
        item=self.project(owner,attempt_id,authorized=authorized)
        files=item["files"]
        buf=BytesIO()
        with ZipFile(buf,"w",compression=ZIP_DEFLATED,compresslevel=9) as z:
            for path,data in sorted(files.items()):
                if not path or path.startswith("/") or ".." in path.split("/") or "\\" in path:
                    raise ValueError("unsafe native source path")
                if not isinstance(data,str) or len(data.encode())>120000:
                    raise ValueError("native source is not bounded text")
                info=ZipInfo(path,date_time=(1980,1,1,0,0,0))
                info.compress_type=ZIP_DEFLATED
                info.external_attr=(0o100644<<16)
                z.writestr(info,data.encode("utf-8"))
        result=buf.getvalue()
        if len(result)>250000:raise ValueError("native project archive too large")
        return result,sha256(result).hexdigest()
