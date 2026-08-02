"""SCL mask policy tests."""

from __future__ import annotations

import numpy as np

from earth_observation.masking import scl_valid_mask
from earth_observation.types import DEFAULT_MASKED_SCL_CLASSES, SCLClass


def test_default_policy_masks_clouds_and_keeps_surface():
    scl = np.array(
        [
            [SCLClass.VEGETATION, SCLClass.CLOUD_HIGH_PROBABILITY],
            [SCLClass.WATER, SCLClass.CLOUD_SHADOWS],
            [SCLClass.NOT_VEGETATED, SCLClass.THIN_CIRRUS],
            [SCLClass.CAST_SHADOWS, SCLClass.SNOW_OR_ICE],
        ],
        dtype=np.uint8,
    )
    valid = scl_valid_mask(scl, DEFAULT_MASKED_SCL_CLASSES)
    # Surface classes retained (vegetation, water, bare, terrain shadow)...
    assert valid[0, 0] and valid[1, 0] and valid[2, 0] and valid[3, 0]
    # ...contamination masked (cloud, cloud shadow, cirrus, snow).
    assert not valid[0, 1] and not valid[1, 1] and not valid[2, 1] and not valid[3, 1]


def test_nodata_and_defective_always_masked_by_default():
    scl = np.array([[0, 1, 4]], dtype=np.uint8)
    valid = scl_valid_mask(scl, DEFAULT_MASKED_SCL_CLASSES)
    assert list(valid[0]) == [False, False, True]


def test_float_scl_with_nan_nodata():
    """rioxarray masked reads deliver SCL as float with NaN nodata."""
    scl = np.array([[np.nan, 4.0, 9.0]], dtype=np.float32)
    valid = scl_valid_mask(scl, DEFAULT_MASKED_SCL_CLASSES)
    assert list(valid[0]) == [False, True, False]


def test_custom_policy():
    scl = np.array([[SCLClass.WATER, SCLClass.VEGETATION]], dtype=np.uint8)
    valid = scl_valid_mask(scl, [SCLClass.WATER])
    assert list(valid[0]) == [False, True]


def test_empty_policy_keeps_everything_finite():
    scl = np.array([[0, 9, 11]], dtype=np.uint8)
    valid = scl_valid_mask(scl, [])
    assert valid.all()
