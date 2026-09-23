import { useState } from 'react';
import { ArrowRight, SlidersHorizontal, Calculator, Info, ArrowDownRight } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
import {
  formatNumber,
  shortReason,
  validateScenario,
  type ScenarioDraft,
} from '../utils/presentation';
import { SalesHistory } from './item/SalesHistory';
import { StatusBadge } from './StatusBadge';

interface Props {
  product: DemoProduct;
  runId: string;
  draft: ScenarioDraft | undefined;
  onDraft: (draft: ScenarioDraft | undefined) => void;
  selected: boolean;
  onToggle: () => void;
  busy: boolean;
  onRecalculate: (draft: ScenarioDraft) => Promise<void>;
}
export function RecommendationDetails({
  product: p,
  runId,
  draft,
  onDraft,
  selected,
  onToggle,
  busy,
  onRecalculate,
}: Props) {
  const [values, setValues] = useState<ScenarioDraft>(
    draft ?? { onHand: String(p.onHand), inTransit: String(p.inTransit) },
  );
  const [error, setError] = useState('');
  const [before, setBefore] = useState<number | null>(null);
  const c = p.calculation;
  async function recalculate() {
    const problem = validateScenario(values);
    if (problem) {
      setError(problem);
      return;
    }
    setError('');
    onDraft(values);
    try {
      const previous = p.recommended;
      await onRecalculate(values);
      setBefore(previous);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Ошибка пересчёта');
    }
  }
  return (
    <>
      <div className="product-detail-heading">
        <span className="eyebrow">Карточка рекомендации</span>
        <h2 id="drawer-title">{p.name}</h2>
        <p>
          {p.sku}
          <span> / </span>
          {p.supplier}
        </p>
      </div>
      <div className="detail-status">
        <StatusBadge status={p.status} />
        <span>Срок поставки: {c.lead_time_days} дн.</span>
      </div>
      <div className="recommendation-result">
        <div>
          <span>Рекомендовано заказать</span>
          <strong data-testid="recommended-qty">
            {formatNumber(p.recommended)} <small>{p.unit}</small>
          </strong>
        </div>
        <p>{shortReason(p)}</p>
      </div>
      <section className="detail-section">
        <h3>
          <Calculator size={17} />
          Из чего складывается заказ
        </h3>
        <dl className="calculation-lines">
          {[
            ['Прогноз на срок поставки', c.forecast_demand, '+'],
            ['Страховой запас', c.safety_stock, '+'],
            ['На складе', c.on_hand, '−'],
            ['Товар в пути', c.in_transit, '−'],
          ].map(([label, value, sign]) => (
            <div key={label}>
              <dt>
                <span className="formula-sign">{sign}</span>
                {label}
              </dt>
              <dd>
                {formatNumber(Number(value))} <small>{p.unit}</small>
              </dd>
            </div>
          ))}
          <div className="total-line">
            <dt>Итог к заказу</dt>
            <dd>
              {formatNumber(p.recommended)} {p.unit}
            </dd>
          </div>
        </dl>
        <p className="formula-label">
          max(0, прогноз + запас − остаток − в пути)
          <br />
          <span>Округление вверх до целой базовой единицы.</span>
        </p>
        <details className="reason-details">
          <summary>Все обоснования · {c.reasons.length}</summary>
          <ul>
            {c.reasons.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        </details>
      </section>
      <SalesHistory product={p} runId={runId} />
      <section className="detail-section scenario-section">
        <div className="scenario-heading">
          <span className="scenario-icon">
            <SlidersHorizontal size={18} />
          </span>
          <div>
            <h3>Что, если изменить запас?</h3>
            <p>Проверьте сценарий до формирования заказа</p>
          </div>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void recalculate();
          }}
        >
          <div className="scenario-fields">
            <label>
              На складе
              <div className="input-unit">
                <input
                  aria-label="На складе"
                  inputMode="numeric"
                  value={values.onHand}
                  disabled={busy}
                  onChange={(e) => {
                    const next = { ...values, onHand: e.target.value };
                    setValues(next);
                    onDraft(next);
                  }}
                />
                <span>{p.unit}</span>
              </div>
            </label>
            <label>
              В пути
              <div className="input-unit">
                <input
                  aria-label="В пути"
                  inputMode="numeric"
                  value={values.inTransit}
                  disabled={busy}
                  onChange={(e) => {
                    const next = { ...values, inTransit: e.target.value };
                    setValues(next);
                    onDraft(next);
                  }}
                />
                <span>{p.unit}</span>
              </div>
            </label>
          </div>
          {error && (
            <p role="alert" className="field-error">
              {error}
            </p>
          )}
          <div className="scenario-actions">
            <button className="primary-button" disabled={busy} type="submit">
              {busy ? 'Пересчёт…' : 'Пересчитать через API'}
              <ArrowRight size={15} />
            </button>
            <button
              className="text-button"
              type="button"
              disabled={busy}
              onClick={() => {
                setValues({ onHand: String(p.onHand), inTransit: String(p.inTransit) });
                onDraft(undefined);
                setError('');
              }}
            >
              Сбросить ввод
            </button>
          </div>
          {before !== null && (
            <div className="scenario-result" role="status">
              <span>
                До<strong>{formatNumber(before)}</strong>
              </span>
              <ArrowRight size={18} />
              <span>
                После<strong>{formatNumber(p.recommended)}</strong>
              </span>
              <span className="scenario-delta">
                <ArrowDownRight size={16} />
                {p.recommended - before > 0 ? '+' : ''}
                {formatNumber(p.recommended - before)} {p.unit}
              </span>
            </div>
          )}
        </form>
        <p className="helper">
          <Info size={14} />
          Результат появится после ответа API. Исходные файлы не меняются. «Обновить данные»
          сбрасывает поправки.
        </p>
      </section>
      <details className="technical-details">
        <summary>Параметры и аудит расчёта</summary>
        <dl className="metadata-list">
          {[
            ['Средний спрос, ' + p.unit + '/день', c.avg_daily_demand],
            ['Срок поставки, дней', c.lead_time_days],
            ['Дней покрытия (включая товар в пути)', c.days_of_cover],
            ['Сезонность', c.seasonality_factor],
            ['Рост', c.growth_factor],
            ['Компенсация stockout, ' + p.unit, c.stockout_compensation],
            ['Удалённые выбросы, ' + p.unit, c.outlier_units_removed],
          ].map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{formatNumber(Number(value))}</dd>
            </div>
          ))}
        </dl>
        <code className="run-id">{runId}</code>
      </details>
      <div className="drawer-footer">
        <button className="secondary-button full-width" onClick={onToggle}>
          {selected ? 'Убрать из выбранных' : 'Добавить к проверке заказа'}
        </button>
      </div>
    </>
  );
}
