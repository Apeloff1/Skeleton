from skeleton.jeeves.memory.index import MemoryEntry,MemoryTier,validate_memory

def test_memory_fingerprint_and_validation():
    x=MemoryEntry("k","v",MemoryTier.CANONICAL)
    assert x.fingerprint==x.fingerprint
    assert validate_memory((x,))==(x.fingerprint,)

def test_memory_duplicate_key_is_rejected():
    x=MemoryEntry("k","v")
    try: validate_memory((x,x))
    except ValueError as e: assert "duplicate" in str(e)
    else: raise AssertionError("duplicate accepted")
