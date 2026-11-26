"""Compatibility CLI for the canonical shift-supervisor package."""
from skeleton.automation.shift_supervisor.__main__ import main

if __name__ == "__main__":
    main()

def _context():
    return {"ok": True}

def _read_state():
    return {"ok": True}

def _write_state(state):
    return {"ok": True}
