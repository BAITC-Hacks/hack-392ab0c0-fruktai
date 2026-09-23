import type { DemoSnapshot } from '../types/demo';
import { formatDate } from '../utils/presentation';
export function DataView({ data }: { data: DemoSnapshot }) {
  return (
    <section className="data-view">
      <div className="view-heading">
        <h2>Данные расчёта</h2>
        <p>Результат FastAPI по набору {data.dataset}, сохранённый в SQLite.</p>
      </div>
      <div className="data-source">
        <div>
          <h3>{data.products.length} позиций</h3>
          <p>Время расчёта: {formatDate(data.updatedAt)}</p>
          <p>Run: {data.response.run_id}</p>
        </div>
      </div>
      <p className="data-notice">
        {data.dataset === 'demo' ? 'Набор учебный.' : 'Использованы загруженные источники.'}{' '}
        Количество рассчитано по нормализованным данным. Прямое соединение с 1С не настроено.
      </p>
      {data.metadata && (
        <>
          <p>Склад: {data.metadata.warehouse_id || 'не указан'}</p>
          <ul>
            {data.metadata.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </>
      )}
      <dl className="metadata-list">
        <div>
          <dt>Единиц к заказу</dt>
          <dd>{data.response.summary.total_units_to_order}</dd>
        </div>
        <div>
          <dt>Позиций с высоким риском</dt>
          <dd>{data.response.summary.high_risk_items}</dd>
        </div>
        <div>
          <dt>Исключённых дневных аномалий</dt>
          <dd>{data.response.summary.anomalies_removed}</dd>
        </div>
        <div>
          <dt>Позиций с компенсацией stockout</dt>
          <dd>{data.response.summary.estimated_stockout_items}</dd>
        </div>
      </dl>
      <p>
        Категория и единица отображаются из загруженного справочника. Пропуски обозначаются «Не
        указана» и «ед.».
      </p>
    </section>
  );
}
