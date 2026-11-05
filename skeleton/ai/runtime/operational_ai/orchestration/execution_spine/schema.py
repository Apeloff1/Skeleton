"""SQL invariants: every turn and its outbound event share one transaction."""
SCHEMA_VERSION=1
DDL=(
 """CREATE TABLE IF NOT EXISTS principals (
    principal TEXT PRIMARY KEY, identity_json BLOB NOT NULL,
    created_ns INTEGER NOT NULL CHECK(created_ns>0))""",
 """CREATE TABLE IF NOT EXISTS sessions (
    session TEXT PRIMARY KEY, principal TEXT NOT NULL REFERENCES principals(principal),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
    state TEXT NOT NULL CHECK(state IN('open','closed')),
    created_ns INTEGER NOT NULL CHECK(created_ns>0))""",
 """CREATE TABLE IF NOT EXISTS requests (
    session TEXT NOT NULL REFERENCES sessions(session), request_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL, generation_nonce TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN('pending','committed','held','cancelled')),
    owner_token INTEGER NOT NULL DEFAULT 0 CHECK(owner_token>=0),
    lease_deadline_ns INTEGER, created_ns INTEGER NOT NULL, updated_ns INTEGER NOT NULL,
    PRIMARY KEY(session,request_id))""",
 """CREATE TABLE IF NOT EXISTS turns (
    session TEXT NOT NULL REFERENCES sessions(session), request_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision>0),
    prompt BLOB NOT NULL, response BLOB NOT NULL,
    receipt_json BLOB NOT NULL, receipt_sha256 TEXT NOT NULL,
    committed_ns INTEGER NOT NULL,
    PRIMARY KEY(session,request_id), UNIQUE(session,revision),
    FOREIGN KEY(session,request_id) REFERENCES requests(session,request_id))""",
 """CREATE TABLE IF NOT EXISTS outbox (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT NOT NULL UNIQUE,
    stream TEXT NOT NULL, kind TEXT NOT NULL,
    event_json BLOB NOT NULL, event_sha256 TEXT NOT NULL,
    acked INTEGER NOT NULL DEFAULT 0 CHECK(acked IN (0,1)),
    created_ns INTEGER NOT NULL)""",
 """CREATE TABLE IF NOT EXISTS deliveries (
    consumer TEXT NOT NULL, event_key TEXT NOT NULL,
    event_sha256 TEXT NOT NULL, consumed_ns INTEGER NOT NULL,
    PRIMARY KEY(consumer,event_key))""",
 """CREATE TABLE IF NOT EXISTS chain (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT, stream TEXT NOT NULL,
    entry_kind TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
    previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL,
    entry_json BLOB NOT NULL)""",
 """CREATE TABLE IF NOT EXISTS effects (
    grant_id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES sessions(session),
    principal TEXT NOT NULL REFERENCES principals(principal), tool TEXT NOT NULL,
    args_sha256 TEXT NOT NULL, status TEXT NOT NULL
    CHECK(status IN('attempting','completed','held')),
    started_ns INTEGER NOT NULL, completed_ns INTEGER,
    response_sha256 TEXT)""",
 """CREATE TABLE IF NOT EXISTS controls (
    control TEXT PRIMARY KEY, value TEXT NOT NULL)""",
 """CREATE INDEX IF NOT EXISTS requests_state_idx ON requests(state,updated_ns)""",
 """CREATE INDEX IF NOT EXISTS outbox_ready_idx ON outbox(acked,sequence)""",
 """CREATE INDEX IF NOT EXISTS chain_stream_idx ON chain(stream,sequence)""",
)
