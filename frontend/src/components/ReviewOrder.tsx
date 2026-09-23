import { useState } from 'react';
import { ArrowDownToLine, ShieldCheck, Package } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
import { formatNumber, quantitySummary, positionWord, supplierWord } from '../utils/presentation';
interface Props { products: DemoProduct[]; onExport: () => void }
export function ReviewOrder({ products, onExport }: Props) {
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState('');
  const suppliers = [...new Set(products.map(p => p.supplierId))].sort();
  return <>
    <div className="view-heading"><span className="eyebrow">Проверка перед выгрузкой</span><h2 id="drawer-title">Проверьте план закупки</h2><p>Подтвердите выбранные позиции и скачайте рекомендации одним CSV-файлом.</p></div>
    <div className="review-summary"><Package size={22}/><strong>{quantitySummary(products)}</strong><span>{products.length} {positionWord(products.length)} · {suppliers.length} {supplierWord(suppliers.length)}</span></div>
    <div className="review-groups">{suppliers.map(supplier => <section key={supplier}><h3>{products.find(p => p.supplierId === supplier)?.supplier}</h3>{products.filter(p => p.supplierId === supplier).map(p => <div className="review-row" key={p.sku}><span><strong>{p.name}</strong><small>{p.sku}</small></span><b>{formatNumber(p.recommended)} {p.unit}</b></div>)}</section>)}</div>
    <div className="review-footer"><label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={e => { setConfirmed(e.target.checked); setError(''); }}/>Я проверил(а) позиции и объёмы</label>{error && <p className="field-error" role="alert">{error}</p>}<button className="primary-button full-width" onClick={() => { if (!confirmed) { setError('Подтвердите проверку позиций перед экспортом.'); return; } onExport(); }}><ArrowDownToLine size={18}/>Подтвердить и экспортировать CSV</button><p className="helper"><ShieldCheck size={14}/>Подтверждение относится к локальной выгрузке. Заказ не отправляется поставщику и не сохраняется в 1С.</p></div>
  </>;
}
