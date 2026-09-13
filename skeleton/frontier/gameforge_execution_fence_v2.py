"""One-shot fence preventing duplicate terminal application."""
class ExecutionFenceV2:
    def __init__(self):
        self._closed = False

    @property
    def closed(self):
        return self._closed

    def acquire(self):
        if self._closed:
            return False
        self._closed = True
        return True
