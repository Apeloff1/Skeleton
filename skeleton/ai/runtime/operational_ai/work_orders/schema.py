"""One bounded SQLite authority for durable work and token reservations."""
DDL=(
"""CREATE TABLE IF NOT EXISTS controls(
  key TEXT PRIMARY KEY,value TEXT NOT NULL) STRICT""",
"""CREATE TABLE IF NOT EXISTS budgets(
  tenant TEXT PRIMARY KEY,ceiling INTEGER NOT NULL CHECK(ceiling>0),
  reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0),
  consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed>=0),
  revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
  CHECK(consumed+reserved<=ceiling)) STRICT""",
"""CREATE TABLE IF NOT EXISTS jobs(
  job_id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,subject TEXT NOT NULL,
  model_sha TEXT NOT NULL,tokenizer_sha TEXT NOT NULL,
  session_id TEXT NOT NULL,request_id TEXT NOT NULL,
  prompt_sha TEXT NOT NULL,request_sha TEXT NOT NULL,
  seed INTEGER NOT NULL,temperature REAL NOT NULL,max_output INTEGER NOT NULL,
  status TEXT NOT NULL,revision INTEGER NOT NULL CHECK(revision>=1),
  lease_sha TEXT,token_reservation INTEGER NOT NULL DEFAULT 0,
  tokens_charged INTEGER NOT NULL DEFAULT 0,output_sha TEXT,
  state_sha TEXT NOT NULL DEFAULT '',updated_ns INTEGER NOT NULL,
  UNIQUE(tenant,subject,model_sha,session_id,request_id),
  FOREIGN KEY(tenant) REFERENCES budgets(tenant)) STRICT""",
"""CREATE INDEX IF NOT EXISTS jobs_actor ON jobs(tenant,subject,status,updated_ns)""",
"""CREATE TABLE IF NOT EXISTS events(
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(job_id),
  kind TEXT NOT NULL,body BLOB NOT NULL,body_sha TEXT NOT NULL,
  previous_sha TEXT NOT NULL,event_sha TEXT NOT NULL UNIQUE,
  state_sha TEXT NOT NULL,created_ns INTEGER NOT NULL) STRICT""",
"""CREATE TABLE IF NOT EXISTS outbox(
  event_sha TEXT PRIMARY KEY REFERENCES events(event_sha),
  job_id TEXT NOT NULL REFERENCES jobs(job_id),
  acknowledged INTEGER NOT NULL DEFAULT 0 CHECK(acknowledged IN (0,1)),
  acknowledged_ns INTEGER) STRICT""",
"""CREATE TABLE IF NOT EXISTS admissions(
  nonce_sha TEXT PRIMARY KEY,
  job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
  request_sha TEXT NOT NULL,
  tenant TEXT NOT NULL,subject TEXT NOT NULL,
  consumed_ns INTEGER NOT NULL CHECK(consumed_ns>=0)) STRICT""",
)
