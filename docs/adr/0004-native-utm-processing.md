# ADR 0004: Process in the scene's native UTM CRS

Status: accepted

## Context

Sentinel-2 scenes are distributed on 10 m UTM grids (Southeast Michigan
falls in zones 16T/17T). We could reproject everything to one common CRS
(e.g., Web Mercator or a fixed UTM zone) for uniform outputs, or process
each scene on its own native grid. Every reprojection resamples, and
resampling reflectance alters the values statistics are computed from.

## Decision

Process on the native grid: transform the **AOI polygon** into the scene's
CRS (cheap, exact for vector data) rather than transforming rasters. Clip
via windowed reads, align only the 20 m SCL to the 10 m band grid
(nearest-neighbor, preserving class labels), compute NDVI, and clip to the
exact AOI polygon in that CRS. Output COGs carry their scene's CRS and
transform, recorded per artifact in provenance. AOIs are small (≤600 km²),
so no mosaicking across zones is needed within one scene's processing.

## Consequences

- No unnecessary resampling of measurements: statistics are computed on
  pixel values as distributed (after DN→reflectance conversion only).
- Per-scene scalar statistics are unaffected by scenes falling in different
  UTM zones, so the time series is consistent.
- Consumers overlaying multiple scene COGs must handle per-file CRS
  (standard GIS tooling does); web previews are pre-rendered PNGs, so the UI
  is unaffected.
- If future features need pixel-wise differencing between scenes from
  different zones, an explicit, documented resampling step will be required.
