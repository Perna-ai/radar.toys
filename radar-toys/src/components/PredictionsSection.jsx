export default function PredictionsSection({ toys, content }) {
  const breakouts = toys.filter((t) => t.breakout_flag);
  if (breakouts.length === 0) return null;

  return (
    <section className="predictions-section">
      <div className="section-header">
        <h2 className="section-title">🌱 On Our Radar</h2>
        <p className="section-subtitle">Our model says these break out soon</p>
      </div>
      <div className="predictions-grid">
        {breakouts.map((toy) => {
          const c = content[toy.toy_id];
          return (
            <div key={toy.toy_id} className="prediction-card">
              <div className="prediction-header">
                <span className="prediction-toy-name">{toy.name}</span>
                <span className="prediction-heat">{toy.heat_score?.toFixed(0)} HEAT</span>
              </div>
              {c?.prediction_narrative && (
                <p className="prediction-text">{c.prediction_narrative}</p>
              )}
              <div className="prediction-signals">
                <span>🔍 Search accelerating</span>
                {toy.resale_flag && <span>💸 Resale premium detected</span>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
