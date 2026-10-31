class EiboError(Exception):
    """Base class for controlled failures."""


class ValidationError(EiboError):
    """A scientific or engineering invariant is not satisfied."""


class ImmutabilityError(EiboError):
    """An operation would mutate an immutable record."""


class ModelResolutionError(EiboError):
    """An exact Wave model could not be verified."""


class ProviderError(EiboError):
    """A provider failure that must not be retried automatically."""


class TechnicalRetryableError(EiboError):
    """A transport-level failure eligible for a protocol-defined retry."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
