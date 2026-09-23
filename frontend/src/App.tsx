import { useEffect, useRef, useState } from 'react';
import { LayoutGrid, BarChart3, Database, ChevronRight, RefreshCw, ShoppingCart, Users, ShieldCheck, AlertTriangle, CalendarDays, Check, X, Search, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { loadDashboard, exportRun } from './api/client';
import type { Override } from './types/api';
import type { DemoProduct, DemoSnapshot } from './types/demo';
import { filterProducts, initialFilters, formatDate, type Filters, type ScenarioDraft } from './utils/presentation';
import { ImportPanel } from './components/ImportPanel';
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
  const [dataset, setDataset] = useState(() => localStorage.getItem('fruktai-dataset') || 'demo');
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
  const appliedOverrides = useRef<Override[]>([]);

  async function load(overrides: Override[] = [], targetDataset = dataset) {
    const request = ++requestNumber.current;
    setLoading(true); setError('');
    try {
      const result = await loadDashboard(overrides, targetDataset);
      if (request !== requestNumber.current) return;
      setData(result);
      setDataset(targetDataset); localStorage.setItem('fruktai-dataset', targetDataset);
      if (targetDataset !== dataset) { setDrafts({}); setFilters(initialFilters); setActiveProduct(null); }
      appliedOverrides.current = overrides;
      setActiveProduct(previous => previous ? result.products.find(p => p.sku === previous.sku) ?? null : null);
      setReviewProducts(null);
      setSelected(previous => new Set([...previous].filter(sku => result.products.some(p => p.sku === sku))));
      return result;
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

  async function recalculateProduct(sku: string, draft: ScenarioDraft) {
    const overrides = appliedOverrides.current.filter(row => row.sku !== sku);
    overrides.push({ sku, on_hand: Number(draft.onHand), in_transit: Number(draft.inTransit) });
    const result = await load(overrides);
    if (!result) throw new Error('Пересчёт не выполнен. Проверьте сообщение API.');
    setDraft(sku, undefined);
    setNotice('Пересчёт сохранён в БД. Run: ' + result.response.run_id);
  }

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
      {data && <nav className="header-nav" aria-label="Основная навигация"><button className={view !== 'data' && !grouped ? 'is-active' : ''} onClick={() => { setView('table'); setGrouped(false); }}><ShoppingCart size={18}/>План закупок</button><button className={grouped ? 'is-active' : ''} onClick={() => { setView('table'); setGrouped(true); }}><Users size={18}/>Поставщики</button><button onClick={() => { setView('data'); setAgentOpen(true); }}><ShieldCheck size={18}/>Ход анализа</button></nav>}
      <div className="header-user"><span className="avatar">ББ</span><span><strong>Баймурат Б.</strong><small>Менеджер закупок</small></span></div>
    </header>
    <main id="main-content">
      <div className="page-heading"><div><div className="title-row"><h1>План закупок</h1></div><p>Рекомендации по пополнению склада</p></div><div className="heading-actions"><button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={16}/>{loading ? 'Загрузка…' : 'Обновить данные'}</button>{data && <button className="primary-button" onClick={openReview}><ShoppingCart size={17}/>Проверить заказ{selectedProducts.length ? <span className="button-count">{selectedProducts.length}</span> : null}</button>}</div></div>
      <div className="context-row"><span>API · {data?.dataset === 'demo' ? 'учебный набор demo' : (data?.dataset || dataset)}</span><span><CalendarDays size={14}/>{data ? 'Срез: ' + formatDate(data.updatedAt) + ' · ' + new Date(data.updatedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }) + ' (UTC+5)' : 'Дата среза не получена'}</span>{data && <button className="context-link" onClick={() => setView('data')}>Источник и полнота данных <ChevronRight size={12}/></button>}</div>
      <ImportPanel busy={loading} onCalculate={id => load([], id)}/>
      {dataset !== 'demo' && <button className="text-button" disabled={loading} onClick={() => void load([], 'demo')}>Вернуться к учебному набору demo</button>}
      {error && <div className="error-banner" role="alert"><AlertTriangle size={20}/><div><strong>Не удалось обновить рекомендации</strong><p>{error}</p>{data && <p>На экране сохранён предыдущий набор.</p>}</div><button className="secondary-button" onClick={() => void load()}>Повторить загрузку</button></div>}
      {notice && <div className="notice-banner" role="status"><Check size={17}/><span>{notice}</span><button className="icon-button" aria-label="Закрыть уведомление" onClick={() => setNotice('')}><X size={16}/></button></div>}
      {loading && !data ? <LoadingState/> : data && <>
        <KpiCards products={filtered} onSelect={chooseKpi}/>
        <nav className="workspace-nav" aria-label="Представление данных">{views.map(({ id, label, Icon }) => <button key={id} className={view === id ? 'active' : ''} onClick={() => setView(id)} aria-current={view === id ? 'page' : undefined}><Icon size={17}/><span>{label}</span></button>)}</nav>
        <div className={'workspace ' + (!showAnalytics || view === 'data' ? 'without-analytics' : '')} id="workspace">
          <div className="workspace-content">
            {view !== 'data' && <FiltersBar products={products} value={filters} onChange={setFilters}><label className="checkbox-label"><input type="checkbox" checked={grouped} onChange={e => { setGrouped(e.target.checked); setView('table'); }}/>По поставщикам</label><button className="icon-button filter-display-toggle" aria-label={showAnalytics ? 'Скрыть аналитику' : 'Показать аналитику'} title={showAnalytics ? 'Скрыть аналитику' : 'Показать аналитику'} onClick={() => setShowAnalytics(!showAnalytics)}>{showAnalytics ? <PanelRightClose size={17}/> : <PanelRightOpen size={17}/>}</button></FiltersBar>}
            {view === 'data' ? <><DataView data={data}/><AgentRunPanel steps={data.response.agent_steps} runId={data.response.run_id} open={agentOpen} onChange={setAgentOpen}/></> : filtered.length === 0 ? <div className="empty-state"><Search size={30}/><h2>Подходящих позиций нет</h2><p>Попробуйте другой запрос или сбросьте фильтры.</p><button className="secondary-button" onClick={() => setFilters(initialFilters)}>Сбросить фильтры</button></div> : view === 'comparison' ? <Comparison products={filtered}/> : <RecommendationsTable products={filtered} selected={selected} activeSku={activeProduct?.sku ?? null} grouped={grouped} sort={filters.sort} onSort={sort => setFilters({ ...filters, sort })} onOpen={setActiveProduct} onToggle={toggle} onToggleAll={toggleAll}/>}
            {view !== 'data' && <div className="table-footer"><span>Показано <b>{filtered.length}</b> из {products.length} позиций</span><span>Рекомендации требуют проверки менеджером</span></div>}
            {selectedProducts.length > 0 && <div className="selection-bar"><span><Check size={16}/><b>Выбрано: {selectedProducts.length}</b>{selectedProducts.length > visibleSelectedCount && <small>Скрыто фильтрами: {selectedProducts.length - visibleSelectedCount}</small>}</span><div><button className="text-button" onClick={() => setSelected(new Set())}>Снять выбор</button><button className="primary-button" onClick={openReview}>Проверить и экспортировать <ChevronRight size={15}/></button></div></div>}
          </div>
          {showAnalytics && view !== 'data' && <Analytics products={filtered} onStatus={status => { setView('table'); setFilters({ ...filters, status }); }}/>}
        </div>
      </>}
      <footer className="app-footer"><span>Электрокомплект <span>·</span> Рабочее место закупок</span><span>HackAlem AI <span>·</span> FruktAi</span></footer>
    </main>
    {activeProduct && <Drawer title="Объяснение рекомендации" onClose={() => setActiveProduct(null)}><RecommendationDetails key={activeProduct.sku} product={activeProduct} runId={data!.response.run_id} draft={drafts[activeProduct.sku]} onDraft={draft => setDraft(activeProduct.sku, draft)} selected={selected.has(activeProduct.sku)} onToggle={() => toggle(activeProduct.sku)} busy={loading} onRecalculate={draft => recalculateProduct(activeProduct.sku, draft)}/></Drawer>}
    {reviewProducts && <Drawer title="Проверка заказа" wide onClose={() => setReviewProducts(null)}><ReviewOrder products={reviewProducts} onExport={async format => {
      try {
        if (!data) throw new Error('Нет расчёта');
        await exportRun(data.response.run_id, reviewProducts.map(p => p.sku), format);
        setNotice('Экспорт подготовлен. Позиций: ' + reviewProducts.length + '. Заказ поставщикам не отправлялся.');
        setReviewProducts(null);
      } catch { throw new Error('Не удалось экспортировать сохранённый расчёт. Повторите выгрузку.'); }
    }}/></Drawer>}
  </>;
}
