import { useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { DemoProduct, DemoStatus } from '../types/demo';
import { formatNumber, positionWord } from '../utils/presentation';

const statusStyles: { name: DemoStatus; color: string }[] = [
  { name: 'Дефицит', color: '#B42318' },
  { name: 'Пограничный остаток', color: '#B54708' },
  { name: 'В норме', color: '#98A2B3' },
];
export function Analytics({ products, onStatus }: { products: DemoProduct[]; onStatus: (status: string) => void }) {
  const [expanded, setExpanded] = useState(true);
  const distribution = statusStyles.map(s => ({ ...s, value: products.filter(p => p.status === s.name).length }));
  return <aside className="analytics-sidebar" aria-label="Аналитика текущей выборки">
    <button className="analytics-heading" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-controls="analytics-content"><span>Аналитика</span>{expanded ? <ChevronUp size={18}/> : <ChevronDown size={18}/>}</button>
    {expanded && <div id="analytics-content">
      <section className="analytics-section"><h3>Структура рекомендаций</h3><p className="helper">По текущим фильтрам</p>
        {products.length > 0 ? <><div className="donut"><ResponsiveContainer width="100%" height={190}><PieChart><Pie data={distribution.filter(d => d.value > 0)} dataKey="value" innerRadius={63} outerRadius={83} paddingAngle={3} stroke="none" startAngle={90} endAngle={-270} isAnimationActive={false}>{distribution.filter(d => d.value > 0).map(d => <Cell key={d.name} fill={d.color}/>)}</Pie></PieChart></ResponsiveContainer><div className="donut-label"><strong>{products.length}</strong><span>{positionWord(products.length)}</span></div></div>
        <ul className="chart-legend">{distribution.map(d => <li key={d.name}><button onClick={() => onStatus(d.name)} title={'Отфильтровать: ' + d.name}><span className="legend-dot" style={{ background: d.color }}/><span>{d.name}</span><b>{d.value}</b><small>{Math.round(d.value / products.length * 100)}%</small></button></li>)}</ul></> : <p className="chart-empty">Нет позиций для анализа. Измените фильтры.</p>}
      </section>
    </div>}
  </aside>;
}

export function Comparison({ products }: { products: DemoProduct[] }) {
  const units = [...new Set(products.map(p => p.unit))];
  return <section className="comparison-view"><div className="view-heading"><span className="eyebrow">Сравнение запасов</span><h2>Остаток и рекомендованный заказ</h2><p>Сопоставление текущих значений. Это не прогноз спроса и не оценка экономии.</p></div>
    {units.map(unit => {
      const rows = products.filter(p => p.unit === unit).map(p => ({ sku: p.sku, name: p.name, stock: p.onHand, order: p.recommended }));
      return <div className="comparison-chart" key={unit}><h3>Товары в {unit === 'м' ? 'метрах' : 'штуках'} <span>{rows.length} {positionWord(rows.length)}</span></h3><div style={{ height: Math.max(210, rows.length * 66 + 65) }}><ResponsiveContainer width="100%" height="100%"><BarChart data={rows} layout="vertical" margin={{ left: 0, right: 24, bottom: 8, top: 8 }} barGap={3}>
        <CartesianGrid horizontal={false} stroke="#EAECF0"/><XAxis type="number" tick={{ fontSize: 11, fill: '#667085' }} unit={' ' + unit} axisLine={false} tickLine={false}/><YAxis type="category" dataKey="sku" width={132} tick={{ fontSize: 11, fill: '#475467' }} axisLine={false} tickLine={false}/>
        <Tooltip formatter={value => formatNumber(Number(value)) + ' ' + unit} contentStyle={{ borderRadius: 8, fontSize: 12, borderColor: '#D0D5DD' }}/><Legend iconType="square" wrapperStyle={{ fontSize: 12 }}/><Bar dataKey="stock" name="На складе" fill="#98A2B3" radius={[0, 3, 3, 0]} maxBarSize={13} isAnimationActive={false}/><Bar dataKey="order" name="Рекомендовано заказать" fill="#175CD3" radius={[0, 3, 3, 0]} maxBarSize={13} isAnimationActive={false}/>
      </BarChart></ResponsiveContainer></div></div>;
    })}
  </section>;
}
