"""Scene Classification Layer (SCL) masking."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import numpy.typing as npt


def scl_valid_mask(
    scl: npt.NDArray[np.integer] | npt.NDArray[np.floating],
    masked_classes: Iterable[int],
) -> npt.NDArray[np.bool_]:
    """Boolean array that is True where the SCL class is NOT in ``masked_classes``.

    ``scl`` may arrive as float (rioxarray with ``masked=True`` promotes to
    float and uses NaN for nodata); NaN cells are always invalid.
    """
    arr = np.asarray(scl)
    if arr.dtype.kind == "f":
        finite = np.isfinite(arr)
        classes = np.where(finite, arr, -1).astype(np.int16)
    else:
        finite = np.ones(arr.shape, dtype=bool)
        classes = arr.astype(np.int16)
    valid = finite.copy()
    for cls in masked_classes:
        valid &= classes != np.int16(cls)
    return valid
