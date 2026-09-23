import type { DemoSnapshot } from '../types/demo';
import { formatDate } from '../utils/presentation';
export function DataView({ data }: { data: DemoSnapshot }) {
  return <section className="data-view"><div className="view-heading"><h2>Данные расчёта</h2>
    <p>Результат FastAPI по учебному набору demo, сохранённый в SQLite.</p></div>
    <div className="data-source"><div><h3>{data.products.length} позиций</h3><p>Время расчёта: {formatDate(data.updatedAt)}</p><p>Run: {data.response.run_id}</p></div></div>
    <p className="data-notice">Набор учебный, не синхронизирован с 1С. Количество и причины рассчитаны по шести CSV, а не взяты из UI-примера.</p>
    <dl className="metadata-list">
      <div><dt>Единиц к заказу</dt><dd>{data.response.summary.total_units_to_order}</dd></div>
      <div><dt>Позиций с высоким риском</dt><dd>{data.response.summary.high_risk_items}</dd></div>
      <div><dt>Исключённых дневных аномалий</dt><dd>{data.response.summary.anomalies_removed}</dd></div>
      <div><dt>Позиций с компенсацией stockout</dt><dd>{data.response.summary.estimated_stockout_items}</dd></div>
    </dl><p>API не передаёт категорию, физическую единицу и точную дату поставки: они обозначены как «Не указана», «ед.» и не подменяются предположениями.</p>
  </section>;
}
