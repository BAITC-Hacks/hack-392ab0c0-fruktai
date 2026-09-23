import { useEffect, useRef, useState } from 'react';
import { LayoutGrid, BarChart3, Database, ChevronRight, RefreshCw, ShoppingCart, Users, ShieldCheck, AlertTriangle, Check, X, Search, Upload, Layers3, Warehouse, ArrowUpRight, Menu, Activity } from 'lucide-react';
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

type View = 'table' | 'overview' | 'data' | 'activity';


export default function App() {
  const [dataset, setDataset] = useState(() => localStorage.getItem('fruktai-dataset') || 'demo');
  const [data, setData] = useState<DemoSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [view, setView] = useState<View>('table');
  const [grouped, setGrouped] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [compactNav, setCompactNav] = useState(() => window.matchMedia('(max-width: 1023px)').matches);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 1023px)');
    const update = () => setCompactNav(query.matches);
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileNav(false); };
    query.addEventListener('change', update); window.addEventListener('keydown', escape);
    return () => { query.removeEventListener('change', update); window.removeEventListener('keydown', escape); };
  }, []);
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
      if (targetDataset !== dataset) setView('table');
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
  function navigate(next: View, bySupplier = false) { setView(next); setGrouped(bySupplier); setMobileNav(false); }
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

  const highRisk = products.filter(p => p.status === 'Дефицит').length;
  const title = view === 'overview' ? 'Обзор запасов' : view === 'data' ? 'Источники данных'
    : view === 'activity' ? 'Ход анализа' : grouped ? 'Заказы по поставщикам' : 'План закупок';
  const navItems = [
    { id: 'overview' as View, label: 'Обзор запасов', Icon: BarChart3 },
    { id: 'table' as View, label: 'Рекомендации', Icon: ShoppingCart, count: products.filter(p => p.recommended > 0).length },
    { id: 'table' as View, label: 'Поставщики', Icon: Users, suppliers: true },
    { id: 'data' as View, label: 'Источники данных', Icon: Database },
    { id: 'activity' as View, label: 'Ход анализа', Icon: Activity },
  ];
  return <>
    <a className="skip-link" href="#main-content">Перейти к рекомендациям</a>
    {mobileNav && <button className="nav-scrim" aria-label="Закрыть навигацию" onClick={() => setMobileNav(false)}/>}
    <aside className={'app-sidebar' + (mobileNav ? ' is-open' : '')} inert={compactNav && !mobileNav}>
      <a className="brand" href="#main-content" onClick={() => navigate('table')} aria-label="FruktAI — план закупок">
        <span className="brand-symbol"><Layers3 size={23} strokeWidth={1.8}/></span><strong>frukt<span>ai</span></strong><span className="workspace-badge">WORKSPACE</span>
      </a>
      <div className="workspace-identity"><span className="workspace-avatar">ЭК</span><div><strong>Электрокомплект</strong><small>Планирование закупок</small></div></div>
      <span className="nav-section-label">Рабочее пространство</span>
      <nav aria-label="Основная навигация">{navItems.map(({ id, label, Icon, count, suppliers }) => {
        const active = view === id && (id !== 'table' || grouped === !!suppliers);
        return <button key={label} className={active ? 'is-active' : ''} aria-current={active ? 'page' : undefined}
          onClick={() => navigate(id, suppliers)}><Icon size={18}/><span>{label}</span>{count !== undefined && data && <b>{count}</b>}</button>;
      })}</nav>
      <div className="sidebar-bottom">
        <div className="workflow-note"><ShieldCheck size={19}/><strong>Проверяемый расчёт</strong><p>Алгоритм определяет количество.<br/>AI помогает объяснить решение.</p></div>
        <div className="sidebar-version"><span>HackAlem AI</span><span>MVP</span></div>
      </div>
    </aside>
    <div className="app-shell" inert={compactNav && mobileNav}>
      <header className="app-topbar">
        <button className="icon-button mobile-nav-toggle" aria-label="Открыть навигацию" onClick={() => setMobileNav(true)}><Menu size={20}/></button>
        <div className="breadcrumbs"><span>Закупки</span><ChevronRight size={14}/><strong>{title}</strong></div>
        <div className="topbar-context"><span className="warehouse-label"><Warehouse size={15}/>{data?.metadata?.warehouse_id || 'Склад не указан'}</span>
          <span className={'connection-status' + (error ? ' has-error' : '')}><i/>{loading ? 'Расчёт…' : error ? 'Ошибка обновления' : data ? 'Расчёт получен' : 'Нет данных'}</span>
          <span className="avatar" title="Рабочее место менеджера, без авторизации">МЗ</span>
        </div>
      </header>
      <main id="main-content">
        <div className="page-heading"><div><h1>{title}</h1>
          <p>{view === 'data' ? 'Проверенные источники — основа точной рекомендации.' : view === 'activity' ? 'От исходных данных до объяснимого решения.' : 'Нужный товар. В нужном количестве. Вовремя.'}</p></div>
          <div className="heading-actions">
            <button className="secondary-button" onClick={() => void load()} disabled={loading} title="Повторить расчёт исходного набора без ручных поправок"><RefreshCw size={16} className={loading ? 'is-spinning' : ''}/>{loading ? 'Загрузка…' : 'Обновить данные'}</button>
            {data && <button className="primary-button" onClick={openReview} disabled={loading}><ShoppingCart size={17}/>Проверить заказ{selectedProducts.length > 0 && <span className="button-count">{selectedProducts.length}</span>}</button>}
          </div>
        </div>
        <div className="context-row"><span className="dataset-badge">{(data?.dataset || dataset) === 'demo' ? 'Учебный набор · demo' : 'Загруженные данные'}</span>
          <span>{data ? 'Расчёт: ' + formatDate(data.updatedAt) + ', ' + new Date(data.updatedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }) + ' (UTC+5)' : 'Ожидаем ответ API'}</span>
          <span className="source-freshness" title="API возвращает время расчёта, но не дату актуальности складских остатков">Свежесть источников не подтверждена</span>
          {view !== 'data' && <button className="context-link" onClick={() => navigate('data')}><Upload size={14}/>Загрузить данные / выгрузку 1С</button>}
        </div>
        {error && <div className="error-banner" role="alert"><AlertTriangle size={20}/><div><strong>Не удалось обновить рекомендации</strong><p>{error}</p>{data && <p>На экране сохранён предыдущий набор.</p>}</div><button className="secondary-button" onClick={() => void load()}>Повторить загрузку</button></div>}
        {notice && <div className="notice-banner" role="status"><Check size={17}/><span>{notice}</span><button className="icon-button" aria-label="Закрыть уведомление" onClick={() => setNotice('')}><X size={16}/></button></div>}
        {loading && !data && <LoadingState/>}
        {data && (view === 'table' || view === 'overview') && <>
          {highRisk > 0 && <div className="risk-banner"><span className="risk-banner-icon"><AlertTriangle size={19}/></span><div><strong>Приоритет сегодня: {highRisk} {highRisk === 1 ? 'позиция' : highRisk < 5 ? 'позиции' : 'позиций'} с риском дефицита</strong><p>Проверьте покрытие спроса на срок поставки и включите нужные позиции в заказ.</p></div><button onClick={() => chooseKpi('risk')}>Показать позиции<ArrowUpRight size={16}/></button></div>}
          <KpiCards products={products} summary={data.response.summary} onSelect={chooseKpi}/>
          {view === 'overview' ? <div className="overview-grid">
            <Analytics products={filtered} onStatus={status => { navigate('table'); setFilters({ ...filters, status }); }}/>
            <Comparison products={filtered}/>
          </div> : <section className="workspace-content" aria-label="Закупочная очередь">
            <div className="queue-heading"><div><h2>{grouped ? 'Очередь по поставщикам' : 'Рекомендации к проверке'}</h2><p>От риска — к решению. Откройте позицию, чтобы проверить расчёт.</p></div>
              <div className="segmented-control" aria-label="Группировка"><button className={!grouped ? 'active' : ''} aria-pressed={!grouped} onClick={() => setGrouped(false)}><LayoutGrid size={15}/>Все позиции</button><button className={grouped ? 'active' : ''} aria-pressed={grouped} onClick={() => setGrouped(true)}><Users size={15}/>По поставщикам</button></div>
            </div>
            <FiltersBar products={products} value={filters} onChange={setFilters}/>
            {filtered.length === 0 ? <div className="empty-state"><Search size={30}/><h2>Подходящих позиций нет</h2><p>Попробуйте другой запрос или сбросьте фильтры.</p><button className="secondary-button" onClick={() => setFilters(initialFilters)}>Сбросить фильтры</button></div>
              : <RecommendationsTable products={filtered} selected={selected} activeSku={activeProduct?.sku ?? null} grouped={grouped} sort={filters.sort} onSort={sort => setFilters({ ...filters, sort })} onOpen={setActiveProduct} onToggle={toggle} onToggleAll={toggleAll}/>}
            <div className="table-footer"><span>Показано <b>{filtered.length}</b> из {products.length} позиций</span><span><ShieldCheck size={14}/>Решение подтверждает менеджер</span></div>
            {selectedProducts.length > 0 && <div className="selection-bar"><span><Check size={16}/><b>Выбрано: {selectedProducts.length}</b>{selectedProducts.length > visibleSelectedCount && <small>Скрыто фильтрами: {selectedProducts.length - visibleSelectedCount}</small>}</span><div><button className="text-button" onClick={() => setSelected(new Set())}>Снять выбор</button><button className="primary-button" onClick={openReview} disabled={loading}>Проверить и экспортировать <ChevronRight size={15}/></button></div></div>}
          </section>}
          <AgentRunPanel steps={data.response.agent_steps} runId={data.response.run_id} open={agentOpen} onChange={setAgentOpen}/>
        </>}
        {view === 'data' && <div className="sources-layout">
          <ImportPanel busy={loading} initiallyOpen onCalculate={async id => { const result = await load([], id); if (result) navigate('table'); return result; }}/>
          {data && <DataView data={data}/>}
        </div>}
        {view === 'activity' && data && <section className="activity-view"><div className="section-heading"><ShieldCheck size={22}/><div><h2>Прозрачный процесс</h2><p>Статусы и детали последнего открытого расчёта из API.</p></div></div><AgentRunPanel steps={data.response.agent_steps} runId={data.response.run_id} open onChange={() => {}}/><p className="helper">Журнал показывает завершённый запуск, а не трансляцию этапов в реальном времени.</p></section>}
        {dataset !== 'demo' && <button className="text-button" disabled={loading} onClick={() => void load([], 'demo')}>Вернуться к учебному набору demo</button>}
        <footer className="app-footer"><span>FruktAI <span> / </span> Рабочее место закупок</span><span>Расчёт → проверка → экспорт</span></footer>
      </main>
    </div>
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
