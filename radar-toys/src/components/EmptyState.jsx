export default function EmptyState({ filter, onReset }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">🔍</div>
      <h3>No toys found</h3>
      <p>
        {filter === "all" 
          ? "No products available right now. Check back soon!"
          : `No toys in the "${filter}" category yet.`
        }
      </p>
      {filter !== "all" && (
        <button className="empty-state-btn" onClick={onReset}>
          View all toys
        </button>
      )}
    </div>
  );
}
