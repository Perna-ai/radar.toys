import { useState } from "react";

const STATUS_COLORS = {
  "Peak Demand": { bg: "var(--coral)", label: "#fff" },
  "Rising Fast": { bg: "var(--orange)", label: "#fff" },
  Emerging: { bg: "var(--purple)", label: "#fff" },
};

const STOCK_COLORS = {
  Critical: "var(--coral)",
  High: "var(--orange)",
  Medium: "var(--yellow)",
  Low: "#34C759",
  Unknown: "#999",
};

const TAG_STYLES = {
  "SOLD OUT RISK": { bg: "rgba(255,94,98,0.12)", color: "var(--coral)", border: "rgba(255,94,98,0.3)" },
  "LIMITED STOCK": { bg: "rgba(255,149,0,0.12)", color: "var(--orange)", border: "rgba(255,149,0,0.3)" },
  "GET AHEAD":     { bg: "rgba(155,48,255,0.12)", color: "var(--purple)", border: "rgba(155,48,255,0.3)" },
  "WATCH NOW":     { bg: "rgba(255,205,60,0.15)", color: "#B8860B", border: "rgba(255,205,60,0.4)" },
  TRENDING:        { bg: "rgba(52,199,89,0.12)", color: "#1a7a35", border: "rgba(52,199,89,0.3)" },
};

export default function ToyCard({ toy, content, showPrediction }) {
  const [expanded, setExpanded] = useState(false);

  const status = toy.status || "Emerging";
  const statusStyle = STATUS_COLORS[status] || STATUS_COLORS["Emerging"];
  const stockColor = STOCK_COLORS[toy.stock_risk] || STOCK_COLORS["Unknown"];
  const tag = content?.card_tag || "TRENDING";
  const tagStyle = TAG_STYLES[tag] || TAG_STYLES["TRENDING"];
  const retailers = Array.isArray(toy.retailers)
    ? toy.retailers
    : JSON.parse(toy.retailers || "[]");

  const heatPct = Math.min(100, Math.max(0, toy.heat_score || 0));

  return (
    <article className="toy-card" onClick={() => setExpanded((p) => !p)}>
      {/* Heat bar */}
      <div className="heat-bar-track">
        <div
          className="heat-bar-fill"
          style={{
            width: `${heatPct}%`,
            background: heatPct >= 80
              ? "linear-gradient(90deg, var(--coral), var(--orange))"
              : heatPct >= 55
              ? "linear-gradient(90deg, var(--orange), var(--yellow))"
              : "linear-gradient(90deg, var(--purple), var(--purple))",
          }}
        />
      </div>

      <div className="card-inner">
        {/* Header row */}
        <div className="card-header">
          <div className="card-meta">
            <span
              className="status-badge"
              style={{ background: statusStyle.bg, color: statusStyle.label }}
            >
              {status}
            </span>
            <span
              className="tag-badge"
              style={{
                background: tagStyle.bg,
                color: tagStyle.color,
                border: `1.5px solid ${tagStyle.border}`,
              }}
            >
              {tag}
            </span>
          </div>
          <div className="heat-score">
            <span className="heat-number">{heatPct.toFixed(0)}</span>
            <span className="heat-label">HEAT</span>
          </div>
        </div>

        {/* Toy image placeholder */}
        {toy.image_url && (
          <div className="card-image">
            <img src={toy.image_url} alt={toy.name} loading="lazy" />
          </div>
        )}

        {/* Toy name + brand */}
        <div className="card-body">
          <p className="toy-brand">{toy.brand}</p>
          <h3 className="toy-name">{toy.name}</h3>
          <p className="toy-age">Ages {toy.age_range}</p>

          {content?.card_description && (
            <p className="card-description">{content.card_description}</p>
          )}
        </div>

        {/* Price + stock row */}
        <div className="card-stats">
          <div className="stat">
            <span className="stat-label">RETAIL</span>
            <span className="stat-value">${toy.retail_price?.toFixed(2)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">STOCK RISK</span>
            <span className="stat-value" style={{ color: stockColor }}>
              {toy.stock_risk}
            </span>
          </div>
          {toy.resale_flag && (
            <div className="stat resale-stat">
              <span className="stat-label">⚠️ RESALE</span>
              <span className="stat-value resale-value">2x+</span>
            </div>
          )}
        </div>

        {/* Expandable: where to buy + parent tip */}
        {expanded && (
          <div className="card-expanded">
            {content?.parent_tip && (
              <div className="parent-tip">
                <span className="tip-label">💡 Parent tip</span>
                <p>{content.parent_tip}</p>
              </div>
            )}
            {retailers.length > 0 && (
              <div className="retailers">
                <span className="retailers-label">Where to buy</span>
                <div className="retailer-chips">
                  {retailers.map((r) => (
                    <span key={r} className="retailer-chip">{r}</span>
                  ))}
                </div>
              </div>
            )}
            {showPrediction && content?.prediction_narrative && (
              <div className="prediction-box">
                <span className="prediction-label">🌱 Breakout prediction</span>
                <p>{content.prediction_narrative}</p>
              </div>
            )}
          </div>
        )}

        <button className="expand-btn">
          {expanded ? "Less ↑" : "Where to buy ↓"}
        </button>
      </div>
    </article>
  );
}
