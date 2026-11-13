"""Independent versioned metadata CAS with no blind overwrite."""
from ..contracts.canonical import dumps, loads
from ..contracts.errors import ContractError, ConflictError
from ..contracts.identity import identifier

class Revisions:

    def __init__(self, db):
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS pf_revisions(key TEXT PRIMARY KEY,version INTEGER NOT NULL,body BLOB NOT NULL)')

    def read(self, key):
        identifier(key)
        row = self.db.execute('SELECT version,body FROM pf_revisions WHERE key=?', (key,)).fetchone()
        return (row[0], loads(row[1])) if row else (0, None)

    def write(self, key, expected_version, body):
        identifier(key)
        raw = dumps(body)
        if type(expected_version) is not int or expected_version < 0:
            raise ContractError('invalid expected metadata revision')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            version, _ = self.read(key)
            if expected_version != version:
                raise ConflictError('metadata revision mismatch')
            self.db.execute('INSERT INTO pf_revisions VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET version=excluded.version,body=excluded.body', (key, version + 1, raw))
            self.db.execute('COMMIT')
            return version + 1
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
