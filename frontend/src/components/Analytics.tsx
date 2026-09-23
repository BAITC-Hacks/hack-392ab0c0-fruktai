import { ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import type { DemoProduct, DemoStatus } from '../types/demo';
const colors = ['#1768c5', '#81baff', '#d9dfeb'];
const statuses: DemoStatus[] = ['Дефицит', 'Пограничный остаток', 'В норме'];
export function Analytics({ products }: { products: DemoProduct[] }) {
  const distribution = statuses.map((name) => ({ name, value: products.filter(p => p.status === name).length }));
  const pieces = products.filter(p => p.unit === 'шт.').map(p => ({ name: p.sku, 'Остаток, шт.': p.onHand, 'Заказ, шт.': p.recommended }));
  return <section className="panel analytics" id="analytics">
    <div className="panel-heading"><h2>Аналитика рекомендаций</h2><span>По текущему фильтру</span></div>
    <div className="analytics-grid">
      <div><h3>Структура рекомендаций</h3><div className="donut-layout">
        <div className="donut"><ResponsiveContainer width="100%" height={210}><PieChart><Pie data={distribution} dataKey="value" innerRadius={70} outerRadius={96} strokeWidth={3} isAnimationActive={false}>{distribution.map((d,i) => <Cell key={d.name} fill={colors[i]}/>)}</Pie></PieChart></ResponsiveContainer><div className="donut-label"><strong>{products.length}</strong><span>позиций</span></div></div>
        <ul className="chart-legend">{distribution.map((d,i)=><li key={d.name}><span className="legend-dot" style={{background: colors[i]}}/><span>{d.name}</span><strong>{d.value}</strong><small>{products.length ? Math.round(d.value/products.length*100) : 0}%</small></li>)}</ul>
      </div></div>
      <div className="comparison"><h3>Остаток и рекомендованный заказ <span>шт.</span></h3><p className="chart-caption">Товары в штуках · кабель в метрах не включён</p>
        <div style={{width:'100%',height:210}}><ResponsiveContainer><AreaChart data={pieces} margin={{top:12,right:16,left:0,bottom:0}}>
          <defs><linearGradient id="orderFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2281eb" stopOpacity={0.22}/><stop offset="100%" stopColor="#2281eb" stopOpacity={0.02}/></linearGradient></defs>
          <CartesianGrid stroke="#eaf0f8" vertical={false}/><XAxis dataKey="name" tick={{fontSize:10,fill:'#7183a5'}} tickFormatter={value=>String(value).slice(0,10)} axisLine={false} tickLine={false}/><YAxis tick={{fontSize:11,fill:'#7183a5'}} axisLine={false} tickLine={false}/><Tooltip/><Legend iconType="circle" wrapperStyle={{fontSize:12}}/>
          <Area type="linear" dataKey="Заказ, шт." stroke="#1977e7" strokeWidth={2.5} fill="url(#orderFill)" dot={{r:4,fill:'#1977e7'}} isAnimationActive={false}/><Area type="linear" dataKey="Остаток, шт." stroke="#9bacbf" fill="transparent" strokeDasharray="4 4" isAnimationActive={false}/>
        </AreaChart></ResponsiveContainer></div>
      </div>
    </div>
  </section>;
}
