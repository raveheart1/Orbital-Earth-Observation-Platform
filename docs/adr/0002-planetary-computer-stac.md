# ADR 0002: Microsoft Planetary Computer as the STAC source

Status: accepted

## Context

The platform needs Sentinel-2 L2A surface reflectance with a queryable
catalog, cloud-optimized assets suitable for HTTP range reads, and no
per-request data fees. Candidates included the Planetary Computer, AWS Earth
Search, and the Copernicus Data Space Ecosystem.

## Decision

Use the Microsoft Planetary Computer STAC API
(`https://planetarycomputer.microsoft.com/api/stac/v1`, collection
`sentinel-2-l2a`). Assets are COGs supporting windowed reads; the catalog is
a standards-compliant STAC API usable via `pystac-client`; access is free
with lightweight URL signing via the `planetary-computer` SDK. Signing is
isolated in one function (`earth_observation.stac.sign_href`), called
immediately before access; signed URLs are never persisted and provenance
records the unsigned hrefs
([data-provenance.md](../data-provenance.md#unsigned-vs-signed-url-policy)).

## Consequences

- The science core stays portable: only the signing step is
  provider-specific, so switching catalogs means changing an endpoint and a
  sign function.
- PC data lives in West Europe; the default eastus deployment accepts
  cross-region reads ([cost-and-scaling.md](../cost-and-scaling.md#region-trade-off-eastus-vs-westeurope)).
- We depend on PC availability and its token endpoint; both are wrapped in
  retry logic and classified as transient failures.
- Required attribution: "Contains modified Copernicus Sentinel data,
  processed by ESA, accessed via the Microsoft Planetary Computer."
