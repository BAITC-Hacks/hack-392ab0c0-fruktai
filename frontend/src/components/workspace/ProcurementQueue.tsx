import { Users, Search, ShieldCheck, Check, ChevronRight } from 'lucide-react';
import type { WorkspaceController } from '../../hooks/useWorkspace';
import { initialFilters } from '../../utils/presentation';
import { FiltersBar } from '../FiltersBar';
import { RecommendationsTable } from '../RecommendationsTable';

export function ProcurementQueue({ workspace }: { workspace: WorkspaceController }) {
  const {
    navigate,
    products,
    filters,
    setFilters,
    filtered,
    selected,
    activeProduct,
    setActiveProduct,
    toggle,
    toggleAll,
    selectedProducts,
    visibleSelectedCount,
    setSelected,
    openReview,
    loading,
  } = workspace;
  return (
    <section className="workspace-content" aria-label="Закупочная очередь">
      <div className="queue-heading">
        <div>
          <h2>Рекомендации к проверке</h2>
          <p>От риска — к решению. Откройте позицию, чтобы проверить расчёт.</p>
        </div>
        <div>
          <button className="secondary-button" onClick={() => navigate('suppliers')}>
            <Users size={15} />
            По поставщикам
          </button>
        </div>
      </div>
      <FiltersBar products={products} value={filters} onChange={setFilters} />
      {filtered.length === 0 ? (
        <div className="empty-state">
          <Search size={30} />
          <h2>Подходящих позиций нет</h2>
          <p>Попробуйте другой запрос или сбросьте фильтры.</p>
          <button className="secondary-button" onClick={() => setFilters(initialFilters)}>
            Сбросить фильтры
          </button>
        </div>
      ) : (
        <RecommendationsTable
          products={filtered}
          selected={selected}
          activeSku={activeProduct?.sku ?? null}
          grouped={false}
          sort={filters.sort}
          onSort={(sort) => setFilters({ ...filters, sort })}
          onOpen={setActiveProduct}
          onToggle={toggle}
          onToggleAll={toggleAll}
        />
      )}
      <div className="table-footer">
        <span>
          Показано <b>{filtered.length}</b> из {products.length} позиций
        </span>
        <span>
          <ShieldCheck size={14} />
          Решение подтверждает менеджер
        </span>
      </div>
      {selectedProducts.length > 0 && (
        <div className="selection-bar">
          <span>
            <Check size={16} />
            <b>Выбрано: {selectedProducts.length}</b>
            {selectedProducts.length > visibleSelectedCount && (
              <small>Скрыто фильтрами: {selectedProducts.length - visibleSelectedCount}</small>
            )}
          </span>
          <div>
            <button className="text-button" onClick={() => setSelected(new Set())}>
              Снять выбор
            </button>
            <button className="primary-button" onClick={openReview} disabled={loading}>
              Проверить и экспортировать <ChevronRight size={15} />
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
