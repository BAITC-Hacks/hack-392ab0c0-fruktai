import { exportRun } from '../../api/client';
import type { WorkspaceController } from '../../hooks/useWorkspace';
import { Drawer } from '../Drawer';
import { RecommendationDetails } from '../RecommendationDetails';
import { ReviewOrder } from '../ReviewOrder';

export function WorkspaceDialogs({ workspace }: { workspace: WorkspaceController }) {
  const {
    activeProduct,
    setActiveProduct,
    data,
    drafts,
    setDraft,
    selected,
    toggle,
    loading,
    recalculateProduct,
    reviewProducts,
    setReviewProducts,
    setNotice,
  } = workspace;
  return (
    <>
      {' '}
      {workspace.profileOpen && (
        <Drawer title="Профиль рабочего места" onClose={() => workspace.setProfileOpen(false)}>
          <section className="profile-panel">
            <h2>Менеджер закупок</h2>
            <p className="helper">
              Локальное рабочее место. Авторизация и личные аккаунты в MVP не подключены.
            </p>
            <dl>
              <dt>Набор данных</dt>
              <dd>{workspace.dataset}</dd>
              <dt>Склад</dt>
              <dd>{data?.metadata?.warehouse_id || 'Не указан'}</dd>
              <dt>Последний расчёт</dt>
              <dd>{data?.response.run_id || 'Ещё не выполнен'}</dd>
            </dl>
            <button
              className="secondary-button full-width"
              onClick={() => workspace.navigate('data')}
            >
              Открыть источники данных
            </button>
            <button
              className="secondary-button full-width"
              onClick={() => workspace.navigate('activity')}
            >
              Открыть ход анализа
            </button>
            <button
              className="primary-button full-width"
              onClick={() => workspace.navigate('table')}
            >
              Перейти к рекомендациям
            </button>
          </section>
        </Drawer>
      )}
      {activeProduct && (
        <Drawer title="Объяснение рекомендации" onClose={() => setActiveProduct(null)}>
          <RecommendationDetails
            key={activeProduct.sku}
            product={activeProduct}
            runId={data!.response.run_id}
            draft={drafts[activeProduct.sku]}
            onDraft={(draft) => setDraft(activeProduct.sku, draft)}
            selected={selected.has(activeProduct.sku)}
            onToggle={() => toggle(activeProduct.sku)}
            busy={loading}
            onRecalculate={(draft) => recalculateProduct(activeProduct.sku, draft)}
          />
        </Drawer>
      )}
      {reviewProducts && (
        <Drawer title="Проверка заказа" wide onClose={() => setReviewProducts(null)}>
          <ReviewOrder
            products={reviewProducts}
            onExport={async (format) => {
              try {
                if (!data) throw new Error('Нет расчёта');
                await exportRun(
                  data.response.run_id,
                  reviewProducts.map((p) => p.sku),
                  format,
                );
                setNotice(
                  'Экспорт подготовлен. Позиций: ' +
                    reviewProducts.length +
                    '. Заказ поставщикам не отправлялся.',
                );
                setReviewProducts(null);
              } catch {
                throw new Error(
                  'Не удалось экспортировать сохранённый расчёт. Повторите выгрузку.',
                );
              }
            }}
          />
        </Drawer>
      )}
    </>
  );
}
