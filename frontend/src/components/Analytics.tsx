import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';
import { AlertTriangle, ArrowUpRight, ShieldCheck, Clock3 } from 'lucide-react';
import type { DemoProduct, DemoStatus } from '../types/demo';
import { formatNumber, positionWord } from '../utils/presentation';

const statusStyles: { name: DemoStatus; color: string; Icon: typeof AlertTriangle }[] = [
  { name: 'Дефицит', color: '#B42318', Icon: AlertTriangle },
  { name: 'Пограничный остаток', color: '#B54708', Icon: Clock3 },
  { name: 'В норме', color: '#667085', Icon: ShieldCheck },
];
export function Analytics({ products, onStatus }: { products: DemoProduct[]; onStatus: (status: string) => void }) {
  const distribution = statusStyles.map(s => ({ ...s, value: products.filter(p => p.status === s.name).length }));
  return <aside className="analytics-sidebar" aria-label="Аналитика текущей выборки">
    <div className="section-heading"><div><span className="eyebrow">Контроль запасов</span><h2>Где нужно внимание</h2><p>{products.length} {positionWord(products.length)} по текущим фильтрам</p></div></div>
    {products.length > 0 ? <div className="risk-distribution">{distribution.map(({ name, color, value, Icon }) => <button key={name} onClick={() => onStatus(name)} title={'Отфильтровать: ' + name}>
      <span className="risk-distribution-label"><Icon size={16} style={{ color }}/><strong>{name}</strong><ArrowUpRight size={15}/></span>
      <span className="risk-distribution-value">{value}<small>{Math.round(value / products.length * 100)}% выборки</small></span>
      <span className="distribution-track"><i style={{ width: (value / products.length * 100) + '%', background: color }}/></span>
    </button>)}</div> : <p className="chart-empty">Нет позиций для анализа. Измените фильтры.</p>}
    <p className="analytics-footnote">Нажмите на статус, чтобы перейти к соответствующим рекомендациям.</p>
  </aside>;
}

export function Comparison({ products }: { products: DemoProduct[] }) {
  const units = [...new Set(products.map(p => p.unit))];
  return <section className="comparison-view"><div className="section-heading"><div><span className="eyebrow">Сценарий пополнения</span><h2>Как изменится доступный запас</h2><p>Текущий остаток и товар в пути → запас при получении рекомендованного заказа.</p></div></div>
    {units.map(unit => {
      const rows = products.filter(p => p.unit === unit).map(p => ({ sku: p.sku, before: p.onHand + p.inTransit, after: p.onHand + p.inTransit + p.recommended }));
      return <div className="comparison-chart" key={unit}><h3>Единица: {unit}<span>{rows.length} {positionWord(rows.length)}</span></h3><div style={{ height: Math.max(210, rows.length * 54 + 60) }}><ResponsiveContainer width="100%" height="100%"><BarChart data={rows} layout="vertical" margin={{ left: 0, right: 24, bottom: 8, top: 8 }} barGap={3}>
        <CartesianGrid horizontal={false} stroke="#EAECF0"/><XAxis type="number" tick={{ fontSize: 11, fill: '#667085' }} unit={' ' + unit} axisLine={false} tickLine={false}/><YAxis type="category" dataKey="sku" width={114} tick={{ fontSize: 11, fill: '#475467' }} axisLine={false} tickLine={false}/>
        <Tooltip formatter={value => formatNumber(Number(value)) + ' ' + unit} contentStyle={{ borderRadius: 8, fontSize: 12, borderColor: '#D0D5DD' }}/><Legend iconType="square" wrapperStyle={{ fontSize: 12 }}/><Bar dataKey="before" name="Остаток + в пути" fill="#98A2B3" radius={[0, 3, 3, 0]} maxBarSize={11} isAnimationActive={false}/><Bar dataKey="after" name="С рекомендованным заказом" fill="#175CD3" radius={[0, 3, 3, 0]} maxBarSize={11} isAnimationActive={false}/>
      </BarChart></ResponsiveContainer></div></div>;
    })}
    <p className="analytics-footnote">Сопоставление объёмов, не прогноз остатков во времени. Сроки прибытия, расход до поставки и экономия здесь не моделируются.</p>
  </section>;
}
