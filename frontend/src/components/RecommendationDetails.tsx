import { useState } from 'react';
import { ArrowDown, ArrowUp, Info, ShieldCheck, TrendingUp, SlidersHorizontal, Save, RotateCcw, Check } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
import { formatNumber, formatDate, shortReason, validateScenario, type ScenarioDraft } from '../utils/presentation';
import { ProductArt } from './ProductArt';
import { StatusBadge } from './StatusBadge';

interface Props {
  product: DemoProduct; draft: ScenarioDraft | undefined;
  onDraft: (draft: ScenarioDraft | undefined) => void;
  selected: boolean; onToggle: () => void;
}
export function RecommendationDetails({ product: p, draft, onDraft, selected, onToggle }: Props) {
  const baseline = { onHand: String(p.onHand), inTransit: String(p.inTransit) };
  const [values, setValues] = useState<ScenarioDraft>(draft ?? baseline);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  function save() {
    const problem = validateScenario(values);
    if (problem) { setError(problem); setSaved(false); return; }
    setError(''); onDraft(values); setSaved(true);
  }
  return <>
    <div className="product-detail-heading"><ProductArt kind={p.kind}/><div><p className="eyebrow">{p.category}</p><h2 id="drawer-title">{p.name}</h2><p className="muted">{p.sku} · {p.supplier}</p></div></div>
    <div className="detail-status"><StatusBadge status={p.status}/></div>
    <div className="recommendation-result"><div><span>Рекомендовано заказать</span><strong>{formatNumber(p.recommended)} <small>{p.unit}</small></strong></div><p>{shortReason(p)}</p></div>
    <p className="detail-copy">{p.explanation}</p>
    <section className="detail-section"><h3>Из чего складывается заказ</h3><div className="formula-label">max(0, прогноз + запас − остаток − в пути)</div>
      <dl className="calculation-lines">
        <div><dt><ArrowUp size={14}/>Прогноз на срок поставки</dt><dd className="muted">Нет данных</dd></div>
        <div><dt><ArrowUp size={14}/>Страховой запас</dt><dd className="muted">Нет данных</dd></div>
        <div><dt><ArrowDown size={14}/>На складе</dt><dd>−{formatNumber(p.onHand)} {p.unit}</dd></div>
        <div><dt><ArrowDown size={14}/>Товар в пути</dt><dd>−{formatNumber(p.inTransit)} {p.unit}</dd></div>
        <div className="total-line"><dt>Рекомендация из примера</dt><dd>{formatNumber(p.recommended)} {p.unit}</dd></div>
      </dl>
      <p className="helper">Компоненты прогноза отсутствуют в наборе. Формула показана для объяснения; интерфейс не вычисляет заказ.</p>
    </section>
    {(p.anomalyNote || p.stockoutNote) && <section className="detail-section"><h3>Коррекции спроса</h3>{p.anomalyNote && <div className="insight"><ShieldCheck size={20}/><div><strong>Крупная разовая продажа</strong><p>{p.anomalyNote}</p><span>Демонстрационное объяснение</span></div></div>}{p.stockoutNote && <div className="insight"><TrendingUp size={20}/><div><strong>Спрос во время отсутствия товара</strong><p>{p.stockoutNote}</p><span>Демонстрационное объяснение</span></div></div>}</section>}
    <section className="detail-section scenario-section"><h3><SlidersHorizontal size={18}/> Что, если изменить запас?</h3><p className="helper">Подготовьте сценарий. Черновик сохраняется до обновления страницы, исходный заказ не изменяется.</p>
      <form onSubmit={event => { event.preventDefault(); save(); }} noValidate>
        <div className="scenario-fields"><label>На складе, {p.unit}<input inputMode="decimal" value={values.onHand} aria-invalid={!!error} aria-describedby={error ? 'scenario-error' : undefined} onChange={e => { setValues({ ...values, onHand: e.target.value }); setSaved(false); setError(''); }}/></label><label>В пути, {p.unit}<input inputMode="decimal" value={values.inTransit} aria-invalid={!!error} aria-describedby={error ? 'scenario-error' : undefined} onChange={e => { setValues({ ...values, inTransit: e.target.value }); setSaved(false); setError(''); }}/></label></div>
        {error && <p className="field-error" id="scenario-error" role="alert">{error}</p>}
        <div className="scenario-actions"><button className="secondary-button" type="submit"><Save size={15}/>Сохранить сценарий</button><button className="icon-button" type="button" aria-label="Восстановить исходный запас" title="Восстановить исходные значения" onClick={() => { setValues(baseline); onDraft(undefined); setSaved(false); setError(''); }}><RotateCcw size={16}/></button></div>
        {saved && <p className="saved-message" role="status"><Check size={14}/>Черновик сохранён. Пересчёт не выполнялся.</p>}
      </form>
      <div className="integration-notice"><Info size={16}/><p>Пересчёт и сравнение «до / после» появятся после подключения сервиса расчёта.</p></div>
    </section>
    <details className="technical-details"><summary>Данные и параметры расчёта</summary><dl className="metadata-list"><div><dt>Ожидаемая поставка</dt><dd>{p.expectedDate ? formatDate(p.expectedDate) : 'Не указана'}</dd></div>{['Средний спрос', 'Срок поставки', 'Дней покрытия', 'Коэффициент сезонности', 'Коэффициент роста', 'Численная компенсация stockout', 'Объём удалённого выброса'].map(label => <div key={label}><dt>{label}</dt><dd>Нет данных</dd></div>)}</dl><p className="helper">Неизвестные показатели не заменены нулями. История спроса в набор не включена, поэтому график прогноза не строится.</p></details>
    <div className="drawer-footer"><button className={selected ? 'secondary-button full-width' : 'primary-button full-width'} onClick={onToggle}>{selected ? <Check size={18}/> : null}{selected ? 'Убрать из выбранных' : 'Добавить к проверке заказа'}</button></div>
  </>;
}
