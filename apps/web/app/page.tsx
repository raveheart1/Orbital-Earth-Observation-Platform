import HeroActions from "@/components/HeroActions";
import LimitationsNote from "@/components/LimitationsNote";
import RecentAnalyses from "@/components/RecentAnalyses";
import SystemStatus from "@/components/SystemStatus";

export default function LandingPage() {
  return (
    <main id="main" className="page">
      <section className="hero">
        <p className="kicker">Reproducible satellite analysis</p>
        <h1>Orbital Earth Observation Platform</h1>
        <p className="question">
          How has vegetation health changed at a given place over time, based on
          Sentinel-2 satellite observations?
        </p>
        <p className="lede">
          Orbital computes the Normalized Difference Vegetation Index (NDVI)
          from Copernicus Sentinel-2 imagery over areas of interest you choose,
          producing per-scene statistics, before/after imagery, and a complete
          provenance record for every run. Each analysis is fully reproducible:
          the scenes considered, the pixels masked, and the software versions
          used are all recorded and downloadable.
        </p>
        <p className="lede">
          It was built around Southeast Michigan and still calls it home — the
          demonstration analysis lives there — but the pipeline runs anywhere
          Sentinel-2 observes, roughly <span className="num">56°S</span> to{" "}
          <span className="num">83°N</span>. Ten curated regions ship with it —
          four in Michigan and six more spanning Africa, Asia, Europe, and the
          Americas.
        </p>
        <HeroActions />
      </section>

      <section className="section" aria-labelledby="status-heading">
        <div className="section-head">
          <h2 id="status-heading">System status</h2>
        </div>
        <SystemStatus />
      </section>

      <section className="section" aria-labelledby="how-heading">
        <div className="section-head">
          <p className="kicker">Method</p>
          <h2 id="how-heading">How it works</h2>
        </div>
        <div className="how-grid">
          <div className="card">
            <h3>1 · Measure vegetation</h3>
            <p>
              Healthy vegetation strongly reflects near-infrared light and
              absorbs red light. NDVI captures that contrast:
            </p>
            <p className="formula">NDVI = (NIR − Red) / (NIR + Red)</p>
            <p>
              Values range from −1 to +1. Dense, healthy vegetation typically
              scores <span className="num">0.6–0.9</span>, sparse vegetation and
              bare soil sit lower, and water is negative.
            </p>
          </div>
          <div className="card">
            <h3>2 · Observe from orbit</h3>
            <p>
              The ESA/Copernicus Sentinel-2 mission images land surfaces at{" "}
              <span className="num">10 m</span> resolution in the red and
              near-infrared bands, revisiting mid-latitudes roughly every{" "}
              <span className="num">5</span> days.
            </p>
            <p>
              Orbital reads atmospherically corrected surface reflectance
              (Level-2A) directly from the Microsoft Planetary Computer STAC
              catalog — only the raster windows covering your area are fetched.
            </p>
          </div>
          <div className="card">
            <h3>3 · Mask, aggregate, record</h3>
            <p>
              Clouds, cloud shadows, and snow are masked using the Sentinel-2
              Scene Classification Layer (SCL) before any statistic is computed.
            </p>
            <p>
              Per-scene NDVI statistics form a time series, and every step —
              scene selection, mask policy, software versions — is captured in a
              downloadable provenance document.
            </p>
          </div>
        </div>
      </section>

      <section className="section" aria-labelledby="regions-heading">
        <div className="section-head">
          <p className="kicker">Curated regions</p>
          <h2 id="regions-heading">Where it looks</h2>
        </div>
        <div className="how-grid">
          <div className="card">
            <h3>Michigan — home ground</h3>
            <p>
              <strong>Southeast Michigan Demonstration Region</strong> — suburban
              Oakland County, and the subject of the committed demonstration
              analysis.
            </p>
            <p>
              <strong>Detroit Urban Core</strong> — dense impervious surface
              against parks and street trees.
            </p>
            <p>
              <strong>Sleeping Bear Dunes Shoreline</strong> — bare sand, water,
              and vegetated dune side by side.
            </p>
            <p>
              <strong>Hartwick Pines Forest</strong> — conifer cover, whose
              seasonal cycle is damped next to deciduous stands.
            </p>
          </div>
          <div className="card">
            <h3>Global — four more continents</h3>
            <p>
              <strong>Nile Delta Farmland</strong> (Egypt) — irrigated cropland
              meeting desert; three Sentinel-2 tiles mosaicked into one grid.
            </p>
            <p>
              <strong>Amazon Deforestation Frontier</strong> (Brazil) — the
              &ldquo;fishbone&rdquo; of roads and clearings against intact
              canopy.
            </p>
            <p>
              <strong>Central Valley Cropland</strong> (California) — neighbouring
              irrigated fields at opposite NDVI extremes on the same day.
            </p>
            <p>
              <strong>Okavango Delta</strong> (Botswana) — a flood pulse arriving
              months after the rains that caused it.
            </p>
            <p>
              <strong>Mekong Delta Rice</strong> (Vietnam) — two to three crops a
              year, so NDVI cycles several times within one.
            </p>
            <p>
              <strong>Doñana Wetlands</strong> (Spain) — a Mediterranean marsh
              drying through summer beside irrigation that does not.
            </p>
          </div>
        </div>
        <p className="panel-note" style={{ marginTop: "1rem" }}>
          Each curated region covers about{" "}
          <span className="num">137 km²</span>, so processing cost is comparable
          between them. You can also draw your own area anywhere Sentinel-2
          observes — its orbit images land between roughly 56°S and 83°N, so the
          poles and the open ocean are out of reach.
        </p>
      </section>

      <section className="section" aria-labelledby="recent-heading">
        <div className="section-head">
          <h2 id="recent-heading">Recent analyses</h2>
        </div>
        <RecentAnalyses />
      </section>

      <section className="section" aria-label="Scientific limitations">
        <LimitationsNote />
      </section>
    </main>
  );
}
