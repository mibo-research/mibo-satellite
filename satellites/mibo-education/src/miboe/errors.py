class MiboeError(Exception):
    """Base class for controlled failures."""


class ValidationError(MiboeError):
    """A scientific or engineering invariant is not satisfied."""


class ImmutabilityError(MiboeError):
    """An operation would mutate an immutable record."""


class ModelResolutionError(MiboeError):
    """An exact Wave model could not be verified."""


class ProviderError(MiboeError):
    """A provider failure that must not be retried automatically."""


class TechnicalRetryableError(MiboeError):
    """A transport-level failure eligible for a protocol-defined retry."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
