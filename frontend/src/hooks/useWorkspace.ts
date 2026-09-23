import { useEffect, useRef, useState } from 'react';
import { loadDashboard } from '../api/client';
import type { Override } from '../types/api';
import type { DemoProduct, DemoSnapshot } from '../types/demo';
import {
  filterProducts,
  initialFilters,
  type Filters,
  type ScenarioDraft,
} from '../utils/presentation';

export type View = 'table' | 'overview' | 'suppliers' | 'data' | 'activity';

/** Owns API state, request ordering, selections and explicit what-if overrides. */
export function useWorkspace() {
  const [dataset, setDataset] = useState(() => localStorage.getItem('fruktai-dataset') || 'demo');
  const [data, setData] = useState<DemoSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [view, setView] = useState<View>('table');
  const [grouped, setGrouped] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [compactNav, setCompactNav] = useState(
    () => window.matchMedia('(max-width: 1023px)').matches,
  );
  useEffect(() => {
    const query = window.matchMedia('(max-width: 1023px)');
    const update = () => setCompactNav(query.matches);
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileNav(false);
    };
    query.addEventListener('change', update);
    window.addEventListener('keydown', escape);
    return () => {
      query.removeEventListener('change', update);
      window.removeEventListener('keydown', escape);
    };
  }, []);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeProduct, setActiveProduct] = useState<DemoProduct | null>(null);
  const [reviewProducts, setReviewProducts] = useState<DemoProduct[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ScenarioDraft>>({});
  const [agentOpen, setAgentOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const requestNumber = useRef(0);
  const appliedOverrides = useRef<Override[]>([]);

  async function load(overrides: Override[] = [], targetDataset = dataset) {
    const request = ++requestNumber.current;
    setLoading(true);
    setError('');
    try {
      const result = await loadDashboard(overrides, targetDataset);
      if (request !== requestNumber.current) return;
      setData(result);
      if (targetDataset !== dataset) setView('table');
      setDataset(targetDataset);
      localStorage.setItem('fruktai-dataset', targetDataset);
      if (targetDataset !== dataset) {
        setDrafts({});
        setFilters(initialFilters);
        setActiveProduct(null);
      }
      appliedOverrides.current = overrides;
      setActiveProduct((previous) =>
        previous ? (result.products.find((p) => p.sku === previous.sku) ?? null) : null,
      );
      setReviewProducts(null);
      setSelected(
        (previous) =>
          new Set([...previous].filter((sku) => result.products.some((p) => p.sku === sku))),
      );
      return result;
    } catch (problem) {
      if (request === requestNumber.current)
        setError(problem instanceof Error ? problem.message : 'Не удалось загрузить рекомендации.');
    } finally {
      if (request === requestNumber.current) setLoading(false);
    }
  }
  useEffect(() => {
    void load();
    return () => {
      requestNumber.current++;
    };
  }, []);

  const products = data?.products ?? [];
  const filtered = filterProducts(products, filters);
  const selectedProducts = products.filter((p) => selected.has(p.sku));
  const visibleSelectedCount = filtered.filter((p) => selected.has(p.sku)).length;

  async function recalculateProduct(sku: string, draft: ScenarioDraft) {
    const overrides = appliedOverrides.current.filter((row) => row.sku !== sku);
    overrides.push({ sku, on_hand: Number(draft.onHand), in_transit: Number(draft.inTransit) });
    const result = await load(overrides);
    if (!result) throw new Error('Пересчёт не выполнен. Проверьте сообщение API.');
    setDraft(sku, undefined);
    setNotice('Пересчёт сохранён в БД. Run: ' + result.response.run_id);
  }

  function toggle(sku: string) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(sku)) next.delete(sku);
      else next.add(sku);
      return next;
    });
  }
  function toggleAll() {
    setSelected((previous) => {
      const next = new Set(previous);
      const allVisibleSelected = filtered.every((p) => previous.has(p.sku));
      filtered.forEach((p) => (allVisibleSelected ? next.delete(p.sku) : next.add(p.sku)));
      return next;
    });
  }
  function chooseKpi(type: 'orders' | 'risk' | 'anomaly' | 'stockout') {
    navigate('table');
    setFilters({
      ...initialFilters,
      onlyOrders: type === 'orders',
      status: type === 'risk' ? 'Дефицит' : '',
      signal: type === 'anomaly' || type === 'stockout' ? type : 'all',
    });
  }
  function navigate(next: View, bySupplier = false) {
    setView(next);
    setGrouped(bySupplier);
    setMobileNav(false);
    setProfileOpen(false);
    setFilters(initialFilters);
    if (next === 'activity') setAgentOpen(true);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  function openReview() {
    const rows = selectedProducts.length ? selectedProducts : filtered;
    if (!rows.length) {
      setNotice('Нет позиций для выгрузки. Измените фильтры.');
      return;
    }
    setReviewProducts(rows);
  }
  function setDraft(sku: string, draft: ScenarioDraft | undefined) {
    setDrafts((previous) => {
      const next = { ...previous };
      if (draft) next[sku] = draft;
      else delete next[sku];
      return next;
    });
  }

  const highRisk = products.filter((p) => p.status === 'Дефицит').length;
  const title =
    view === 'overview'
      ? 'Обзор запасов'
      : view === 'data'
        ? 'Источники данных'
        : view === 'activity'
          ? 'Ход анализа'
          : view === 'suppliers'
            ? 'Заказы по поставщикам'
            : 'План закупок';

  return {
    dataset,
    data,
    loading,
    error,
    notice,
    filters,
    view,
    grouped,
    mobileNav,
    compactNav,
    selected,
    activeProduct,
    reviewProducts,
    drafts,
    agentOpen,
    profileOpen,
    setProfileOpen,
    products,
    filtered,
    selectedProducts,
    visibleSelectedCount,
    highRisk,
    title,
    setFilters,
    setGrouped,
    setMobileNav,
    setNotice,
    setSelected,
    setActiveProduct,
    setReviewProducts,
    setAgentOpen,
    load,
    recalculateProduct,
    toggle,
    toggleAll,
    chooseKpi,
    navigate,
    openReview,
    setDraft,
  };
}
export type WorkspaceController = ReturnType<typeof useWorkspace>;
