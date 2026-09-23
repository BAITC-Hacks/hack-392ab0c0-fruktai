import { useEffect, useState } from 'react';
import { Line, LineChart, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import type { DemoProduct } from '../types/demo';
import type { ItemResponse } from '../types/api';
import { loadItem } from '../api/client';
import { formatNumber, validateScenario, type ScenarioDraft } from '../utils/presentation';
import { StatusBadge } from './StatusBadge';

interface Props {
  product: DemoProduct; draft: ScenarioDraft | undefined;
  onDraft: (draft: ScenarioDraft | undefined) => void;
  selected: boolean; onToggle: () => void; busy: boolean;
  onRecalculate: (draft: ScenarioDraft) => Promise<void>;
}
export function RecommendationDetails({ product: p, draft, onDraft, selected, onToggle, busy, onRecalculate }: Props) {
  const [values, setValues] = useState<ScenarioDraft>(draft ?? { onHand: String(p.onHand), inTransit: String(p.inTransit) });
  const [error, setError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [item, setItem] = useState<ItemResponse | null>(null);
  const [before, setBefore] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    setItem(null); setHistoryError('');
    loadItem(p.sku).then(value => { if (active) setItem(value); })
      .catch(problem => { if (active) setHistoryError(String(problem.message)); });
    return () => { active = false; };
  }, [p]);
  const c = p.calculation;
  async function recalculate() {
    const problem = validateScenario(values);
    if (problem) { setError(problem); return; }
    setError(''); onDraft(values);
    try { const previous = p.recommended; await onRecalculate(values); setBefore(previous); }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'Ошибка пересчёта'); }
  }
  return <>
    <div className="product-detail-heading"><div><h2 id="drawer-title">{p.name}</h2><p className="muted">{p.sku} · {p.supplier}</p></div></div>
    <StatusBadge status={p.status}/>
    <div className="recommendation-result"><div><span>Рекомендовано заказать</span><strong data-testid="recommended-qty">{formatNumber(p.recommended)} <small>{p.unit}</small></strong></div></div>
    <section className="detail-section"><h3>Обоснование расчёта</h3><ul>{c.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul></section>
    <section className="detail-section"><h3>Из чего складывается заказ</h3><div className="formula-label">ceil(max(0, прогноз + запас − остаток − в пути))</div>
      <dl className="calculation-lines">{[
        ['Прогноз на срок поставки', c.forecast_demand], ['Страховой запас', c.safety_stock],
        ['На складе', c.on_hand], ['Товар в пути', c.in_transit],
      ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{formatNumber(Number(value))} {p.unit}</dd></div>)}</dl>
    </section>
    <section className="detail-section scenario-section"><h3>Что, если изменить запас?</h3><p className="helper">Пересчёт выполняется API и сохраняется в SQLite. Исходные CSV не меняются. «Обновить данные» сбрасывает все поправки.</p>
      <form onSubmit={event => { event.preventDefault(); void recalculate(); }}>
        <div className="scenario-fields">
          <label>На складе<input aria-label="На складе" inputMode="numeric" value={values.onHand} disabled={busy} onChange={e => setValues({ ...values, onHand: e.target.value })}/></label>
          <label>В пути<input aria-label="В пути" inputMode="numeric" value={values.inTransit} disabled={busy} onChange={e => setValues({ ...values, inTransit: e.target.value })}/></label>
        </div>
        {error && <p role="alert" className="field-error">{error}</p>}
        <button className="primary-button" disabled={busy} type="submit">{busy ? 'Пересчёт…' : 'Пересчитать через API'}</button>
        {before !== null && <p role="status">До: {formatNumber(before)} → После: {formatNumber(p.recommended)} {p.unit}</p>}
      </form>
    </section>
    <section className="detail-section"><h3>История продаж</h3>
      {historyError ? <p role="alert">{historyError}</p> : !item ? <p>Загрузка истории…</p> : <>
        <div style={{ width: '100%', height: 240 }} data-testid="sales-history"><ResponsiveContainer width="100%" height="100%">
          <LineChart data={item.history}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="date" tick={{ fontSize: 10 }}/><YAxis/><Tooltip/><Legend/>
            <Line dataKey="units" name="Продажи" stroke="#175CD3" dot={false} isAnimationActive={false}/>
            <Line dataKey="estimated_lost_units" name="Упущенный спрос" stroke="#E04F16" dot={false} isAnimationActive={false}/>
          </LineChart>
        </ResponsiveContainer></div>
        <p>Дней с аномалиями: {item.history.filter(d => d.is_outlier).length}. Дней stockout: {item.history.filter(d => d.is_stockout).length}.</p>
      </>}
    </section>
    <details className="technical-details"><summary>Параметры расчёта</summary><dl className="metadata-list">{[
      ['Средний спрос', c.avg_daily_demand], ['Срок поставки, дней', c.lead_time_days],
      ['Дней покрытия', c.days_of_cover], ['Сезонность', c.seasonality_factor],
      ['Рост', c.growth_factor], ['Компенсация stockout', c.stockout_compensation],
      ['Удалённые выбросы', c.outlier_units_removed],
    ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{formatNumber(Number(value))}</dd></div>)}</dl></details>
    <div className="drawer-footer"><button className="secondary-button full-width" onClick={onToggle}>{selected ? 'Убрать из выбранных' : 'Добавить к проверке заказа'}</button></div>
  </>;
}
