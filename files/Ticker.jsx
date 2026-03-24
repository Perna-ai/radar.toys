export default function Ticker({ toys, content }) {
  // Build ticker items from live toy data, fall back to defaults
  const items =
    toys.length > 0
      ? toys.flatMap((toy) => {
          const hook = content?.[toy.toy_id]?.ticker_hook;
          return hook
            ? [hook]
            : [`${toy.status?.toUpperCase()}: ${toy.name.toUpperCase()}`];
        })
      : [
          "🔥🔥 NEEDOH NICE CUBE — KIDS ARE LOSING THEIR MINDS",
          "💸 $7 AT TARGET. $95 ON EBAY. SUGAR SKULL CATS ARE BLOWING UP",
          "🐉✨ JELLYCAT LAZULIA DRAGON JUST DROPPED — GET IT NOW",
          "⚡🃏 POKÉMON 30TH ANNIVERSARY PACKS SELL OUT IN MINUTES",
          "📈 SEARCH FOR NEEDOH UP 840% THIS WEEK",
          "🎯 RADAR.TOYS — KNOW FIRST. BUY FIRST.",
        ];

  // Duplicate for seamless loop
  const doubled = [...items, ...items];

  return (
    <div className="ticker-wrap">
      <div className="ticker-inner">
        {doubled.map((item, i) => (
          <span key={i}>
            {item}
            <span className="ticker-sep">●</span>
          </span>
        ))}
      </div>
    </div>
  );
}
