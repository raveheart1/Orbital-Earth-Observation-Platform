"""Scientific core for the Orbital Earth Observation Platform.

This package contains everything needed to turn a Sentinel-2 STAC search into
validated NDVI measurements: scene discovery and deterministic selection,
Scene Classification Layer (SCL) masking, windowed cloud-optimized raster
reads, NDVI computation, statistics, Cloud Optimized GeoTIFF and preview
outputs, and machine-readable provenance.

It deliberately has no database or Azure dependencies so that the science is
testable and reusable outside the platform (see ``notebooks/``).
"""

PROCESSING_VERSION = "1.0.0"
SCENE_SELECTION_ALGORITHM = "temporal-stratified-lowest-cloud"
SCENE_SELECTION_VERSION = "1.0.0"

__version__ = PROCESSING_VERSION
