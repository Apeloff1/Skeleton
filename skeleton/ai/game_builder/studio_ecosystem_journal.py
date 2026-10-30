"""Durable, single-host SQLite studio work journal with transactional CAS.

All states represent operator-reported *planning* progress, never independently
verified assets or finished game releases. The only mutable state is a local
private SQLite database; the source work graph remains immutable.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Iterator, Mapping

from .studio_ecosystem_quest import StudioQuestError

TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
HEX = re.compile(r"^[0-9a-f]{64}$")
SCHEMA = "skeleton.game_builder.studio_work_journal.v1"


def canonical(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StudioQuestError("noncanonical work journal input") from exc


def digest(value: object) -> str:
    return sha256(canonical(value).encode("ascii")).hexdigest()


def checked_graph(graph: Mapping[str, Any]) -> tuple[str, str, str, tuple[dict[str, object], ...]]:
    if not isinstance(graph, Mapping) or graph.get("schema") != "skeleton.game_builder.studio_work_graph.v1":
        raise StudioQuestError("wrong producer graph schema")
    project, source, fingerprint = (graph.get("project_id"), graph.get("source_digest"),
                                    graph.get("work_graph_sha256"))
    if not isinstance(project, str) or not TOKEN.fullmatch(project):
        raise StudioQuestError("unsafe producer project ID")
    if not isinstance(source, str) or not HEX.fullmatch(source):
        raise StudioQuestError("invalid producer source digest")
    tasks = graph.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise StudioQuestError("producer graph has no tasks")
    observed: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise StudioQuestError("invalid producer task")
        name, deps, kind = task.get("id"), task.get("depends_on"), task.get("kind")
        if (not isinstance(name, str) or not TOKEN.fullmatch(name)
                or name in observed or not isinstance(kind, str) or not TOKEN.fullmatch(kind)
                or not isinstance(deps, list) or any(
                    not isinstance(dep, str) or dep not in observed for dep in deps
                ) or len(deps) != len(set(deps))):
            raise StudioQuestError("invalid or out-of-order task dependency")
        observed.add(name)
    expected = digest({"project": project, "source": source, "tasks": tasks})
    if fingerprint != expected:
        raise StudioQuestError("work graph digest or canonical owner mismatch")
    return project, source, expected, tuple(tasks)


def _private_directory(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise StudioQuestError("existing non-symlink private workspace required")
    st = root.stat()
    if os.name == "posix":
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise StudioQuestError("work journal directory must be owned and private")


def _safe_database(path: Path) -> None:
    if path.is_symlink():
        raise StudioQuestError("linked journal database refused")
    if path.exists():
        st = path.stat()
        if not stat.S_ISREG(st.st_mode):
            raise StudioQuestError("journal path must be a regular file")
        if os.name == "posix" and (st.st_uid != os.getuid() or st.st_mode & 0o077):
            raise StudioQuestError("journal file must be owned and private")


def _create_private_database(path: Path) -> None:
    """Prevent SQLite's default umask from creating a world-readable DB."""
    _safe_database(path)
    if path.exists():
        return
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        _safe_database(path)
        return
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    _safe_database(path)


class WorkJournal:
    """Atomic work claims, unverified submissions, and explicit review decisions."""

    def __init__(self, root: Path, graph: Mapping[str, Any], *, authorized: bool):
        if not authorized:
            raise PermissionError("private work journal requires operator authorization")
        self.root = Path(root)
        _private_directory(self.root)
        self.path = self.root / "studio_work.sqlite3"
        self.project, self.source, self.graph_digest, self.tasks = checked_graph(graph)
        _create_private_database(self.path)
        with self._tx() as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, status TEXT NOT NULL,
                worker TEXT, token TEXT, attempt INTEGER NOT NULL DEFAULT 0,
                submitted_sha TEXT, reviewer TEXT
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, event_json TEXT NOT NULL,
                previous_sha TEXT NOT NULL, event_sha TEXT NOT NULL
            )""")
            self._verify_chain(db)
            rows = dict(db.execute("SELECT key, value FROM meta"))
            expected = {"schema": SCHEMA, "project": self.project,
                        "source": self.source, "graph": self.graph_digest}
            if rows:
                if any(rows.get(k) != v for k, v in expected.items()):
                    raise StudioQuestError("work journal changed source or graph identity")
                existing = {r[0] for r in db.execute("SELECT id FROM tasks")}
                if existing != {t["id"] for t in self.tasks}:
                    raise StudioQuestError("journal task inventory differs from source")
            else:
                for key, value in expected.items():
                    db.execute("INSERT INTO meta (key,value) VALUES (?,?)", (key,value))
                for task in self.tasks:
                    db.execute("INSERT INTO tasks (id,status) VALUES (?,'pending')", (task["id"],))
        _safe_database(self.path)
        self.verify_state()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        _private_directory(self.root)
        _safe_database(self.path)
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _verify_chain(db: sqlite3.Connection) -> str:
        """Replay every durable event before trusting any stored task status."""
        prior = "0"*64
        for encoded, parent, fingerprint in db.execute(
            "SELECT event_json,previous_sha,event_sha FROM events ORDER BY seq"
        ):
            if not isinstance(encoded, str) or parent != prior:
                raise StudioQuestError("journal event predecessor mismatch")
            if sha256(encoded.encode("utf-8")).hexdigest() != fingerprint:
                raise StudioQuestError("journal event digest mismatch")
            try:
                event = json.loads(encoded)
            except (TypeError, ValueError) as exc:
                raise StudioQuestError("invalid durable event") from exc
            if (not isinstance(event, dict) or
                    set(event) != {"kind","task","actor","previous"} or
                    event["previous"] != prior or canonical(event) != encoded):
                raise StudioQuestError("noncanonical durable event chain")
            prior = fingerprint
        return prior

    def verify_events(self) -> dict[str, object]:
        with self._tx() as db:
            last = self._verify_chain(db)
            count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            return {"schema":"skeleton.game_builder.studio_work_journal_audit.v1",
                    "project_id":self.project,"events":count,
                    "final_sha256":last,"external_attestation_verified":False,
                    "release_certified":False}

    def _verify_state(self, db: sqlite3.Connection) -> None:
        """Reconstruct task lifecycle from the event stream, not mutable rows."""
        self._verify_chain(db)
        state = {
            task["id"]: {"status":"pending", "worker":None, "attempt":0,
                         "sha":None, "reviewer":None}
            for task in self.tasks
        }
        deps = {task["id"]:task["depends_on"] for task in self.tasks}
        paused = False
        for (encoded,) in db.execute("SELECT event_json FROM events ORDER BY seq"):
            event = json.loads(encoded)
            kind, task, actor = event["kind"], event["task"], event["actor"]
            if kind in ("pause","resume"):
                if task != "producer-admission" or not isinstance(actor,str):
                    raise StudioQuestError("corrupt pause authority")
                paused = kind == "pause"
                continue
            if task not in state:
                raise StudioQuestError("durable event names an unregistered task")
            row = state[task]
            if kind == "claim":
                if row["status"] != "pending" or paused or any(
                    state[d]["status"] != "reviewed_claim" for d in deps[task]
                ):
                    raise StudioQuestError("invalid historical producer admission")
                row.update(status="leased",worker=actor,attempt=row["attempt"]+1)
            elif kind == "submit":
                if row["status"]!="leased" or not isinstance(actor,str) or not HEX.fullmatch(actor):
                    raise StudioQuestError("invalid historical producer submission")
                row.update(status="submitted",sha=actor)
            elif kind in ("review_accept","review_reject"):
                if row["status"]!="submitted" or actor==row["worker"]:
                    raise StudioQuestError("invalid historical reviewer transition")
                if kind=="review_accept":
                    row.update(status="reviewed_claim",reviewer=actor)
                else:
                    row.update(status="pending",worker=None,sha=None,reviewer=actor)
            elif kind == "operator_recovery":
                if row["status"]!="leased" or actor==row["worker"]:
                    raise StudioQuestError("invalid historical operator recovery")
                row.update(status="pending",worker=None)
            else:
                raise StudioQuestError("unrecognized producer event kind")
        stored = {
            name: {"status": status, "worker": worker, "attempt": attempt,
                   "sha": sha, "reviewer": reviewer, "token": token}
            for name,status,worker,attempt,sha,reviewer,token in db.execute(
                "SELECT id,status,worker,attempt,submitted_sha,reviewer,token FROM tasks"
            )
        }
        if set(stored) != set(state):
            raise StudioQuestError("task table differs from source inventory")
        for name, replay in state.items():
            persisted = stored[name]
            if any(persisted[key] != replay[key] for key in replay):
                raise StudioQuestError("stored task status differs from event replay")
            if (persisted["status"] == "leased") != (persisted["token"] is not None):
                raise StudioQuestError("lease token presence disagrees with history")
        setting=db.execute("SELECT value FROM meta WHERE key='paused'").fetchone()
        if (setting is not None and setting[0] not in ("0","1")) or (
            paused != (setting is not None and setting[0] == "1")
        ):
            raise StudioQuestError("pause state differs from event history")

    def verify_state(self) -> dict[str, object]:
        with self._tx() as db:
            self._verify_state(db)
            return {"schema":"skeleton.game_builder.studio_work_state_replay.v1",
                    "project_id":self.project,
                    "local_lifecycle_replay_valid":True,
                    "external_proof_verified":False,"release_certified":False}

    def snapshot(self) -> dict[str, object]:
        with self._tx() as db:
            self._verify_state(db)
            rows = {r[0]: {"status":r[1],"worker":r[2],"attempt":r[3],
                           "submitted_sha":r[4],"reviewer":r[5]}
                    for r in db.execute("SELECT id,status,worker,attempt,submitted_sha,reviewer FROM tasks")}
            return {"schema": SCHEMA,"project_id":self.project,
                    "source_digest":self.source,"graph_sha256":self.graph_digest,
                    "tasks":rows,"completion_evidence_verified":False,
                    "release_certified":False}

    def set_paused(self, paused: bool, *, operator: str, authorized: bool) -> None:
        """Pause only fresh task admissions; in-flight evidence can still submit."""
        if not authorized:
            raise PermissionError("pause requires operator authorization")
        if type(paused) is not bool or not isinstance(operator,str) or not TOKEN.fullmatch(operator):
            raise StudioQuestError("invalid pause command")
        with self._tx() as db:
            db.execute("""INSERT INTO meta(key,value) VALUES('paused',?)
                          ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                       ("1" if paused else "0",))
            self._event(db,"pause" if paused else "resume","producer-admission",operator)

    def claim(self, task_id: str, *, worker: str, token: str, authorized: bool) -> None:
        if not authorized:
            raise PermissionError("claim requires operator authorization")
        if not all(isinstance(x,str) and TOKEN.fullmatch(x) for x in (task_id,worker,token)):
            raise StudioQuestError("unsafe claim identity")
        definitions = {t["id"]:t for t in self.tasks}
        if task_id not in definitions:
            raise StudioQuestError("unregistered producer task")
        with self._tx() as db:
            states = dict(db.execute("SELECT id,status FROM tasks"))
            paused=db.execute("SELECT value FROM meta WHERE key='paused'").fetchone()
            if paused is not None and paused[0]=="1":
                raise StudioQuestError("producer admission paused by operator")
            if states[task_id] != "pending":
                raise StudioQuestError("already claimed or not pending")
            if any(states[dep] != "reviewed_claim" for dep in definitions[task_id]["depends_on"]):
                raise StudioQuestError("source producer prerequisites not reviewed")
            db.execute("""UPDATE tasks SET status='leased',worker=?,token=?,
                        attempt=attempt+1 WHERE id=? AND status='pending'""",
                       (worker,token,task_id))
            self._event(db,"claim",task_id,worker)

    def recover_claim(self, task_id: str, *, former_worker: str,
                      expected_attempt: int, operator: str,
                      authorized: bool) -> None:
        """Explicit operator recovery, never a timer-based silent takeover."""
        if not authorized:
            raise PermissionError("recovery needs operator authorization")
        if (not isinstance(former_worker,str) or not TOKEN.fullmatch(former_worker)
                or not isinstance(operator,str) or not TOKEN.fullmatch(operator)
                or type(expected_attempt) is not int or expected_attempt < 1
                or operator == former_worker):
            raise StudioQuestError("invalid independent recovery authority")
        with self._tx() as db:
            row=db.execute("SELECT status,worker,attempt FROM tasks WHERE id=?",
                           (task_id,)).fetchone()
            if row != ("leased",former_worker,expected_attempt):
                raise StudioQuestError("stale recovery or changed lease owner")
            db.execute("""UPDATE tasks SET status='pending',worker=NULL,token=NULL
                          WHERE id=?""",(task_id,))
            self._event(db,"operator_recovery",task_id,operator)

    def submit(self, task_id: str, *, worker: str, token: str,
               artifact_sha256: str, authorized: bool) -> None:
        if not authorized:
            raise PermissionError("submit requires operator authorization")
        if not isinstance(artifact_sha256,str) or not HEX.fullmatch(artifact_sha256):
            raise StudioQuestError("invalid submitted evidence fingerprint")
        with self._tx() as db:
            row=db.execute("SELECT status,worker,token FROM tasks WHERE id=?",(task_id,)).fetchone()
            if (not isinstance(worker,str) or not TOKEN.fullmatch(worker)
                    or not isinstance(token,str) or not TOKEN.fullmatch(token)
                    or row != ("leased",worker,token)):
                raise StudioQuestError("stale or mismatched worker token")
            db.execute("""UPDATE tasks SET status='submitted',submitted_sha=?,token=NULL
                          WHERE id=?""",(artifact_sha256,task_id))
            self._event(db,"submit",task_id,artifact_sha256)

    def review(self, task_id: str, *, reviewer: str, accepted: bool,
               authorized: bool) -> None:
        if not authorized:
            raise PermissionError("review needs independent operator authorization")
        if not isinstance(reviewer,str) or not TOKEN.fullmatch(reviewer) or type(accepted) is not bool:
            raise StudioQuestError("invalid reviewer decision")
        with self._tx() as db:
            row=db.execute("SELECT status,worker FROM tasks WHERE id=?",(task_id,)).fetchone()
            if row is None or row[0] != "submitted" or reviewer == row[1]:
                raise StudioQuestError("missing submission or non-independent review")
            if accepted:
                db.execute("""UPDATE tasks SET status='reviewed_claim',reviewer=?
                              WHERE id=?""",(reviewer,task_id))
            else:
                # A rejected unverified hash cannot survive into a new attempt.
                db.execute("""UPDATE tasks SET status='pending',reviewer=?,
                              worker=NULL,token=NULL,submitted_sha=NULL WHERE id=?""",
                           (reviewer,task_id))
            self._event(db,"review_accept" if accepted else "review_reject",task_id,reviewer)

    @staticmethod
    def _event(db: sqlite3.Connection, kind: str, task_id: str, actor: str) -> None:
        last = db.execute("SELECT event_sha FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last[0] if last else "0"*64
        payload = {"kind":kind,"task":task_id,"actor":actor,"previous":previous}
        encoded=canonical(payload)
        db.execute("INSERT INTO events (event_json,previous_sha,event_sha) VALUES (?,?,?)",
                   (encoded,previous,sha256(encoded.encode("ascii")).hexdigest()))
