import { Search, X, SlidersHorizontal } from 'lucide-react';
import type { ReactNode } from 'react';
import type { DemoProduct } from '../types/demo';
import type { Filters } from '../utils/presentation';

interface Props { products: DemoProduct[]; value: Filters; onChange: (next: Filters) => void; children?: ReactNode }
export function FiltersBar({ products, value, onChange, children }: Props) {
  const set = <K extends keyof Filters>(key: K, next: Filters[K]) => onChange({ ...value, [key]: next });
  const hasFilters = !!(value.search || value.supplier || value.status || value.category || value.onlyOrders || value.signal !== 'all');
  return <div className="filters-area">
    <div className="filters-main">
      <label className="search-field"><Search size={18} aria-hidden="true"/><input aria-label="Поиск по товару, артикулу или поставщику" placeholder="Товар, артикул или поставщик" value={value.search} onChange={e => set('search', e.target.value)}/>{value.search && <button className="icon-button" aria-label="Очистить поиск" onClick={() => set('search', '')}><X size={16}/></button>}</label>
      <label className="select-field"><span className="sr-only">Поставщик</span><select value={value.supplier} onChange={e => set('supplier', e.target.value)}><option value="">Все поставщики</option>{[...new Set(products.map(p => p.supplier))].sort().map(s => <option key={s}>{s}</option>)}</select></label>
      <label className="select-field"><span className="sr-only">Уровень риска</span><select value={value.status} onChange={e => set('status', e.target.value)}><option value="">Все статусы</option>{[...new Set(products.map(p => p.status))].map(s => <option key={s}>{s}</option>)}</select></label>
    </div>
    <div className="filters-secondary">
      <label className="compact-select"><SlidersHorizontal size={14} aria-hidden="true"/><span className="sr-only">Категория</span><select value={value.category} onChange={e => set('category', e.target.value)}><option value="">Все категории</option>{[...new Set(products.map(p => p.category))].map(s => <option key={s}>{s}</option>)}</select></label>
      <label className="checkbox-label"><input type="checkbox" checked={value.onlyOrders} onChange={e => set('onlyOrders', e.target.checked)}/>Только к заказу</label>
      {value.signal !== 'all' && <button className="filter-chip" onClick={() => set('signal', 'all')}>{value.signal === 'anomaly' ? 'Исключённые аномалии' : 'Упущенный спрос'}<X size={12}/></button>}
      {children}
      {hasFilters && <button className="text-button reset-filters" onClick={() => onChange({ ...value, search: '', supplier: '', status: '', category: '', onlyOrders: false, signal: 'all' })}>Сбросить</button>}
    </div>
  </div>;
}
