import { useEffect, useRef, useState } from 'react';
import { LayoutGrid, BarChart3, Database, Warehouse, ChevronRight, RefreshCw, ShoppingCart, Users, ShieldCheck, AlertTriangle, CalendarDays, CircleHelp, Check, X, Search, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { loadDashboard } from './api/client';
import type { DemoProduct, DemoSnapshot } from './types/demo';
import { filterProducts, initialFilters, formatDate, type Filters, type ScenarioDraft } from './utils/presentation';
import { exportCsv } from './utils/csv';
import { KpiCards } from './components/KpiCards';
import { FiltersBar } from './components/FiltersBar';
import { RecommendationsTable } from './components/RecommendationsTable';
import { Analytics, Comparison } from './components/Analytics';
import { Drawer } from './components/Drawer';
import { RecommendationDetails } from './components/RecommendationDetails';
import { AgentRunPanel } from './components/AgentRunPanel';
import { DataView } from './components/DataView';
import { ReviewOrder } from './components/ReviewOrder';
import { LoadingState } from './components/LoadingState';

type View = 'table' | 'comparison' | 'data';
const views = [
  { id: 'table' as const, label: 'Таблица', Icon: LayoutGrid },
  { id: 'comparison' as const, label: 'Сравнение', Icon: BarChart3 },
  { id: 'data' as const, label: 'Данные', Icon: Database },
];

export default function App() {
  const [data, setData] = useState<DemoSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [view, setView] = useState<View>('table');
  const [grouped, setGrouped] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeProduct, setActiveProduct] = useState<DemoProduct | null>(null);
  const [reviewProducts, setReviewProducts] = useState<DemoProduct[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ScenarioDraft>>({});
  const [agentOpen, setAgentOpen] = useState(false);
  const requestNumber = useRef(0);

  async function load() {
    const request = ++requestNumber.current;
    setLoading(true); setError('');
    try {
      const result = await loadDashboard();
      if (request !== requestNumber.current) return;
      setData(result);
      setSelected(previous => new Set([...previous].filter(sku => result.products.some(p => p.sku === sku))));
    } catch (problem) {
      if (request === requestNumber.current) setError(problem instanceof Error ? problem.message : 'Не удалось загрузить рекомендации.');
    } finally {
      if (request === requestNumber.current) setLoading(false);
    }
  }
  useEffect(() => { void load(); return () => { requestNumber.current++; }; }, []);

  const products = data?.products ?? [];
  const filtered = filterProducts(products, filters);
  const selectedProducts = products.filter(p => selected.has(p.sku));
  const visibleSelectedCount = filtered.filter(p => selected.has(p.sku)).length;
  const riskCount = products.filter(p => p.status === 'Дефицит').length;

  function toggle(sku: string) {
    setSelected(previous => {
      const next = new Set(previous);
      if (next.has(sku)) next.delete(sku); else next.add(sku);
      return next;
    });
  }
  function toggleAll() {
    setSelected(previous => {
      const next = new Set(previous);
      const allVisibleSelected = filtered.every(p => previous.has(p.sku));
      filtered.forEach(p => allVisibleSelected ? next.delete(p.sku) : next.add(p.sku));
      return next;
    });
  }
  function chooseKpi(type: 'orders' | 'risk' | 'anomaly' | 'stockout') {
    setView('table');
    setFilters({
      ...initialFilters,
      onlyOrders: type === 'orders',
      status: type === 'risk' ? 'Дефицит' : '',
      signal: type === 'anomaly' || type === 'stockout' ? type : 'all',
    });
  }
  function openReview() {
    const rows = selectedProducts.length ? selectedProducts : filtered;
    if (!rows.length) { setNotice('Нет позиций для выгрузки. Измените фильтры.'); return; }
    setReviewProducts(rows);
  }
  function setDraft(sku: string, draft: ScenarioDraft | undefined) {
    setDrafts(previous => {
      const next = { ...previous };
      if (draft) next[sku] = draft; else delete next[sku];
      return next;
    });
  }

  return <>
    <a className="skip-link" href="#main-content">Перейти к рекомендациям</a>
    <header className="app-header"><div className="brand"><span className="brand-mark" aria-hidden="true"><i/><i/><i/><i/></span><div><strong>Электрокомплект</strong><span>ekt.kz <span className="brand-divider">/</span> Закупки</span></div></div>
      <nav className="header-nav" aria-label="Основная навигация"><button className={view !== 'data' && !grouped ? 'is-active' : ''} onClick={() => { setView('table'); setGrouped(false); }}><ShoppingCart size={18}/>План закупок</button><button className={grouped ? 'is-active' : ''} onClick={() => { setView('table'); setGrouped(true); }}><Users size={18}/>Поставщики</button><button onClick={() => { setAgentOpen(true); document.getElementById('agent-run')?.scrollIntoView({ block: 'center' }); }}><ShieldCheck size={18}/>Ход анализа</button></nav>
      <div className="header-user"><span className="avatar">ББ</span><span><strong>Баймурат Б.</strong><small>Менеджер закупок</small></span></div>
    </header>
    <main id="main-content">
      <div className="breadcrumb"><span>Закупки</span><ChevronRight size={13}/><span>План пополнения</span></div>
      <div className="page-heading"><div><div className="title-row"><h1>План закупок</h1><span className="demo-badge">Демо</span></div><p>Рекомендации по пополнению склада с объяснением каждого заказа</p></div><div className="heading-actions"><button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={16}/>{loading ? 'Загрузка…' : 'Обновить данные'}</button><button className="primary-button" onClick={openReview}><ShoppingCart size={17}/>Проверить заказ{selectedProducts.length ? <span className="button-count">{selectedProducts.length}</span> : null}</button></div></div>
      <div className="context-row"><span><Warehouse size={14}/>Склад не указан в наборе</span><span><CalendarDays size={14}/>{data ? 'Срез: ' + formatDate(data.updatedAt) + ' · ' + new Date(data.updatedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }) + ' (UTC+5)' : 'Дата среза не получена'}</span><button className="context-link" onClick={() => setView('data')}>Источник и полнота данных <ChevronRight size={12}/></button></div>
      {error && <div className="error-banner" role="alert"><AlertTriangle size={20}/><div><strong>Не удалось обновить рекомендации</strong><p>{error}</p>{data && <p>На экране сохранён предыдущий набор.</p>}</div><button className="secondary-button" onClick={() => void load()}>Повторить загрузку</button></div>}
      {notice && <div className="notice-banner" role="status"><Check size={17}/><span>{notice}</span><button className="icon-button" aria-label="Закрыть уведомление" onClick={() => setNotice('')}><X size={16}/></button></div>}
      {loading && !data ? <LoadingState/> : data && <>
        <div className="attention-banner"><span className="alert-symbol"><AlertTriangle size={19}/></span><div><strong>Проверьте позиции с риском дефицита</strong><p>{riskCount} позиций в демонстрационном наборе требуют внимания. Начните с товаров без остатка.</p></div><button onClick={() => chooseKpi('risk')}>Показать позиции <ChevronRight size={16}/></button></div>
        <KpiCards products={filtered} onSelect={chooseKpi}/>
        <div className={'workspace ' + (!showAnalytics ? 'without-analytics' : '')} id="workspace">
          <aside className="workspace-nav"><nav aria-label="Представление данных">{views.map(({ id, label, Icon }) => <button key={id} className={view === id ? 'active' : ''} onClick={() => setView(id)} aria-current={view === id ? 'page' : undefined} title={label}><Icon size={19}/><span>{label}</span></button>)}</nav><div className="nav-note"><ShieldCheck size={18}/><p>Решение о закупке — за вами</p></div></aside>
          <div className="workspace-content">
            {view !== 'data' && <><FiltersBar products={products} value={filters} onChange={setFilters}/><div className="view-controls"><label className="checkbox-label"><input type="checkbox" checked={grouped} onChange={e => { setGrouped(e.target.checked); setView('table'); }}/>По поставщикам</label><button className="icon-button" aria-label={showAnalytics ? 'Скрыть аналитику' : 'Показать аналитику'} title={showAnalytics ? 'Скрыть аналитику' : 'Показать аналитику'} onClick={() => setShowAnalytics(!showAnalytics)}>{showAnalytics ? <PanelRightClose size={17}/> : <PanelRightOpen size={17}/>}</button></div></>}
            {view === 'data' ? <DataView data={data}/> : filtered.length === 0 ? <div className="empty-state"><Search size={30}/><h2>Подходящих позиций нет</h2><p>Попробуйте другой запрос или сбросьте фильтры.</p><button className="secondary-button" onClick={() => setFilters(initialFilters)}>Сбросить фильтры</button></div> : view === 'comparison' ? <Comparison products={filtered}/> : <RecommendationsTable products={filtered} selected={selected} activeSku={activeProduct?.sku ?? null} grouped={grouped} sort={filters.sort} onSort={sort => setFilters({ ...filters, sort })} onOpen={setActiveProduct} onToggle={toggle} onToggleAll={toggleAll}/>}
            {view !== 'data' && <div className="table-footer"><span>Показано <b>{filtered.length}</b> из {products.length} позиций</span><span>Данные примера · август 2025</span></div>}
            {selectedProducts.length > 0 && <div className="selection-bar"><span><Check size={16}/><b>Выбрано: {selectedProducts.length}</b>{selectedProducts.length > visibleSelectedCount && <small>Скрыто фильтрами: {selectedProducts.length - visibleSelectedCount}</small>}</span><div><button className="text-button" onClick={() => setSelected(new Set())}>Снять выбор</button><button className="primary-button" onClick={openReview}>Проверить и экспортировать <ChevronRight size={15}/></button></div></div>}
          </div>
          {showAnalytics && <Analytics products={filtered} onStatus={status => { setView('table'); setFilters({ ...filters, status }); }}/>}
        </div>
        <AgentRunPanel open={agentOpen} onChange={setAgentOpen}/>
        <div className="demo-disclosure"><CircleHelp size={16}/><p>Демонстрационный набор от {formatDate(data.updatedAt)} не отражает текущий склад. Реальный расчёт, прогноз и отправка заказов не подключены.</p><button className="text-button" onClick={() => { setView('data'); document.getElementById('workspace')?.scrollIntoView({ block: 'start' }); }}>Подробнее</button></div>
      </>}
      <footer className="app-footer"><span>Электрокомплект <span>·</span> Рабочее место закупок</span><span>HackAlem AI <span>·</span> FruktAi</span></footer>
    </main>
    {activeProduct && <Drawer title="Объяснение рекомендации" onClose={() => setActiveProduct(null)}><RecommendationDetails key={activeProduct.sku} product={activeProduct} draft={drafts[activeProduct.sku]} onDraft={draft => setDraft(activeProduct.sku, draft)} selected={selected.has(activeProduct.sku)} onToggle={() => toggle(activeProduct.sku)}/></Drawer>}
    {reviewProducts && <Drawer title="Проверка заказа" wide onClose={() => setReviewProducts(null)}><ReviewOrder products={reviewProducts} onExport={() => {
      try {
        exportCsv(reviewProducts);
        setNotice('CSV подготовлен. Позиций: ' + reviewProducts.length + '. Заказ поставщикам не отправлялся.');
        setReviewProducts(null);
      } catch { setError('Не удалось подготовить CSV. Повторите выгрузку.'); }
    }}/></Drawer>}
  </>;
}
