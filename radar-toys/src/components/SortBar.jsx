export default function SortBar({ sortBy, onChange }) {
  return (
    <div className="sort-bar">
      <label className="sort-label">Sort by:</label>
      <select 
        className="sort-select" 
        value={sortBy} 
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="heat-desc">🔥 Hottest First</option>
        <option value="heat-asc">❄️ Coolest First</option>
        <option value="price-asc">💰 Price: Low to High</option>
        <option value="price-desc">💎 Price: High to Low</option>
        <option value="name-asc">🔤 Name: A-Z</option>
      </select>
    </div>
  );
}
