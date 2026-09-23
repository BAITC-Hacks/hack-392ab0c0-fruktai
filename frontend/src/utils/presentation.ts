import type { DemoProduct, DemoStatus } from '../types/demo';

export const formatNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value);

export const formatDate = (value: string): string =>
  new Date(value).toLocaleDateString('ru-RU', { timeZone: 'Asia/Almaty' });

export const statusRank: Record<DemoStatus, number> = {
  'Дефицит': 0, 'Пограничный остаток': 1, 'В норме': 2,
};

export function quantitySummary(products: DemoProduct[]): string {
  const totals = new Map<string, number>();
  for (const product of products) {
    totals.set(product.unit, (totals.get(product.unit) ?? 0) + product.recommended);
  }
  return [...totals].sort(([a], [b]) => a.localeCompare(b, 'ru')).map(([unit, value]) => `${formatNumber(value)} ${unit}`).join(' · ') || '0 ед.';
}

export function shortReason(product: DemoProduct): string {
  if (product.onHand === 0) return 'Нет товара на складе';
  if (product.anomalyNote) return 'Разовая продажа исключена';
  if (product.stockoutNote) return 'Восстановлен упущенный спрос';
  if (product.status === 'Дефицит') return 'Низкий текущий остаток';
  return 'Плановое пополнение';
}

/** Input draft converted to the public override payload after validation. */
export interface ScenarioDraft { onHand: string; inTransit: string }
export function validateScenario(draft: ScenarioDraft): string | null {
  for (const [key, label] of [['onHand', 'Остаток'], ['inTransit', 'В пути']] as const) {
    const input = draft[key].trim();
    if (!input || !/^\d+$/.test(input)) {
      return `${label}: введите целое неотрицательное число.`;
    }
    const value = Number(input.replace(',', '.'));
    if (!Number.isFinite(value) || value > 1_000_000_000) {
      return `${label}: допустимо значение от 0 до 1 000 000 000.`;
    }
  }
  return null;
}

export type SortKey = 'risk' | 'sku' | 'supplier';
export interface Filters {
  search: string; supplier: string; category: string; status: string;
  onlyOrders: boolean; signal: 'all' | 'anomaly' | 'stockout'; sort: SortKey;
}
export const initialFilters: Filters = {
  search: '', supplier: '', category: '', status: '', onlyOrders: false,
  signal: 'all', sort: 'risk',
};
export function filterProducts(products: DemoProduct[], filters: Filters): DemoProduct[] {
  const search = filters.search.trim().toLocaleLowerCase('ru');
  return products.filter(product =>
    [product.sku, product.name, product.supplier].some(value => value.toLocaleLowerCase('ru').includes(search)) &&
    (!filters.supplier || product.supplier === filters.supplier) &&
    (!filters.category || product.category === filters.category) &&
    (!filters.status || product.status === filters.status) &&
    (!filters.onlyOrders || product.recommended > 0) &&
    (filters.signal !== 'anomaly' || !!product.anomalyNote) &&
    (filters.signal !== 'stockout' || !!product.stockoutNote)
  ).sort((a, b) => {
    if (filters.sort === 'sku') return a.sku.localeCompare(b.sku, 'ru');
    if (filters.sort === 'supplier') return a.supplier.localeCompare(b.supplier, 'ru');
    return statusRank[a.status] - statusRank[b.status] || Number(b.onHand === 0) - Number(a.onHand === 0);
  });
}

function plural(value: number, one: string, few: string, many: string): string {
  const mod100 = Math.abs(value) % 100;
  const mod10 = mod100 % 10;
  return mod100 >= 11 && mod100 <= 14 ? many : mod10 === 1 ? one : mod10 >= 2 && mod10 <= 4 ? few : many;
}
export const positionWord = (value: number): string => plural(value, 'позиция', 'позиции', 'позиций');
export const supplierWord = (value: number): string => plural(value, 'поставщик', 'поставщика', 'поставщиков');
