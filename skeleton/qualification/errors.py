class QualificationError(Exception):
    """Base error for the qualification harness."""


class SchemaError(QualificationError):
    """A case or evidence document does not match its schema."""

    def __init__(self, path: str, message: str):
        self.path = path
        super().__init__(f"{path}: {message}")
