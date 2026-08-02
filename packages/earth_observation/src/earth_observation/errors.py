"""Typed error hierarchy separating user errors, data errors, and transient faults.

The worker uses this taxonomy to decide retry behaviour: ``TransientError``
is retryable, everything else is deterministic and must not be retried
indefinitely.
"""


class EarthObservationError(Exception):
    """Base class for all errors raised by this package."""

    category = "internal"


class UserInputError(EarthObservationError):
    """The request itself is invalid (geometry, dates, limits). Never retried."""

    category = "user_input"


class DataError(EarthObservationError):
    """The upstream data cannot satisfy the request (no scenes, missing assets,

    fully masked pixels). Deterministic for a given catalog state; not retried."""

    category = "data"


class AssetKeysError(DataError):
    """A STAC item does not expose the expected asset keys."""


class NoUsableScenesError(DataError):
    """The search or selection produced no scenes that can be processed."""


class TransientError(EarthObservationError):
    """Network / remote-service faults that are worth retrying."""

    category = "transient"
