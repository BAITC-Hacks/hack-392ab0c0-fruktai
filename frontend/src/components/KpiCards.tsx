import { ShoppingBag, Package, AlertTriangle, ShieldCheck, TrendingUp } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
import { formatNumber, quantitySummary } from '../utils/presentation';

interface Props {
  products: DemoProduct[];
  onSelect: (type: 'orders' | 'risk' | 'anomaly' | 'stockout') => void;
}
export function KpiCards({ products, onSelect }: Props) {
  const values = [
    { title: 'Позиций к заказу', value: formatNumber(products.filter(p => p.recommended > 0).length), note: 'позиций в текущей выборке', Icon: ShoppingBag, action: 'orders' as const },
    { title: 'Объём закупки', value: quantitySummary(products), note: 'разные единицы учтены отдельно', Icon: Package },
    { title: 'Риск дефицита', value: formatNumber(products.filter(p => p.status === 'Дефицит').length), note: 'позиций требуют внимания', Icon: AlertTriangle, action: 'risk' as const },
    { title: 'Аномалии исключены', value: formatNumber(products.filter(p => p.anomalyNote).length), note: 'позиций в демонстрационном примере', Icon: ShieldCheck, action: 'anomaly' as const },
    { title: 'Спрос восстановлен', value: formatNumber(products.filter(p => p.stockoutNote).length), note: 'позиций со stockout · демо', Icon: TrendingUp, action: 'stockout' as const },
  ];
  return <section className="kpis" aria-label="Показатели текущей выборки">{values.map(({ title, value, note, Icon, action }) => {
    const content = <><span className="kpi-label">{title}<Icon size={17} aria-hidden="true"/></span><strong className={action === 'risk' ? 'risk-number' : ''}>{value}</strong><span className="kpi-note">{note}</span></>;
    return action ? <button className="kpi" key={title} onClick={() => onSelect(action)} title="Показать соответствующие позиции">{content}</button> : <div className="kpi" key={title}>{content}</div>;
  })}</section>;
}
