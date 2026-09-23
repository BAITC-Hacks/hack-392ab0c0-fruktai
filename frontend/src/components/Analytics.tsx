import { useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';
import { ChevronDown, ChevronUp, ArrowUpRight, Package } from 'lucide-react';
import type { DemoProduct, DemoStatus } from '../types/demo';
import { formatNumber, quantitySummary } from '../utils/presentation';

const statusStyles: { name: DemoStatus; color: string }[] = [
  { name: 'Дефицит', color: '#ce5747' },
  { name: 'Пограничный остаток', color: '#c48a33' },
  { name: 'В норме', color: '#2c7770' },
];
export function Analytics({ products, onStatus }: { products: DemoProduct[]; onStatus: (status: string) => void }) {
  const [expanded, setExpanded] = useState(true);
  const distribution = statusStyles.map(s => ({ ...s, value: products.filter(p => p.status === s.name).length }));
  const suppliers = new Set(products.map(p => p.supplier)).size;
  return <aside className="analytics-sidebar" aria-label="Аналитика текущей выборки">
    <button className="analytics-heading" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-controls="analytics-content"><span>Аналитика</span>{expanded ? <ChevronUp size={18}/> : <ChevronDown size={18}/>}</button>
    {expanded && <div id="analytics-content">
      <section className="analytics-section"><h3>Структура рекомендаций</h3><p className="helper">По текущим фильтрам</p>
        {products.length > 0 ? <><div className="donut"><ResponsiveContainer width="100%" height={190}><PieChart><Pie data={distribution.filter(d => d.value > 0)} dataKey="value" innerRadius={63} outerRadius={83} paddingAngle={3} stroke="none" startAngle={90} endAngle={-270} isAnimationActive={false}>{distribution.filter(d => d.value > 0).map(d => <Cell key={d.name} fill={d.color}/>)}</Pie></PieChart></ResponsiveContainer><div className="donut-label"><strong>{products.length}</strong><span>позиций</span></div></div>
        <ul className="chart-legend">{distribution.map(d => <li key={d.name}><button onClick={() => onStatus(d.name)} title={'Отфильтровать: ' + d.name}><span className="legend-dot" style={{ background: d.color }}/><span>{d.name}</span><b>{d.value}</b><small>{Math.round(d.value / products.length * 100)}%</small></button></li>)}</ul></> : <p className="chart-empty">Нет позиций для анализа. Измените фильтры.</p>}
      </section>
      <section className="analytics-section"><h3>План пополнения</h3><div className="plan-total"><Package size={18}/><strong>{quantitySummary(products)}</strong></div><p className="helper">{suppliers} поставщиков в выборке. Объёмы в разных единицах не складываются.</p><div className="mini-metric"><span>Товар отсутствует</span><b>{products.filter(p => p.onHand === 0).length} позиций</b></div><div className="mini-metric"><span>Есть товар в пути</span><b>{products.filter(p => p.inTransit > 0).length} позиций</b></div></section>
      <section className="analytics-section"><div className="small-label">Проверка решения</div><h3>Каждое число объяснимо</h3><p className="helper">Откройте позицию, чтобы посмотреть состав заказа и причины корректировки спроса.</p><a href="#workspace" className="text-button sidebar-link">К рекомендациям <ArrowUpRight size={15}/></a></section>
      <div className="source-label">Источник: демонстрационный набор<br/>Результаты расчётного сервиса не получены</div>
    </div>}
  </aside>;
}

export function Comparison({ products }: { products: DemoProduct[] }) {
  const units = [...new Set(products.map(p => p.unit))];
  return <section className="comparison-view"><div className="view-heading"><span className="eyebrow">Сравнение запасов</span><h2>Остаток и рекомендованный заказ</h2><p>Сопоставление текущих значений. Это не прогноз спроса и не оценка экономии.</p></div>
    {units.map(unit => {
      const rows = products.filter(p => p.unit === unit).map(p => ({ sku: p.sku, name: p.name, stock: p.onHand, order: p.recommended }));
      return <div className="comparison-chart" key={unit}><h3>Товары в {unit === 'м' ? 'метрах' : 'штуках'} <span>{rows.length} позиций</span></h3><div style={{ height: Math.max(210, rows.length * 66 + 65) }}><ResponsiveContainer width="100%" height="100%"><BarChart data={rows} layout="vertical" margin={{ left: 0, right: 24, bottom: 8, top: 8 }} barGap={3}>
        <CartesianGrid horizontal={false} stroke="#e9eceb"/><XAxis type="number" tick={{ fontSize: 11, fill: '#66736e' }} unit={' ' + unit} axisLine={false} tickLine={false}/><YAxis type="category" dataKey="sku" width={132} tick={{ fontSize: 11, fill: '#4f5b56' }} axisLine={false} tickLine={false}/>
        <Tooltip formatter={value => formatNumber(Number(value)) + ' ' + unit} contentStyle={{ borderRadius: 8, fontSize: 12, borderColor: '#dce2de' }}/><Legend iconType="square" wrapperStyle={{ fontSize: 12 }}/><Bar dataKey="stock" name="На складе" fill="#b0bab6" radius={[0, 3, 3, 0]} maxBarSize={13} isAnimationActive={false}/><Bar dataKey="order" name="Рекомендовано заказать" fill="#236c61" radius={[0, 3, 3, 0]} maxBarSize={13} isAnimationActive={false}/>
      </BarChart></ResponsiveContainer></div></div>;
    })}
  </section>;
}
