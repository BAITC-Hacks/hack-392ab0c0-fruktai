import { Fragment, useEffect, useRef } from 'react';
import { ChevronRight, ArrowDownWideNarrow } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
import type { SortKey } from '../utils/presentation';
import { formatNumber, shortReason } from '../utils/presentation';
import { ProductArt } from './ProductArt';
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
  const rows = grouped ? [...products].sort((a, b) => a.supplier.localeCompare(b.supplier, 'ru')) : products;
  return <>
    <div className="table-subheading"><span><b>{products.length}</b> позиций <span className="muted">· нажмите на товар для объяснения</span></span><label className="sort-select"><ArrowDownWideNarrow size={14}/><span className="sr-only">Сортировка</span><select value={sort} onChange={e => onSort(e.target.value as SortKey)}><option value="risk">Сначала дефицит</option><option value="sku">По артикулу</option><option value="supplier">По поставщику</option></select></label></div>
    <div className="desktop-table"><div className="table-scroll" tabIndex={0} role="region" aria-label="Таблица рекомендаций с горизонтальной прокруткой">
      <table><caption className="sr-only">Демонстрационные рекомендации закупок</caption><thead><tr>
        <th scope="col" className="select-column"><input ref={checkbox} type="checkbox" aria-label="Выбрать все найденные позиции" checked={products.length > 0 && selectedCount === products.length} onChange={onToggleAll}/></th>
        <th scope="col" className="product-column">Товар / артикул</th><th scope="col">Поставщик</th><th scope="col" className="numeric">На складе</th><th scope="col" className="numeric">В пути</th><th scope="col" className="numeric order-heading">Заказать</th><th scope="col">Срочность</th><th scope="col">Обоснование</th><th scope="col"><span className="sr-only">Подробнее</span></th>
      </tr></thead><tbody>{rows.map((p, index) => <Fragment key={p.sku}>
        {grouped && (index === 0 || rows[index - 1].supplier !== p.supplier) && <tr className="supplier-row"><th colSpan={9} scope="rowgroup">{p.supplier} <span>{rows.filter(r => r.supplier === p.supplier).length} позиций</span></th></tr>}
        <tr className={activeSku === p.sku ? 'active-row' : selected.has(p.sku) ? 'selected-row' : ''}>
          <td className="select-column"><input type="checkbox" checked={selected.has(p.sku)} onChange={() => onToggle(p.sku)} aria-label={'Выбрать ' + p.name}/></td>
          <td className="product-column"><button className="product-cell" onClick={() => onOpen(p)} aria-label={'Открыть расчёт: ' + p.name} aria-haspopup="dialog"><ProductArt kind={p.kind}/><span><strong>{p.name}</strong><small>{p.sku}</small></span></button></td>
          <td className="supplier-cell">{p.supplier}</td><td className={'numeric ' + (p.status === 'Дефицит' ? 'risk-text' : '')}>{formatNumber(p.onHand)} <small>{p.unit}</small></td><td className="numeric">{formatNumber(p.inTransit)} <small>{p.unit}</small></td><td className="numeric order-number">{formatNumber(p.recommended)} <small>{p.unit}</small></td><td><StatusBadge status={p.status}/></td><td className="reason-cell">{shortReason(p)}</td><td><button className="icon-button" aria-label={'Подробнее: ' + p.sku} onClick={() => onOpen(p)}><ChevronRight size={17}/></button></td>
        </tr>
      </Fragment>)}</tbody></table>
    </div></div>
    <div className="mobile-products">{rows.map(p => <article className={'mobile-product ' + (selected.has(p.sku) ? 'selected-row' : '')} key={p.sku}><div className="mobile-product-top"><label><input type="checkbox" checked={selected.has(p.sku)} onChange={() => onToggle(p.sku)} aria-label={'Выбрать ' + p.name}/></label><StatusBadge status={p.status}/></div><h3>{p.name}</h3><p className="muted">{p.sku} · {p.supplier}</p><div className="mobile-product-bottom"><span>Заказать <strong>{formatNumber(p.recommended)} {p.unit}</strong></span><button className="text-button" onClick={() => onOpen(p)}>Открыть расчёт <ChevronRight size={14}/></button></div></article>)}</div>
  </>;
}
