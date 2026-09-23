export function LoadingState() {
  return (
    <div className="loading-state" role="status" aria-label="Загрузка рекомендаций">
      <p>Загрузка рекомендаций…</p>
      <div className="loading-kpis">
        {[1, 2, 3, 4, 5].map((key) => (
          <div key={key} className="skeleton" />
        ))}
      </div>
      <div className="loading-table">
        {[1, 2, 3, 4, 5].map((key) => (
          <div key={key} className="skeleton" />
        ))}
      </div>
    </div>
  );
}
