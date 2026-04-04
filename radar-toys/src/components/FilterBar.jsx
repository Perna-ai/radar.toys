const LABEL_MAP = {
  all: "All Toys",
  "Squishies": "🫧 Squishies",
  "Plush": "🧸 Plush",
  "Cards": "🃏 Cards",
  "Dolls": "👧 Dolls",
  "Collectibles": "🎯 Collectibles",
  "Action Figures": "🤖 Figures",
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
