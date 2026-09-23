import type { WorkspaceController } from '../../hooks/useWorkspace';
import type { DemoProduct } from '../../types/demo';
import { initialFilters, quantitySummary } from '../../utils/presentation';

export function SuppliersView({ workspace }: { workspace: WorkspaceController }) {
  const groups = new Map<string, DemoProduct[]>();
  for (const product of workspace.products) {
    const rows = groups.get(product.supplierId) ?? [];
    rows.push(product);
    groups.set(product.supplierId, rows);
  }
  return (
    <section aria-label="Сводка по поставщикам">
      <div className="section-heading">
        <div>
          <h2>Поставщики и потребность</h2>
          <p>{groups.size} групп поставки. Откройте товары или проверьте отдельный заказ.</p>
        </div>
      </div>
      <div className="supplier-cards">
        {[...groups]
          .sort((a, b) => a[1][0].supplier.localeCompare(b[1][0].supplier))
          .map(([id, rows]) => {
            const orders = rows.filter((row) => row.recommended > 0);
            return (
              <article className="supplier-card" key={id}>
                <h3>{rows[0].supplier}</h3>
                <p className="helper">Группа: {id}</p>
                <dl>
                  <dt>Товаров</dt>
                  <dd>{rows.length}</dd>
                  <dt>К пополнению</dt>
                  <dd>
                    {orders.length} позиций · {quantitySummary(orders)}
                  </dd>
                  <dt>Высокий риск</dt>
                  <dd>{rows.filter((row) => row.status === 'Дефицит').length}</dd>
                  <dt>Сроки поставки</dt>
                  <dd>
                    {[...new Set(rows.map((row) => row.calculation.lead_time_days))].join(', ')} дн.
                  </dd>
                </dl>
                <button
                  className="secondary-button"
                  onClick={() => {
                    workspace.navigate('table');
                    workspace.setFilters({ ...initialFilters, supplier: rows[0].supplier });
                  }}
                >
                  Открыть товары
                </button>
                <button
                  className="primary-button"
                  disabled={!orders.length || workspace.loading}
                  onClick={() => workspace.setReviewProducts(orders)}
                >
                  Проверить заказ поставщику
                </button>
              </article>
            );
          })}
      </div>
    </section>
  );
}
