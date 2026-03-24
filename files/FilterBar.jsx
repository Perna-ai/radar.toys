const LABEL_MAP = {
  all: "All Toys",
  "Sensory / Squishies": "🫧 Squishies",
  "Collectible Plush": "🧸 Plush",
  "Trading Cards": "🃏 Cards",
};

export default function FilterBar({ categories, active, onChange }) {
  return (
    <div className="filter-bar">
      {categories.map((cat) => (
        <button
          key={cat}
          className={`filter-chip ${active === cat ? "active" : ""}`}
          onClick={() => onChange(cat)}
        >
          {LABEL_MAP[cat] || cat}
        </button>
      ))}
    </div>
  );
}
