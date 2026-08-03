"""Scientific core for the Orbital Earth Observation Platform.

This package contains everything needed to turn a Sentinel-2 STAC search into
validated NDVI measurements: scene discovery and deterministic selection,
Scene Classification Layer (SCL) masking, windowed cloud-optimized raster
reads, NDVI computation, statistics, Cloud Optimized GeoTIFF and preview
outputs, and machine-readable provenance.

It deliberately has no database or Azure dependencies so that the science is
testable and reusable outside the platform (see ``notebooks/``).
"""

#: Bumped to 2.0.0 when processing moved to a per-analysis canonical grid with
#: acquisition-level mosaicking (see docs/adr/0007-canonical-analysis-grid.md).
#: Results produced by 1.x are NOT comparable with 2.x for AOIs that cross
#: Sentinel-2 tile boundaries.
PROCESSING_VERSION = "2.0.0"

__version__ = PROCESSING_VERSION
