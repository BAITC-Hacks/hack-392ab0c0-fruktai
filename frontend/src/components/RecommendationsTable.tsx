import { Fragment, useEffect, useRef } from 'react';
import { ChevronRight, ArrowDownWideNarrow, ArrowDown, ChevronsUpDown, Truck } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
import type { SortKey } from '../utils/presentation';
import { formatNumber, shortReason, positionWord, quantitySummary } from '../utils/presentation';
import { StatusBadge } from './StatusBadge';

interface Props {
  products: DemoProduct[]; selected: Set<string>; activeSku: string | null;
  grouped: boolean; sort: SortKey; onSort: (value: SortKey) => void;
  onOpen: (product: DemoProduct) => void; onToggle: (sku: string) => void; onToggleAll: () => void;
}
export function RecommendationsTable({ products, selected, activeSku, grouped, sort, onSort, onOpen, onToggle, onToggleAll }: Props) {
  const selectedCount = products.filter(p => selected.has(p.sku)).length;
  const checkbox = useRef<HTMLInputElement>(null);
  useEffect(() => { if (checkbox.current) checkbox.current.indeterminate = selectedCount > 0 && selectedCount < products.length; }, [selectedCount, products.length]);
  const rows = grouped ? [...products].sort((a, b) => a.supplierId.localeCompare(b.supplierId)) : products;
  const sortButton = (label: string, key: SortKey) => <button className="column-sort" onClick={() => onSort(key)}>{label}{sort === key ? <ArrowDown size={12}/> : <ChevronsUpDown size={12}/>}</button>;
  return <>
    <div className="table-subheading"><span><b>{products.length}</b> {positionWord(products.length)} <span className="muted">· значения из последнего расчёта</span></span><label className="sort-select"><ArrowDownWideNarrow size={14}/><span className="sr-only">Сортировка</span><select value={sort} onChange={e => onSort(e.target.value as SortKey)}><option value="risk">Сначала дефицит</option><option value="quantity">Больше к заказу</option><option value="cover">Меньше дней покрытия</option><option value="sku">По артикулу</option><option value="supplier">По поставщику</option></select></label></div>
    <div className="desktop-table"><div className="table-scroll" tabIndex={0} role="region" aria-label="Таблица рекомендаций с горизонтальной прокруткой">
      <table><caption className="sr-only">Рекомендации закупок из API. Прогноз — на срок поставки; покрытие учитывает остаток и товар в пути.</caption><thead><tr>
        <th scope="col" className="select-column"><input ref={checkbox} type="checkbox" aria-label="Выбрать все найденные позиции" checked={products.length > 0 && selectedCount === products.length} onChange={onToggleAll}/></th>
        <th scope="col" className="product-column" aria-sort={sort === 'sku' ? 'ascending' : undefined}>{sortButton('Товар / артикул', 'sku')}</th>
        <th scope="col" aria-sort={sort === 'supplier' ? 'ascending' : undefined}>{sortButton('Поставщик', 'supplier')}</th>
        <th scope="col" className="numeric">На складе</th><th scope="col" className="numeric">В пути</th>
        <th scope="col" className="numeric" aria-sort={sort === 'cover' ? 'ascending' : undefined}>{sortButton('Покрытие', 'cover')}</th>
        <th scope="col" className="numeric" title="Прогноз спроса на срок поставки">Прогноз</th>
        <th scope="col" className="numeric order-heading" aria-sort={sort === 'quantity' ? 'descending' : undefined}>{sortButton('Заказать', 'quantity')}</th>
        <th scope="col" aria-sort={sort === 'risk' ? 'ascending' : undefined}>{sortButton('Срочность', 'risk')}</th>
        <th scope="col"><span className="sr-only">Подробнее</span></th>
      </tr></thead><tbody>{rows.map((p, index) => <Fragment key={p.sku}>
        {grouped && (index === 0 || rows[index - 1].supplierId !== p.supplierId) && <tr className="supplier-row"><th colSpan={10} scope="rowgroup"><div><Truck size={15}/>{p.supplier}<span>{rows.filter(r => r.supplierId === p.supplierId).length} позиций</span><b>{quantitySummary(rows.filter(r => r.supplierId === p.supplierId))}</b></div></th></tr>}
        <tr className={activeSku === p.sku ? 'active-row' : selected.has(p.sku) ? 'selected-row' : ''}>
          <td className="select-column"><input type="checkbox" checked={selected.has(p.sku)} onChange={() => onToggle(p.sku)} aria-label={'Выбрать ' + p.name}/></td>
          <td className="product-column"><button className="product-cell" onClick={() => onOpen(p)} aria-label={'Открыть расчёт: ' + p.name} aria-haspopup="dialog" title={shortReason(p)}><span><strong>{p.name}</strong><small>{p.sku}</small></span></button></td>
          <td className="supplier-cell"><span>{p.supplier}</span><small>{p.calculation.lead_time_days} дн. поставка</small></td>
          <td className={'numeric ' + (p.onHand === 0 ? 'risk-text' : '')}>{formatNumber(p.onHand)} <small>{p.unit}</small></td>
          <td className="numeric">{formatNumber(p.inTransit)} <small>{p.unit}</small></td>
          <td className="numeric"><span className={p.calculation.days_of_cover < p.calculation.lead_time_days && p.calculation.avg_daily_demand > 0 ? 'coverage-low' : ''}>{p.calculation.avg_daily_demand > 0 ? formatNumber(p.calculation.days_of_cover) : '—'} <small>дн.</small></span></td>
          <td className="numeric">{formatNumber(p.calculation.forecast_demand)} <small>{p.unit}</small></td>
          <td className="numeric order-number">{formatNumber(p.recommended)} <small>{p.unit}</small></td>
          <td><StatusBadge status={p.status}/></td><td><button className="icon-button" aria-label={'Подробнее: ' + p.sku} title="Открыть расчёт" onClick={() => onOpen(p)}><ChevronRight size={17}/></button></td>
        </tr>
      </Fragment>)}</tbody></table>
    </div></div>
    <div className="mobile-products">{rows.map(p => <article className={'mobile-product ' + (selected.has(p.sku) ? 'selected-row' : '')} key={p.sku}><div className="mobile-product-top"><label><input type="checkbox" checked={selected.has(p.sku)} onChange={() => onToggle(p.sku)} aria-label={'Выбрать ' + p.name}/></label><StatusBadge status={p.status}/></div><h3>{p.name}</h3><p className="muted">{p.sku} · {p.supplier}</p><div className="mobile-product-bottom"><span>Заказать <strong>{formatNumber(p.recommended)} {p.unit}</strong></span><button className="text-button" aria-label={'Открыть расчёт: ' + p.name} onClick={() => onOpen(p)}>Открыть расчёт <ChevronRight size={14}/></button></div></article>)}</div>
  </>;
}
