import type { Metadata } from "next";
import Link from "next/link";
import SiteNav from "@/components/SiteNav";
import "./globals.css";

const GITHUB_URL = "https://github.com/raveheart1/Orbital-Earth-Observation-Platform";

export const metadata: Metadata = {
  title: {
    default: "Orbital Earth Observation Platform",
    template: "%s · Orbital Earth Observation Platform",
  },
  description:
    "Reproducible NDVI analyses of Sentinel-2 observations over Southeast Michigan: how has vegetation health changed over time?",
};

function OrbitGlyph() {
  return (
    <svg
      className="orbit-glyph"
      width="30"
      height="30"
      viewBox="0 0 30 30"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="15" cy="15" r="6.5" stroke="currentColor" strokeWidth="1.8" />
      <ellipse
        cx="15"
        cy="15"
        rx="13"
        ry="5"
        stroke="currentColor"
        strokeWidth="1.2"
        transform="rotate(-24 15 15)"
      />
      <circle cx="26.2" cy="9.4" r="1.9" fill="currentColor" />
    </svg>
  );
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <header className="site-header">
          <div className="inner">
            <Link href="/" className="wordmark">
              <OrbitGlyph />
              <span className="name">
                Orbital
                <span className="sub">Earth Observation Platform</span>
              </span>
            </Link>
            <span className="spacer" aria-hidden="true" />
            <SiteNav />
          </div>
        </header>
        {children}
        <footer className="site-footer">
          <div className="inner">
            <p>
              Contains modified Copernicus Sentinel data, processed by ESA,
              accessed via Microsoft Planetary Computer.
            </p>
            <p>Basemap tiles © OpenStreetMap contributors.</p>
            <p>
              Open source on{" "}
              <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
                GitHub
              </a>
              . NDVI results describe observed spectral change, not causes — see
              the methodology and limitations documents before drawing
              conclusions.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
