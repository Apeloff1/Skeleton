"""Integer threshold arithmetic; not an authenticated consensus protocol."""
def quorum(total: int) -> int:
    if type(total) is not int or not 1 <= total <= (1 << 63) - 1:
        raise ValueError("total must be a bounded positive integer")
    return total // 2 + 1


def reached(total: int, votes: int) -> bool:
    threshold = quorum(total)
    if type(votes) is not int or not 0 <= votes <= total:
        raise ValueError("votes out of range")
    return votes >= threshold
