class RewindError(Exception):
    """Base exception for Rewind platform."""
    pass

class NotFoundError(RewindError):
    """Raised when a requested resource is not found."""
    pass

class ExecutionError(RewindError):
    """Raised when a test execution fails unexpectedly."""
    pass
