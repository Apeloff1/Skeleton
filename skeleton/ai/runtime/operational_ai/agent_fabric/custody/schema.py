"""SQLite tables scoped to the existing authoritative SpineDatabase."""
DDL=(
"""CREATE TABLE IF NOT EXISTS agent_plans(plan_id TEXT PRIMARY KEY, owner TEXT NOT NULL, plan_sha TEXT NOT NULL, plan_json BLOB NOT NULL, state TEXT NOT NULL, created_ns INTEGER NOT NULL, updated_ns INTEGER NOT NULL, CHECK(state IN ('active','complete','held','cancelled')))""",
"""CREATE TABLE IF NOT EXISTS agent_steps(plan_id TEXT NOT NULL REFERENCES agent_plans(plan_id) ON DELETE CASCADE, step_id TEXT NOT NULL, state TEXT NOT NULL, kind TEXT NOT NULL, digest TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0, fence INTEGER NOT NULL DEFAULT 0, worker TEXT, result_json BLOB, result_sha TEXT, reason TEXT, updated_ns INTEGER NOT NULL, PRIMARY KEY(plan_id,step_id), CHECK(state IN ('pending','running','complete','held','cancelled')))""",
"""CREATE TABLE IF NOT EXISTS agent_events(plan_id TEXT NOT NULL REFERENCES agent_plans(plan_id) ON DELETE CASCADE, sequence INTEGER NOT NULL, kind TEXT NOT NULL, step_id TEXT, prior_sha TEXT NOT NULL, event_sha TEXT NOT NULL, event_json BLOB NOT NULL, PRIMARY KEY(plan_id,sequence))""",
"""CREATE TABLE IF NOT EXISTS agent_approvals(plan_id TEXT NOT NULL, step_id TEXT NOT NULL, approval_sha TEXT NOT NULL, grant_json BLOB NOT NULL, redeemed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(plan_id,step_id), FOREIGN KEY(plan_id,step_id) REFERENCES agent_steps(plan_id,step_id))""",
"""CREATE INDEX IF NOT EXISTS agent_steps_ready_idx ON agent_steps(state,plan_id,step_id)""",
"""CREATE INDEX IF NOT EXISTS agent_events_by_plan ON agent_events(plan_id,sequence)""",
)
def install(db):
    with db.transaction() as conn:
        for sql in DDL:conn.execute(sql)
