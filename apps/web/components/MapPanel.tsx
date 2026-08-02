"use client";

import dynamic from "next/dynamic";

/**
 * Client-only wrapper around the MapLibre map. MapLibre touches window/WebGL
 * at import time, so it must never be server-rendered.
 */
const MapPanel = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => (
    <div className="map-shell">
      <div className="map-placeholder">Loading map…</div>
    </div>
  ),
});

export default MapPanel;
