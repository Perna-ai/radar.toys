export default function HeroSection() {
  return (
    <header className="hero">
      <div className="blob blob-1" />
      <div className="blob blob-2" />
      <div className="blob blob-3" />

      <div className="hero-inner">
        <div className="logo">
          <div className="logo-icon">🎯</div>
          <div className="logo-text">
            RADAR<span className="logo-dot">.</span>
            <span className="logo-tld">TOYS</span>
          </div>
        </div>
        <p className="hero-tagline">Know first. Buy first.</p>
        <div className="hero-badge">
          <span className="badge-dot" />
          TREND DATA UPDATED HOURLY
        </div>
        <h1 className="hero-headline">
          Know what kids want<br />
          <span className="hero-highlight">before they ask.</span>
        </h1>
        <p className="hero-sub">
          Real-time signals from Google Trends, Amazon, and eBay —
          so you buy at retail before resale prices explode.
        </p>
      </div>
    </header>
  );
}
