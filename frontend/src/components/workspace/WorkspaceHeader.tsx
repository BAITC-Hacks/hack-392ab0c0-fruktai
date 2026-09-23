import { RefreshCw, ShoppingCart, Upload, AlertTriangle, Check, X } from 'lucide-react';
import { formatDate } from '../../utils/presentation';
import type { WorkspaceController } from '../../hooks/useWorkspace';

export function WorkspaceHeader({ workspace }: { workspace: WorkspaceController }) {
  const {
    title,
    view,
    load,
    loading,
    data,
    openReview,
    selectedProducts,
    dataset,
    navigate,
    error,
    notice,
    setNotice,
  } = workspace;
  return (
    <>
      {' '}
      <div className="page-heading">
        <div>
          <h1>{title}</h1>
          <p>
            {view === 'data'
              ? 'Проверенные источники — основа точной рекомендации.'
              : view === 'activity'
                ? 'От исходных данных до объяснимого решения.'
                : 'Нужный товар. В нужном количестве. Вовремя.'}
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="secondary-button"
            onClick={() => void load()}
            disabled={loading}
            title="Повторить расчёт исходного набора без ручных поправок"
          >
            <RefreshCw size={16} className={loading ? 'is-spinning' : ''} />
            {loading ? 'Загрузка…' : 'Обновить данные'}
          </button>
          {data && (
            <button className="primary-button" onClick={openReview} disabled={loading}>
              <ShoppingCart size={17} />
              Проверить заказ
              {selectedProducts.length > 0 && (
                <span className="button-count">{selectedProducts.length}</span>
              )}
            </button>
          )}
        </div>
      </div>
      <div className="context-row">
        <span className="dataset-badge">
          {(data?.dataset || dataset) === 'demo' ? 'Учебный набор · demo' : 'Загруженные данные'}
        </span>
        <span>
          {data
            ? 'Расчёт: ' +
              formatDate(data.updatedAt) +
              ', ' +
              new Date(data.updatedAt).toLocaleTimeString('ru-RU', {
                hour: '2-digit',
                minute: '2-digit',
                timeZone: 'Asia/Almaty',
              }) +
              ' (UTC+5)'
            : 'Ожидаем ответ API'}
        </span>
        <span
          className="source-freshness"
          title="API возвращает время расчёта, но не дату актуальности складских остатков"
        >
          Свежесть источников не подтверждена
        </span>
        {view !== 'data' && (
          <button className="context-link" onClick={() => navigate('data')}>
            <Upload size={14} />
            Загрузить данные / выгрузку 1С
          </button>
        )}
      </div>
      {error && (
        <div className="error-banner" role="alert">
          <AlertTriangle size={20} />
          <div>
            <strong>Не удалось обновить рекомендации</strong>
            <p>{error}</p>
            {data && <p>На экране сохранён предыдущий набор.</p>}
          </div>
          <button className="secondary-button" onClick={() => void load()}>
            Повторить загрузку
          </button>
        </div>
      )}
      {notice && (
        <div className="notice-banner" role="status">
          <Check size={17} />
          <span>{notice}</span>
          <button
            className="icon-button"
            aria-label="Закрыть уведомление"
            onClick={() => setNotice('')}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </>
  );
}
