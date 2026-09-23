import { Fragment, useEffect, useMemo, useState } from 'react';
import { ArrowDownToLine, ArrowUpDown, Box, CalendarDays, ChevronDown, ChevronRight, CircleAlert, Filter, PackageCheck, Search, ShieldCheck, ShoppingCart, TrendingUp, X } from 'lucide-react';
import { loadDashboard } from './api/client';
import type { DemoSnapshot, DemoProduct } from './types/demo';
import { ProductArt } from './components/ProductArt';
import { Analytics } from './components/Analytics';
import { RecommendationDetails } from './components/RecommendationDetails';
import { exportCsv } from './utils/csv';

const fmt = (n:number) => n.toLocaleString('ru-RU');
const date = (value:string) => new Date(value).toLocaleDateString('ru-RU');
const statusClass = (p:DemoProduct) => p.status === 'Дефицит' ? 'danger' : p.status === 'В норме' ? 'success' : 'warning';

export default function App() {
  const [data,setData] = useState<DemoSnapshot|null>(null);
  const [error,setError] = useState('');
  const [loading,setLoading] = useState(true);
  const [query,setQuery] = useState('');
  const [supplier,setSupplier] = useState('');
  const [category,setCategory] = useState('');
  const [status,setStatus] = useState('');
  const [showFilters,setShowFilters] = useState(false);
  const [grouped,setGrouped] = useState(false);
  const [ascending,setAscending] = useState<boolean|null>(null);
  const [expanded,setExpanded] = useState<string|null>(null);
  const [selected,setSelected] = useState<Set<string>>(new Set());
  const [notice,setNotice] = useState('');
  async function load() {
    setLoading(true); setError('');
    try { setData(await loadDashboard()); }
    catch(e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить данные'); }
    finally { setLoading(false); }
  }
  useEffect(()=>{void load();},[]);
  const products = data?.products ?? [];
  const filtered = useMemo(()=>{
    const term=query.trim().toLocaleLowerCase('ru');
    const result=(data?.products ?? []).filter(p=>
      (!supplier || p.supplier===supplier) && (!category || p.category===category) &&
      (!status || p.status===status) && [p.name,p.sku,p.supplier].some(s=>s.toLocaleLowerCase('ru').includes(term)));
    if(ascending !== null) result.sort((a,b)=>(ascending ? 1 : -1)*a.sku.localeCompare(b.sku,'ru'));
    if(grouped) result.sort((a,b)=>a.supplier.localeCompare(b.supplier,'ru'));
    return result;
  },[data,query,supplier,category,status,ascending,grouped]);
  const selectedProducts = filtered.filter(p=>selected.has(p.sku));
  const allSelected = filtered.length>0 && selectedProducts.length===filtered.length;
  const units = [...new Set(filtered.map(p=>p.unit))].map(unit=>fmt(filtered.filter(p=>p.unit===unit).reduce((s,p)=>s+p.recommended,0))+' '+unit).join(' + ') || '0 ед.';
  function toggle(sku:string) {setSelected(prev=>{const next=new Set(prev);if(next.has(sku))next.delete(sku);else next.add(sku);return next;});}
  function toggleAll(){setSelected(prev=>{const next=new Set(prev);filtered.forEach(p=>allSelected?next.delete(p.sku):next.add(p.sku));return next;});}
  function download(chosen:DemoProduct[]){exportCsv(chosen);setNotice('CSV подготовлен: '+chosen.length+' позиций. Заказ поставщикам не отправлялся.');}
  const kpis=[
    {title:'Позиций к заказу',value:fmt(filtered.filter(p=>p.recommended>0).length),unit:'позиций',icon:ShoppingCart},
    {title:'Рекомендуемый объём',value:units,unit:'по единицам измерения',icon:Box},
    {title:'Высокий риск дефицита',value:fmt(filtered.filter(p=>p.status==='Дефицит').length),unit:'позиций',icon:CircleAlert},
    {title:'Пример исключения аномалий',value:fmt(filtered.filter(p=>p.anomalyNote).length),unit:'позиций',icon:ShieldCheck},
    {title:'Пример упущенного спроса',value:fmt(filtered.filter(p=>p.stockoutNote).length),unit:'позиций',icon:TrendingUp}
  ];
  return <>
    <header className="topbar"><div className="topbar-inner">
      <a className="brand" href="#orders" aria-label="Электрокомплект — рекомендации"><span className="brand-symbol"><i/><i/><i/></span><span><strong>Электрокомплект</strong><small>ekt.kz</small></span></a>
      <nav aria-label="Разделы экрана"><a className="active" href="#orders">Заказы</a><a href="#analytics">Аналитика</a></nav>
      <div className="header-meta"><span className="period"><CalendarDays size={19}/> Август 2025</span><span className="avatar" aria-label="Менеджер закупок">ББ</span></div>
    </div></header>
    <main id="orders">
      <div className="page-heading"><div><div className="eyebrow">УПРАВЛЕНИЕ ЗАКУПКАМИ <span>ДЕМО</span></div><h1>Рекомендации к заказу</h1><p>Оптимальный запас начинается с точного решения</p></div><button className="primary" disabled={!selectedProducts.length} onClick={()=>download(selectedProducts)}><ShoppingCart size={19}/> Выгрузить выбранное{selectedProducts.length>0?' ('+selectedProducts.length+')':''}</button></div>
      <div className="update-line"><span className="live-dot"/> Подготовленный демонстрационный набор <span className="divider">/</span><span>{data?'Обновлён '+date(data.updatedAt)+' в '+new Date(data.updatedAt).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Almaty'})+' (UTC+5)':'Загрузка данных…'}</span></div>
      {error && <div className="error" role="alert"><CircleAlert size={20}/><span>{error}</span><button onClick={()=>void load()}>Повторить</button></div>}
      {notice && <div className="notice" role="status"><PackageCheck size={18}/>{notice}<button aria-label="Закрыть уведомление" onClick={()=>setNotice('')}><X size={16}/></button></div>}
      {loading ? <div className="loading" role="status">Загружаем рекомендации…</div> : data && <>
      <section className="kpi-grid" aria-label="Ключевые показатели">{kpis.map(({title,value,unit,icon:Icon},i)=><div className="kpi" key={title}><div className="kpi-title">{title}<Icon size={17} className={i===2?'risk-icon':''}/></div><strong className={i===2?'risk-value':''}>{value}</strong><small>{unit}</small></div>)}</section>
      <section aria-label="Рекомендации">
      <div className="toolbar"><label className="search"><Search size={20}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Поиск по товару, артикулу или поставщику…" aria-label="Поиск по товару, артикулу или поставщику"/>{query && <button aria-label="Очистить поиск" onClick={()=>setQuery('')}><X size={16}/></button>}</label><div className="toolbar-actions"><button className="secondary" onClick={()=>download(filtered)} disabled={!filtered.length}><ArrowDownToLine size={17}/><span>Экспорт CSV</span></button><button className={'secondary '+(showFilters?'pressed':'')} onClick={()=>setShowFilters(!showFilters)} aria-expanded={showFilters} aria-controls="filters"><Filter size={17}/> Фильтры{[supplier,category,status].filter(Boolean).length>0 && <b className="filter-count">{[supplier,category,status].filter(Boolean).length}</b>}</button></div></div>
      {showFilters && <div className="filters" id="filters">
        <label>Поставщик<select value={supplier} onChange={e=>setSupplier(e.target.value)}><option value="">Все поставщики</option>{[...new Set(products.map(p=>p.supplier))].map(v=><option key={v}>{v}</option>)}</select></label>
        <label>Категория<select value={category} onChange={e=>setCategory(e.target.value)}><option value="">Все категории</option>{[...new Set(products.map(p=>p.category))].map(v=><option key={v}>{v}</option>)}</select></label>
        <label>Срочность<select value={status} onChange={e=>setStatus(e.target.value)}><option value="">Все статусы</option>{[...new Set(products.map(p=>p.status))].map(v=><option key={v}>{v}</option>)}</select></label>
        <button className="text-button" onClick={()=>{setSupplier('');setCategory('');setStatus('');setQuery('');}}>Сбросить</button>
      </div>}
      <div className="table-context"><span>Рекомендации <b>{filtered.length}</b></span><label><input type="checkbox" checked={grouped} onChange={e=>setGrouped(e.target.checked)}/> По поставщикам</label></div>
      <div className="table-wrap"><table><caption className="sr-only">Рекомендации закупок — демонстрационные данные. Откройте товар для объяснения.</caption><thead><tr><th className="check-cell"><input type="checkbox" aria-label="Выбрать все найденные позиции" checked={allSelected} onChange={toggleAll} disabled={!filtered.length}/></th><th>Товар</th><th><button className="sort" onClick={()=>setAscending(ascending===null?true:!ascending)}>Артикул <ArrowUpDown size={13}/></button></th><th>Остаток</th><th>В пути</th><th>Рекомендуемый<br/>заказ</th><th>Поставщик</th><th>Ожидаемая<br/>поставка</th><th>Статус</th><th><span className="sr-only">Подробности</span></th></tr></thead>
      <tbody>{filtered.map((p,index)=><Fragment key={p.sku}>
        {grouped && (index===0 || filtered[index-1].supplier!==p.supplier) && <tr className="supplier-row"><th colSpan={10} scope="rowgroup">{p.supplier}</th></tr>}
        <tr className={expanded===p.sku?'expanded-row':selected.has(p.sku)?'selected-row':''}>
          <td className="check-cell"><input type="checkbox" aria-label={'Выбрать '+p.name} checked={selected.has(p.sku)} onChange={()=>toggle(p.sku)}/></td>
          <td><button className="product" onClick={()=>setExpanded(expanded===p.sku?null:p.sku)} aria-expanded={expanded===p.sku}><ProductArt kind={p.kind}/><span><strong>{p.name}</strong><small>{p.subtitle}</small></span></button></td>
          <td className="muted sku">{p.sku}</td><td className={p.status==='Дефицит'?'stock-danger':''}>{fmt(p.onHand)} {p.unit}</td><td className="muted">{fmt(p.inTransit)} {p.unit}</td><td className="order-qty">{fmt(p.recommended)} {p.unit}</td><td className="muted">{p.supplier}</td><td className="muted">{p.expectedDate?date(p.expectedDate):'Не указана'}</td><td><span className={'badge '+statusClass(p)}>{p.status}</span></td><td><button className="expand-button" aria-label={'Объяснение: '+p.sku} aria-expanded={expanded===p.sku} onClick={()=>setExpanded(expanded===p.sku?null:p.sku)}>{expanded===p.sku?<ChevronDown size={16}/>:<ChevronRight size={16}/>}</button></td>
        </tr>
        {expanded===p.sku && <tr><td colSpan={10} className="details-cell"><RecommendationDetails product={p}/></td></tr>}
      </Fragment>)}</tbody></table>{!filtered.length && <div className="empty"><Search size={28}/><h3>Позиции не найдены</h3><p>Измените запрос или сбросьте фильтры.</p><button className="secondary" onClick={()=>{setQuery('');setCategory('');setSupplier('');setStatus('');}}>Сбросить фильтры</button></div>}</div>
      <div className="table-footer"><span>Показано {filtered.length} из {products.length} позиций</span><span>Нажмите на товар, чтобы увидеть объяснение <ChevronRight size={14}/></span></div>
      </section>
      <Analytics products={filtered}/>
      <footer><span><ShieldCheck size={15}/> Решение о закупке остаётся за менеджером</span><span>Демонстрационные данные · отправка поставщикам отключена</span></footer>
      </>}
    </main>
  </>;
}
