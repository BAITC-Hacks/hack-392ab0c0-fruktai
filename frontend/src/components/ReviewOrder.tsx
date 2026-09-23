import { useState } from 'react';
import { ArrowDownToLine, ShieldCheck, Package } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
import { formatNumber, quantitySummary, positionWord, supplierWord } from '../utils/presentation';
interface Props { products: DemoProduct[]; onExport: (format: 'csv' | 'xlsx') => Promise<void> }
export function ReviewOrder({ products, onExport }: Props) {
  const [format, setFormat] = useState<'csv' | 'xlsx'>('csv');
  const [exporting, setExporting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState('');
  const suppliers = [...new Set(products.map(p => p.supplierId))].sort();
  return <>
    <div className="view-heading"><span className="eyebrow">Проверка перед выгрузкой</span><h2 id="drawer-title">Проверьте план закупки</h2><p>Подтвердите выбранные позиции и скачайте рекомендации файлом CSV или Excel.</p></div>
    <div className="review-summary"><Package size={22}/><strong>{quantitySummary(products)}</strong><span>{products.length} {positionWord(products.length)} · {suppliers.length} {supplierWord(suppliers.length)}</span></div>
    <div className="review-groups">{suppliers.map(supplier => <section key={supplier}><h3>{products.find(p => p.supplierId === supplier)?.supplier}</h3>{products.filter(p => p.supplierId === supplier).map(p => <div className="review-row" key={p.sku}><span><strong>{p.name}</strong><small>{p.sku}</small></span><b>{formatNumber(p.recommended)} {p.unit}</b></div>)}</section>)}</div>
    <div className="review-footer"><label>Формат экспорта<select aria-label="Формат экспорта" value={format} onChange={e => setFormat(e.target.value as 'csv' | 'xlsx')}><option value="csv">CSV</option><option value="xlsx">Excel XLSX</option></select></label><label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={e => { setConfirmed(e.target.checked); setError(''); }}/>Я проверил(а) позиции и объёмы</label>{error && <p className="field-error" role="alert">{error}</p>}<button className="primary-button full-width" disabled={exporting} onClick={async () => { if (!confirmed) { setError('Подтвердите проверку позиций перед экспортом.'); return; } setExporting(true); try { await onExport(format); } catch (problem) { setError(problem instanceof Error ? problem.message : 'Ошибка экспорта'); } finally { setExporting(false); } }}><ArrowDownToLine size={18}/>{exporting ? 'Подготовка…' : 'Подтвердить и экспортировать ' + format.toUpperCase()}</button><p className="helper"><ShieldCheck size={14}/>Подтверждение относится к локальной выгрузке. Заказ не отправляется поставщику и не сохраняется в 1С.</p></div>
  </>;
}
