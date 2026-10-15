class ProviderError(Exception):
    """Vendor HTTP, parse, or configuration failure. Not an HTTP API error."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        # Validation and unknown-symbol failures do not improve on retry.
        self.retryable = retryable
