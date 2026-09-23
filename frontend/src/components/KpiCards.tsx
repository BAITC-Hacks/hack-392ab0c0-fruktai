import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
import { formatNumber, quantitySummary, positionWord } from '../utils/presentation';

interface Props {
  products: DemoProduct[];
  onSelect: (type: 'orders' | 'risk' | 'anomaly' | 'stockout') => void;
}
export function KpiCards({ products, onSelect }: Props) {
  const [expanded, setExpanded] = useState(false);
  const regionId = useId();
  const values = [
    { title: 'Позиций к заказу', value: formatNumber(products.filter(p => p.recommended > 0).length), note: positionWord(products.filter(p => p.recommended > 0).length) + ' в выборке', action: 'orders' as const },
    { title: 'Объём закупки', value: quantitySummary(products), note: 'по единицам измерения' },
    { title: 'Риск дефицита', value: formatNumber(products.filter(p => p.status === 'Дефицит').length), note: positionWord(products.filter(p => p.status === 'Дефицит').length), action: 'risk' as const },
    { title: 'Аномалии исключены', value: formatNumber(products.filter(p => p.anomalyNote).length), note: positionWord(products.filter(p => p.anomalyNote).length), action: 'anomaly' as const },
    { title: 'Упущенный спрос', value: formatNumber(products.filter(p => p.stockoutNote).length), note: positionWord(products.filter(p => p.stockoutNote).length) + ' с компенсацией', action: 'stockout' as const },
  ];
  return <section className="kpi-summary" aria-label="Показатели текущей выборки"><div className={'kpis' + (expanded ? ' is-expanded' : '')} id={regionId}>{values.map(({ title, value, note, action }) => {
    const content = <><span className="kpi-label">{title}</span><strong className={action === 'risk' ? 'risk-number' : ''}>{value}</strong><span className="kpi-note">{note}</span></>;
    return action ? <button className="kpi" key={title} onClick={() => onSelect(action)} title="Показать соответствующие позиции">{content}</button> : <div className="kpi" key={title}>{content}</div>;
  })}</div><button className="kpi-mobile-toggle text-button" aria-expanded={expanded} aria-controls={regionId} onClick={() => setExpanded(!expanded)}>{expanded ? 'Свернуть показатели' : 'Все показатели'}<ChevronDown size={15} aria-hidden="true"/></button></section>;
}
